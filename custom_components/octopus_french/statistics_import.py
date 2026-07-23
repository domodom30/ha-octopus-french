"""Import centralisé des statistiques long-terme (électricité + gaz)."""

from __future__ import annotations

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
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .const import COST_KEY_TO_LABEL, DOMAIN, ENERGY_KEY_TO_LABEL
from .utils import get_tariff_rate_for_key, normalize_consumption_label

if TYPE_CHECKING:
    from .coordinator import OctopusFrenchDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_LABEL_TO_ENERGY_KEY = {label: key for key, label in ENERGY_KEY_TO_LABEL.items()}
_LABEL_TO_COST_KEY = {label: key for key, label in COST_KEY_TO_LABEL.items()}


def _reading_day(start_at: str | None) -> datetime | None:
    """Minuit local du jour calendaire d'un relevé (fusionne les offsets UTC)."""
    if not start_at:
        return None
    try:
        return (
            datetime.fromisoformat(start_at)
            .astimezone(dt_util.DEFAULT_TIME_ZONE)
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
    except (ValueError, TypeError, AttributeError) as err:
        _LOGGER.warning("Error parsing date %s: %s", start_at, err)
        return None


class OctopusStatisticsImporter:
    """Importe les statistiques externes en une passe par cycle de coordinator."""

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
        """Listener du coordinator : planifie une passe d'import."""
        self.hass.async_create_task(self.async_import_all())

    async def async_import_all(self) -> None:
        """Run a full import pass, skipping if one is already in progress."""
        if self._import_in_progress:
            return
        self._import_in_progress = True
        try:
            await self._async_import_electricity()
            await self._async_import_gas()
        finally:
            self._import_in_progress = False

    def _collect_electricity_daily_values(
        self, data: dict[str, Any], prm_id: str, readings: list[dict[str, Any]]
    ) -> dict[str, dict[datetime, float]]:
        """Une passe sur les readings → valeurs journalières de toutes les clés."""
        daily_values: dict[str, dict[datetime, float]] = {}
        rates: dict[str, float | None] = {}

        try:
            sorted_readings = sorted(readings, key=lambda x: x.get("startAt", ""))
        except (TypeError, KeyError) as err:
            _LOGGER.warning("Error sorting readings: %s", err)
            return daily_values

        for reading in sorted_readings:
            day = _reading_day(reading.get("startAt"))
            if day is None:
                continue

            for stat in (reading.get("metaData") or {}).get("statistics", []):
                label = normalize_consumption_label(stat.get("label", ""))
                value = stat.get("value")

                if (
                    (energy_key := _LABEL_TO_ENERGY_KEY.get(label)) is not None
                    and value is not None
                    and float(value) > 0
                ):
                    daily_values.setdefault(energy_key, {})[day] = float(value)

                if (cost_key := _LABEL_TO_COST_KEY.get(label)) is not None:
                    cost = self._compute_cost(data, prm_id, cost_key, stat, rates)
                    if cost is not None and cost > 0:
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
        """Coût d'un relevé : montant réel de l'API, sinon kWh x tarif actuel."""

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
                is_energy = key.startswith("energy_")
                await self._async_import_statistic(
                    statistic_id=f"{DOMAIN}:{prm_id}_{key}",
                    name=f"Octopus Energy {key}",
                    unit_class="energy" if is_energy else None,
                    unit=UnitOfEnergy.KILO_WATT_HOUR if is_energy else CURRENCY_EURO,
                    daily_values=values,
                )

    async def _async_import_gas(self) -> None:
        """Import gas statistics for the metered PCE."""
        data = self.coordinator.data or {}
        readings = data.get("gas", [])
        if not readings:
            return

        gas_points = data.get("supply_points", {}).get("gas", [])
        pce_ref = gas_points[0].get("prm") if gas_points else None
        if not pce_ref:
            return

        try:
            sorted_readings = sorted(readings, key=lambda x: x.get("startAt", ""))
        except (TypeError, KeyError) as err:
            _LOGGER.warning("Error sorting gas readings: %s", err)
            return

        rate = get_tariff_rate_for_key(data, pce_ref, "cost")
        consumption_values: dict[datetime, float] = {}
        cost_values: dict[datetime, float] = {}

        for reading in sorted_readings:
            day = _reading_day(reading.get("startAt"))
            if day is None:
                continue
            consumption = float(reading.get("value") or 0)
            if consumption <= 0:
                continue
            consumption_values[day] = consumption
            if rate:
                cost_values[day] = consumption * rate
            else:
                _LOGGER.warning(
                    "No tariff rate found for gas meter %s, cost will be 0", pce_ref
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

    async def _async_import_statistic(
        self,
        statistic_id: str,
        name: str,
        unit_class: str | None,
        unit: str,
        daily_values: dict[datetime, float],
    ) -> None:
        """Import one statistic series (algorithme historique, inchangé)."""
        if not daily_values:
            return

        last_imported_day, cumulative_sum = await self._async_get_last_stats(
            statistic_id
        )

        days = sorted(daily_values)
        statistics: list[StatisticData] = []

        contiguous = bool(days) and len(days) == (days[-1] - days[0]).days + 1

        if contiguous:
            cumulative_sum = await self._async_get_anchor_sum(statistic_id, days[0])
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
                "Imported %d statistics for %s (last date: %s)",
                len(statistics),
                statistic_id,
                self.last_imported.get(statistic_id),
            )
        except Exception:
            _LOGGER.exception("Failed to import statistics for %s", statistic_id)

    async def _async_get_last_stats(
        self, statistic_id: str
    ) -> tuple[datetime | None, float]:
        """Dernier jour importé et somme cumulée courante pour un statistic_id."""
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
        """Somme cumulée de la dernière statistique strictement avant first_day."""
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
