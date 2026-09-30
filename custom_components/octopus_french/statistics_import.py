"""Long-term statistics import for electricity and gas."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .const import COST_KEY_TO_LABEL, DOMAIN, ENERGY_KEY_TO_LABEL
from .utils import (
    gas_daily_values,
    get_tariff_rate_for_key,
    normalize_consumption_label,
    reading_local_day,
)

if TYPE_CHECKING:
    from .coordinator import OctopusFrenchDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_LABEL_TO_ENERGY_KEY = {label: key for key, label in ENERGY_KEY_TO_LABEL.items()}
_LABEL_TO_COST_KEY = {label: key for key, label in COST_KEY_TO_LABEL.items()}

_LOGGED_DAYS = 10


def _log_daily_series(
    label: str, daily_values: dict[datetime, float], rate: float | None = None
) -> None:
    """Log the computed daily series fed to statistics."""
    if not _LOGGER.isEnabledFor(logging.DEBUG) or not daily_values:
        return

    days = sorted(daily_values)
    detail = ", ".join(
        f"{day:%Y-%m-%d}={daily_values[day]:.3f}" for day in days[-_LOGGED_DAYS:]
    )
    _LOGGER.debug(
        "%s: %s days from %s to %s, total %.3f, rate %s; last %s days: %s",
        label,
        len(days),
        f"{days[0]:%Y-%m-%d}",
        f"{days[-1]:%Y-%m-%d}",
        sum(daily_values.values()),
        rate if rate is not None else "n/a",
        min(_LOGGED_DAYS, len(days)),
        detail,
    )


class OctopusStatisticsImporter:
    """Import external statistics once per coordinator update."""

    def __init__(
        self, hass: HomeAssistant, coordinator: OctopusFrenchDataUpdateCoordinator
    ) -> None:
        """Initialize the importer."""
        self.hass = hass
        self.coordinator = coordinator
        self.last_imported: dict[str, str] = {}
        self._import_in_progress = False

    @callback
    def schedule_import(self) -> None:
        """Schedule an import pass on coordinator update."""
        self.hass.async_create_task(self.async_import_all())

    async def async_import_all(self) -> None:
        """Run a full import pass, skipping if one is already in progress."""
        if self._import_in_progress:
            _LOGGER.debug("Statistics import already running, skipping this pass")
            return
        self._import_in_progress = True
        try:
            try:
                await self._async_import_electricity()
            except Exception:
                _LOGGER.exception("Electricity statistics import failed")
            await self._async_import_gas()
        finally:
            self._import_in_progress = False

    def _collect_electricity_daily_values(
        self, data: dict[str, Any], prm_id: str, readings: list[dict[str, Any]]
    ) -> dict[str, dict[datetime, float]]:
        """Collect daily values of every key from the readings in one pass."""
        daily_values: dict[str, dict[datetime, float]] = {}
        rates: dict[str, float | None] = {}

        try:
            sorted_readings = sorted(readings, key=lambda x: x.get("startAt", ""))
        except (TypeError, KeyError) as err:
            _LOGGER.warning(
                "Failed to sort readings for PRM %s, skipping import: %s", prm_id, err
            )
            return daily_values

        for reading in sorted_readings:
            day = reading_local_day(reading.get("startAt"))
            if day is None:
                continue

            for stat in (reading.get("metaData") or {}).get("statistics", []):
                label = normalize_consumption_label(stat.get("label", ""))
                value = stat.get("value")

                energy_key = _LABEL_TO_ENERGY_KEY.get(label)
                if energy_key is not None and value is not None:
                    daily_values.setdefault(energy_key, {})[day] = float(value)

                if (cost_key := _LABEL_TO_COST_KEY.get(label)) is not None:
                    cost = self._compute_cost(data, prm_id, cost_key, stat, rates)
                    if cost is not None:
                        daily_values.setdefault(cost_key, {})[day] = cost

        return daily_values

    def _compute_cost(
        self,
        data: dict[str, Any],
        prm_id: str,
        cost_key: str,
        stat: dict[str, Any],
        rates: dict[str, float | None],
    ) -> float | None:
        """Return the API cost of a reading, or kWh times the current rate."""

        amount = (stat.get("costInclTax") or {}).get("estimatedAmount")
        if amount is not None:
            try:
                return float(amount) / 100
            except (ValueError, TypeError):
                pass

        value = stat.get("value")
        if value is None:
            return None
        if cost_key not in rates:
            rates[cost_key] = get_tariff_rate_for_key(data, prm_id, cost_key)
        rate = rates[cost_key]
        return float(value) * rate if rate else None

    async def _async_import_electricity(self) -> None:
        """Import electricity statistics for every PRM."""
        data = self.coordinator.data or {}
        for prm_id, prm_data in data.get("electricity_by_prm", {}).items():
            readings = prm_data.get("readings", [])
            if not readings:
                continue

            daily_values = self._collect_electricity_daily_values(
                data, prm_id, readings
            )
            for key, values in daily_values.items():
                _log_daily_series(f"electricity {prm_id} {key}", values)
                is_energy = key.startswith("energy_")
                await self._async_import_statistic(
                    statistic_id=f"{DOMAIN}:{prm_id}_{key}",
                    name=f"Octopus Energy {key}",
                    unit_class="energy" if is_energy else None,
                    unit=UnitOfEnergy.KILO_WATT_HOUR if is_energy else CURRENCY_EURO,
                    daily_values=values,
                )

    async def _async_import_gas(self) -> None:
        """Import gas statistics for every metered PCE."""
        data = self.coordinator.data or {}
        gas_by_pce = data.get("gas_by_pce") or {}

        for pce_ref, gas_data in gas_by_pce.items():
            consumption_values = gas_daily_values(gas_data)
            if not consumption_values:
                _LOGGER.debug(
                    "No gas reading to import for PCE %s (%s monthly, %s daily, "
                    "%s index)",
                    pce_ref,
                    len(gas_data.get("monthly") or []),
                    len(gas_data.get("daily") or []),
                    len(gas_data.get("index") or []),
                )
                continue

            rate = get_tariff_rate_for_key(data, pce_ref, "cost")
            _log_daily_series(f"gas {pce_ref}", consumption_values, rate)
            if rate:
                cost_values = {
                    day: value * rate for day, value in consumption_values.items()
                }
            else:
                cost_values = {}
                _LOGGER.warning(
                    "No tariff rate found for gas meter %s, cost will not be imported",
                    pce_ref,
                )

            await self._async_import_statistic(
                statistic_id=f"{DOMAIN}:{pce_ref}_consumption",
                name=f"Octopus Energy Gas Consumption {pce_ref}",
                unit_class="energy",
                unit=UnitOfEnergy.KILO_WATT_HOUR,
                daily_values=consumption_values,
            )
            await self._async_import_statistic(
                statistic_id=f"{DOMAIN}:{pce_ref}_cost",
                name=f"Octopus Energy Gas Cost {pce_ref}",
                unit_class=None,
                unit=CURRENCY_EURO,
                daily_values=cost_values,
            )

    async def async_recompute_electricity(
        self, start_date: datetime, prm_id: str | None = None
    ) -> dict[str, int]:
        """Recompute electricity statistics from `start_date` until now."""
        data = self.coordinator.data or {}
        end = dt_util.now()
        imported: dict[str, int] = {}

        for meter in data.get("supply_points", {}).get("electricity", []):
            meter_prm = meter.get("prm")
            if not meter_prm or (prm_id is not None and meter_prm != prm_id):
                continue

            readings = await self.coordinator.api_client.get_energy_readings(
                meter.get("property_id") or data["account_id"],
                start_date.isoformat(),
                end.isoformat(),
                meter_prm,
                utility_type="electricity",
                reading_frequency="DAY_INTERVAL",
                reading_quality="ACTUAL",
            )
            _LOGGER.info(
                "Recomputing statistics for PRM %s from %s readings between %s and %s",
                meter_prm,
                len(readings),
                f"{start_date:%Y-%m-%d}",
                f"{end:%Y-%m-%d}",
            )

            daily_values = self._collect_electricity_daily_values(
                data, meter_prm, readings
            )
            for key, values in daily_values.items():
                is_energy = key.startswith("energy_")
                statistic_id = f"{DOMAIN}:{meter_prm}_{key}"

                self.last_imported.pop(statistic_id, None)
                await self._async_import_statistic(
                    statistic_id=statistic_id,
                    name=f"Octopus Energy {key}",
                    unit_class="energy" if is_energy else None,
                    unit=UnitOfEnergy.KILO_WATT_HOUR if is_energy else CURRENCY_EURO,
                    daily_values=values,
                )
                imported[statistic_id] = len(values)

        return imported

    def _expected_statistic_ids(self) -> set[str]:
        """Return the statistic IDs that active meters can feed."""
        data = self.coordinator.data or {}
        expected: set[str] = set()

        for meter in data.get("supply_points", {}).get("electricity", []):
            if prm_id := meter.get("prm"):
                expected.update(
                    f"{DOMAIN}:{prm_id}_{key}"
                    for key in (*ENERGY_KEY_TO_LABEL, *COST_KEY_TO_LABEL)
                )

        for pce_ref in data.get("gas_by_pce") or {}:
            expected.add(f"{DOMAIN}:{pce_ref}_consumption")
            expected.add(f"{DOMAIN}:{pce_ref}_cost")

        return expected

    async def async_find_orphan_statistic_ids(self) -> list[str]:
        """Return domain statistics that no active meter feeds anymore."""
        all_ids = await get_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        prefix = f"{DOMAIN}:"
        expected = self._expected_statistic_ids()
        return sorted(
            statistic_id
            for entry in all_ids
            if (statistic_id := entry.get("statistic_id", "")).startswith(prefix)
            and statistic_id not in expected
        )

    async def async_purge_orphan_statistics(self, statistic_ids: list[str]) -> None:
        """Permanently delete the given statistic series."""
        if not statistic_ids:
            return
        instance = get_instance(self.hass)
        await instance.async_add_executor_job(
            clear_statistics, instance, list(statistic_ids)
        )
        _LOGGER.info("Deleted statistics: %s", ", ".join(statistic_ids))

    async def _async_import_statistic(
        self,
        statistic_id: str,
        name: str,
        unit_class: str | None,
        unit: str,
        daily_values: dict[datetime, float],
    ) -> None:
        """Import one statistic series."""
        if not daily_values:
            _LOGGER.debug("Nothing to import for %s: empty series", statistic_id)
            return

        last_imported_day, cumulative_sum = await self._async_get_last_stats(
            statistic_id
        )

        days = sorted(daily_values)
        statistics: list[StatisticData] = []

        contiguous = bool(days) and len(days) == (days[-1] - days[0]).days + 1

        if contiguous:
            cumulative_sum = await self._async_get_anchor_sum(statistic_id, days[0])
            _LOGGER.debug(
                "%s: continuous series of %s days, rewriting sums from anchor %.3f",
                statistic_id,
                len(days),
                cumulative_sum,
            )
        else:
            _LOGGER.debug(
                "%s: series has gaps (%s of %s days), continuing cumulative sum from "
                "%.3f (last imported day: %s)",
                statistic_id,
                len(days),
                (days[-1] - days[0]).days + 1 if days else 0,
                cumulative_sum,
                last_imported_day,
            )

        if contiguous:
            for day in days:
                reading_value = daily_values[day]
                cumulative_sum += reading_value
                statistics.append(
                    StatisticData(start=day, state=reading_value, sum=cumulative_sum)
                )
                self.last_imported[statistic_id] = day.isoformat()
        else:
            for day in days:
                if last_imported_day is not None and day <= last_imported_day:
                    continue
                reading_value = daily_values[day]
                cumulative_sum += reading_value
                statistics.append(
                    StatisticData(start=day, state=reading_value, sum=cumulative_sum)
                )
                self.last_imported[statistic_id] = day.isoformat()

        if not statistics:
            _LOGGER.debug("No new statistics to import for %s", statistic_id)
            return

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class=unit_class,
            unit_of_measurement=unit,
        )

        try:
            async_add_external_statistics(self.hass, metadata, statistics)
            _LOGGER.debug(
                "Imported %d statistics for %s (last date: %s, cumulative sum: %.3f)",
                len(statistics),
                statistic_id,
                self.last_imported.get(statistic_id),
                cumulative_sum,
            )
        except Exception:
            _LOGGER.exception("Failed to import statistics for %s", statistic_id)

    async def _async_get_last_stats(
        self, statistic_id: str
    ) -> tuple[datetime | None, float]:
        """Return the last imported day and current cumulative sum."""
        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, False, {"sum", "start"}
            )
        except (OSError, ValueError, TypeError):
            _LOGGER.debug(
                "Could not fetch last statistics for %s, starting sum at 0",
                statistic_id,
            )
            return None, 0.0

        if not (last_stats and last_stats.get(statistic_id)):
            return None, 0.0

        last_entry = last_stats[statistic_id][0]
        cumulative_sum = float(last_entry.get("sum") or 0.0)
        last_imported_day: datetime | None = None
        last_start = last_entry.get("start")
        if last_start is not None:
            last_imported_day = datetime.fromtimestamp(
                float(last_start), tz=dt_util.UTC
            ).astimezone(dt_util.DEFAULT_TIME_ZONE)
        return last_imported_day, cumulative_sum

    async def _async_get_anchor_sum(
        self, statistic_id: str, first_day: datetime
    ) -> float:
        """Return the cumulative sum of the last statistic before first_day."""
        try:
            rows = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                first_day - timedelta(days=40),
                first_day,
                {statistic_id},
                "day",
                None,
                {"sum"},
            )
        except (OSError, ValueError, TypeError):
            _LOGGER.debug("Could not fetch anchor sum for %s, using 0", statistic_id)
            return 0.0

        entries = rows.get(statistic_id) if rows else None
        if not entries:
            return 0.0

        first_ts = first_day.timestamp()
        anchor = 0.0
        anchor_start: float | None = None
        for row in entries:
            row_start = row.get("start")
            if row_start is None or float(row_start) >= first_ts:
                continue
            if anchor_start is None or float(row_start) > anchor_start:
                anchor_start = float(row_start)
                anchor = float(row.get("sum") or 0.0)
        return anchor
