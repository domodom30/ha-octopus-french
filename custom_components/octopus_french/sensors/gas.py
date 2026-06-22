"""Gas sensor entity for Octopus Energy France."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LEDGER_TYPE_GAS
from ..coordinator import OctopusFrenchDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Sensor for gas data."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        pce_ref: str,
        sensor_config: SensorEntityDescription,
    ) -> None:
        """Initialize the gas sensor."""
        super().__init__(coordinator)

        self._pce_ref = pce_ref
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{pce_ref}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, pce_ref)})

        if sensor_config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = sensor_config.suggested_display_precision
        self._attr_entity_category = sensor_config.entity_category

        self._current_month: str | None = None
        self._last_imported_date: str | None = None
        self._statistics_imported = False

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        key = self._sensor_config.key
        if key in ["consumption", "cost"] and self.entity_id:
            self.hass.async_create_task(self._async_import_statistics())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        key = self._sensor_config.key
        if (
            self.entity_id
            and key in ["consumption", "cost"]
            and self._statistics_imported
        ):
            self.hass.async_create_task(self._async_import_statistics())

        super()._handle_coordinator_update()

    async def _async_import_statistics(self) -> None:
        """Import statistics with correct dates from gas readings."""
        key = self._sensor_config.key

        if key not in ["consumption", "cost"]:
            return

        readings = self.coordinator.data.get("gas", [])

        if not readings:
            return

        if not self.entity_id:
            _LOGGER.warning(
                "entity_id not available for %s, skipping statistics import",
                self._attr_unique_id,
            )
            return

        if not self.entity_id.startswith("sensor."):
            _LOGGER.error(
                "Invalid entity_id format '%s' for sensor %s, cannot import statistics",
                self.entity_id,
                self._attr_unique_id,
            )
            return

        statistic_id = f"{DOMAIN}:{self._pce_ref}_{key}"

        current_month = self._get_current_month()
        if (
            self._statistics_imported
            and self._last_imported_date
            and current_month != self._current_month
        ):
            _LOGGER.info(
                "New month detected (%s), forcing statistics re-import for %s",
                current_month,
                statistic_id,
            )
            self._statistics_imported = False
            self._last_imported_date = None

        _LOGGER.debug(
            "Starting statistics import for entity_id: %s (statistic_id: %s)",
            self.entity_id,
            statistic_id,
        )

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting gas readings: %s", e)
            return

        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, False, {"sum", "start"}
            )
            if last_stats and statistic_id in last_stats and last_stats[statistic_id]:
                last_entry = last_stats[statistic_id][0]
                cumulative_sum = float(last_entry.get("sum") or 0.0)
                if not self._last_imported_date:
                    last_start = last_entry.get("start")
                    if last_start is not None:
                        self._last_imported_date = datetime.fromtimestamp(
                            float(last_start), tz=dt_util.UTC
                        ).isoformat()
            else:
                cumulative_sum = 0.0
        except (OSError, ValueError, TypeError):
            _LOGGER.debug(
                "Could not fetch last statistics for %s, starting sum at 0",
                statistic_id,
            )
            cumulative_sum = 0.0

        statistics = []
        first_reading_logged = False

        for reading in sorted_readings:
            reading_date = reading.get("startAt")

            if not reading_date:
                continue

            try:
                date_obj = datetime.fromisoformat(reading_date)
                date_local = date_obj.astimezone(dt_util.DEFAULT_TIME_ZONE)
                date_normalized = date_local.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                if not first_reading_logged:
                    _LOGGER.debug(
                        "First reading - original: %s, normalized: %s",
                        reading_date,
                        date_normalized.isoformat(),
                    )
                    first_reading_logged = True

                if (
                    self._last_imported_date
                    and reading_date <= self._last_imported_date
                ):
                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing gas date %s: %s", reading_date, e)
                continue

            consumption = float(reading.get("value", 0))

            if consumption > 0:
                if key == "cost":
                    tariff_rate = self._get_tariff_rate()
                    if tariff_rate:
                        reading_value = consumption * tariff_rate
                    else:
                        _LOGGER.warning(
                            "No tariff rate found for gas meter %s, cost will be 0",
                            self._pce_ref,
                        )
                        reading_value = 0.0
                else:
                    reading_value = consumption

                cumulative_sum += reading_value

                stat_data = StatisticData(
                    start=date_normalized,
                    state=reading_value,
                    sum=cumulative_sum,
                )
                statistics.append(stat_data)
                self._last_imported_date = reading_date

        if not statistics:
            _LOGGER.debug("No new statistics to import for %s", self.entity_id)
            return

        _LOGGER.debug(
            "Preparing to import %d statistics for statistic_id: %s",
            len(statistics),
            statistic_id,
        )

        unit_class = "energy" if key == "consumption" else None
        sensor_name = "Gas Consumption" if key == "consumption" else "Gas Cost"

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Octopus Energy {sensor_name} {self._pce_ref}",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class=unit_class,
            unit_of_measurement=self._attr_native_unit_of_measurement,
        )

        try:
            async_add_external_statistics(self.hass, metadata, statistics)

            self._statistics_imported = True
            _LOGGER.info(
                "Successfully imported %d statistics for %s (last date: %s)",
                len(statistics),
                statistic_id,
                self._last_imported_date,
            )
        except Exception:
            _LOGGER.exception("Failed to import statistics for %s", statistic_id)

    def _calculate_monthly_subscription(self) -> float:
        """Get the monthly subscription cost from agreements."""
        agreements = self.coordinator.data.get("agreements", [])

        for agreement in agreements:
            if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                tariffs = agreement.get("tariffs", {})
                subscription = tariffs.get("subscription", {})

                if subscription:
                    monthly_ttc = subscription.get("monthly_ttc_eur")
                    if monthly_ttc is not None:
                        return round(monthly_ttc, 2)

        _LOGGER.debug("No subscription found in agreements for PCE %s", self._pce_ref)
        return 0.0

    def _calculate_monthly_total(self) -> float:
        """Calculate total for current month from all readings."""
        readings = self.coordinator.data.get("gas", [])

        if not readings:
            return 0.0

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting gas readings: %s", e)
            sorted_readings = readings

        current_month = self._get_current_month()
        total = 0.0

        for reading in sorted_readings:
            reading_date = reading.get("startAt")

            if not reading_date:
                continue

            try:
                date_obj = datetime.fromisoformat(reading_date)
                reading_month = date_obj.strftime("%Y-%m")

                if reading_month != current_month:
                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing gas date %s: %s", reading_date, e)
                continue

            total += float(reading.get("value", 0))

        return round(total, 2)

    def _calculate_monthly_cost(self) -> float:
        """Calculate monthly cost from consumption and tariff."""
        consumption = self._calculate_monthly_total()

        if consumption == 0:
            return 0.0

        tariff_rate = self._get_tariff_rate()

        if tariff_rate is None or tariff_rate == 0:
            _LOGGER.warning(
                "No tariff rate found for gas meter %s, cannot calculate cost",
                self._pce_ref,
            )
            return 0.0

        cost = consumption * tariff_rate

        return round(cost, 2)

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        key = self._sensor_config.key

        if key == "contract":
            return self._get_contract_status()

        if key == "subscription":
            return self._calculate_monthly_subscription()

        if key == "rate_base":
            return self._get_tariff_rate()

        if key == "consumption":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_total()

        if key == "cost":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_cost()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config.key

        if key == "contract":
            supply_points = self.coordinator.data.get("supply_points", {})
            gas_points = supply_points.get("gas", [])
            meter = next((m for m in gas_points if m.get("id") == self._pce_ref), None)

            if not meter:
                return {}

            ledger = self.coordinator.data.get("ledgers", {}).get(LEDGER_TYPE_GAS, {})

            return {
                "ledger_id": ledger.get("number"),
                "pce_ref": meter.get("id"),
                "gas_nature": meter.get("gasNature"),
                "annual_consumption": f"{meter.get('annualConsumption')} kWh",
                "is_smart_meter": meter.get("isSmartMeter"),
                "powered_status": meter.get("poweredStatus"),
            }

        if key == "subscription":
            agreements = self.coordinator.data.get("agreements", [])
            agreement_data = None

            for agreement in agreements:
                if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                    agreement_data = agreement
                    break

            attributes: dict[str, Any] = {}

            if agreement_data:
                tariffs = agreement_data.get("tariffs", {})
                subscription = tariffs.get("subscription", {})

                attributes.update(
                    {
                        "contract_number": agreement_data.get("contract_number"),
                        "product_name": agreement_data.get("product", {}).get(
                            "display_name"
                        ),
                        "annual_ht_eur": subscription.get("annual_ht_eur"),
                        "annual_ttc_eur": subscription.get("annual_ttc_eur"),
                        "monthly_ttc_eur": subscription.get("monthly_ttc_eur"),
                        "billing_frequency_months": agreement_data.get(
                            "billing_frequency_months"
                        ),
                        "valid_from": agreement_data.get("valid_from"),
                        "calculation_method": "From agreement",
                    }
                )

                next_payment = agreement_data.get("next_payment")
                if next_payment:
                    attributes["next_payment_amount"] = (
                        next_payment.get("amount") / 100
                        if next_payment.get("amount")
                        else None
                    )
                    attributes["next_payment_date"] = next_payment.get("date")
            else:
                attributes.update(
                    {
                        "calculation_method": "No agreement found",
                    }
                )

            return attributes

        if key == "consumption":
            readings = self.coordinator.data.get("gas", [])

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / mois",
                "last_imported_date": self._last_imported_date,
            }

        if key == "cost":
            readings = self.coordinator.data.get("gas", [])
            tariff_rate = self._get_tariff_rate()

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / mois",
                "last_imported_date": self._last_imported_date,
                "tariff_eur_kwh": tariff_rate,
            }

        if key == "rate_base":
            agreements = self.coordinator.data.get("agreements", [])

            for agreement in agreements:
                if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                    tariffs = agreement.get("tariffs", {})
                    consumption = tariffs.get("consumption", {})
                    base_rate = consumption.get("base")

                    if base_rate:
                        return {
                            "contract_number": agreement.get("contract_number"),
                            "product_name": agreement.get("product", {}).get(
                                "display_name"
                            ),
                            "valid_from": agreement.get("valid_from"),
                            "price_ht_eur_kwh": base_rate.get("price_ht"),
                            "price_ttc_eur_kwh": base_rate.get("price_ttc"),
                        }

            return {"status": "No agreement found"}

        return {}

    def _get_tariff_rate(self) -> float | None:
        """Get the tariff rate from agreements."""
        agreements = self.coordinator.data.get("agreements", [])

        for agreement in agreements:
            if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                tariffs = agreement.get("tariffs", {})
                consumption = tariffs.get("consumption", {})

                base_rate = consumption.get("base")
                if base_rate:
                    return base_rate.get("price_ttc")

        _LOGGER.debug("No tariff rate found in agreements for PCE %s", self._pce_ref)
        return None

    def _get_contract_status(self) -> str:
        """Get a human-readable contract status."""
        supply_points = self.coordinator.data.get("supply_points", {})
        gas_points = supply_points.get("gas", [])
        meter = next((m for m in gas_points if m.get("id") == self._pce_ref), None)

        if not meter:
            return "Inconnu"

        powered = meter.get("poweredStatus", "")
        powered_map = {"non_coupe": "En service", "coupe": "Coupé"}
        return powered_map.get(powered, "Inconnu")
