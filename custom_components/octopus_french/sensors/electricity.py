"""Electricity sensor entities for Octopus Energy France."""

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

from ..const import DOMAIN, LEDGER_TYPE_ELECTRICITY
from ..coordinator import OctopusFrenchDataUpdateCoordinator
from .descriptions import OctopusIndexSensorDescription

_LOGGER = logging.getLogger(__name__)


class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity data with statistics support."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: SensorEntityDescription,
    ) -> None:
        """Initialize the electricity sensor."""
        super().__init__(coordinator)

        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})
        self._attr_suggested_display_precision = (
            sensor_config.suggested_display_precision
        )
        self._attr_entity_category = sensor_config.entity_category

        self._current_month: str | None = None
        self._last_imported_date: str | None = None
        self._statistics_imported = False

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        if self._sensor_config.key.startswith(("energy_", "cost_")) and self.entity_id:
            self.hass.async_create_task(self._async_import_statistics())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (
            self.entity_id
            and self._sensor_config.key.startswith(("energy_", "cost_"))
            and not self._statistics_imported
        ):
            self.hass.async_create_task(self._async_import_statistics())

        super()._handle_coordinator_update()

    async def _async_import_statistics(self) -> None:
        """Import statistics with correct dates from readings."""
        key = self._sensor_config.key
        readings = self.coordinator.data.get("electricity", {}).get("readings", [])

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

        statistic_id = f"{DOMAIN}:{self._prm_id}_{key}"

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

        consumption_mapping = {
            "energy_base": "BASE",
            "energy_peak_hours": "HEURES_PLEINES",
            "energy_off_peak_hours": "HEURES_CREUSES",
        }

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting readings: %s", e)
            return

        # Initialize cumulative_sum from the last stored statistic so the sum is
        # monotonically increasing across all time, not just the current month.
        # Also restore _last_imported_date from the DB after a restart so already-stored
        # readings are skipped correctly without double-counting.
        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, False, {"sum", "start"}
            )
            if last_stats and statistic_id in last_stats and last_stats[statistic_id]:
                last_entry = last_stats[statistic_id][0]
                cumulative_sum = float(last_entry.get("sum") or 0.0)
                if not self._last_imported_date:
                    # start is a float Unix timestamp — convert to UTC ISO string
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

                if not statistics:
                    _LOGGER.debug(
                        "First reading - original: %s, normalized: %s",
                        reading_date,
                        date_normalized.isoformat(),
                    )

                # Skip readings already stored: cumulative_sum from DB already includes
                # them, so we must not re-add them to avoid double-counting.
                # Both _last_imported_date and reading_date are ISO strings → comparable.
                if (
                    self._last_imported_date
                    and reading_date <= self._last_imported_date
                ):
                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing date %s: %s", reading_date, e)
                continue

            stat_list = reading.get("metaData", {}).get("statistics", [])
            reading_value = 0.0

            for stat in stat_list:
                label = stat.get("label", "")

                if key.startswith("energy_"):
                    expected_label = consumption_mapping.get(key)
                    value = stat.get("value")

                    if value is not None and label == expected_label:
                        reading_value = float(value)

                elif key in ("cost_base", "cost_peak_hours", "cost_off_peak_hours"):
                    # API has no cost labels → derive cost from consumption × tariff.
                    consumption_label_map = {
                        "cost_base": "BASE",
                        "cost_peak_hours": "HEURES_PLEINES",
                        "cost_off_peak_hours": "HEURES_CREUSES",
                    }
                    if label == consumption_label_map[key]:
                        value = stat.get("value")
                        tariff_rate = self._get_tariff_rate()
                        if value is not None and tariff_rate:
                            reading_value = float(value) * tariff_rate

            if reading_value > 0:
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

        unit_class = "energy" if key.startswith("energy_") else None

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Octopus Energy {key}",
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
            if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                tariffs = agreement.get("tariffs", {})
                subscription = tariffs.get("subscription", {})

                if subscription:
                    monthly_ttc = subscription.get("monthly_ttc_eur")
                    if monthly_ttc is not None:
                        return round(monthly_ttc, 2)

        _LOGGER.debug(
            "No subscription found in agreements for PRM %s, using fallback calculation",
            self._prm_id,
        )
        return self._calculate_monthly_subscription_fallback()

    def _calculate_monthly_subscription_fallback(self) -> float:
        """Fallback: Calculate monthly subscription from daily readings."""
        readings = self.coordinator.data.get("electricity", {}).get("readings", [])

        if not readings:
            return 0.0

        try:
            latest_reading = max(readings, key=lambda x: x.get("startAt", ""))
        except (ValueError, TypeError, KeyError) as e:
            _LOGGER.warning("Error getting latest reading: %s", e)
            return 0.0

        statistics = latest_reading.get("metaData", {}).get("statistics", [])

        for stat in statistics:
            if stat.get("label") == "ABONNEMENT":
                cost_data = stat.get("costInclTax")
                if cost_data and "estimatedAmount" in cost_data:
                    daily_cost_eur = float(cost_data.get("estimatedAmount")) / 100
                    return round(daily_cost_eur * 30, 2)

        return 0.0

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

    def _calculate_monthly_total(self) -> float:
        """Calculate monthly total."""
        key = self._sensor_config.key
        readings = self.coordinator.data.get("electricity", {}).get("readings", [])

        if not readings:
            return 0.0

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting readings: %s", e)
            sorted_readings = readings

        current_month = self._get_current_month()
        total = 0.0

        consumption_mapping = {
            "energy_base": "BASE",
            "energy_peak_hours": "HEURES_PLEINES",
            "energy_off_peak_hours": "HEURES_CREUSES",
        }

        # API does NOT return cost labels → cost must be derived from consumption × tariff.
        cost_to_consumption_label = {
            "cost_base": "BASE",
            "cost_peak_hours": "HEURES_PLEINES",
            "cost_off_peak_hours": "HEURES_CREUSES",
        }

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
                _LOGGER.warning("Error parsing date %s: %s", reading_date, e)
                continue

            statistics = reading.get("metaData", {}).get("statistics", [])

            for stat in statistics:
                label = stat.get("label", "")

                if key.startswith("energy_"):
                    expected_label = consumption_mapping.get(key)
                    value = stat.get("value")

                    if value is not None and label == expected_label:
                        total += float(value)

                elif key in cost_to_consumption_label:
                    # Accumulate kWh consumption; multiply by tariff after the loop.
                    if label == cost_to_consumption_label[key]:
                        value = stat.get("value")
                        if value is not None:
                            total += float(value)

        # For cost sensors: total holds kWh → convert to € using tariff.
        if key in cost_to_consumption_label:
            tariff_rate = self._get_tariff_rate()
            if tariff_rate and total > 0.0:
                total = total * tariff_rate
            else:
                return 0.0

        return round(total, 2)

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        key = self._sensor_config.key

        if key == "contract":
            return self._get_contract_type()

        if key == "subscribed_power":
            return self._get_subscribed_power()

        if key == "subscription":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_subscription()

        if key.startswith("rate_"):
            return self._get_tariff_rate()

        if key.startswith(("energy_", "cost_")):
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_total()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config.key

        if key == "contract":
            meter = self._get_meter_data()
            if not meter:
                return {}

            ledgers = self.coordinator.data.get("ledgers", {})
            electricity_ledger = ledgers.get(LEDGER_TYPE_ELECTRICITY, {})

            return {
                "ledger_id": electricity_ledger.get("number"),
                "prm_id": meter.get("id"),
                "agreement": meter.get("providerCalendar", {}).get("id"),
                "distributor_status": meter.get("distributorStatus"),
                "meter_kind": meter.get("meterKind"),
                "subscribed_max_power": f"{meter.get('subscribedMaxPower')} kVA",
                "is_teleoperable": meter.get("isTeleoperable"),
                "off_peak_label": meter.get("offPeakLabel"),
                "powered_status": meter.get("poweredStatus"),
            }

        if key == "subscription":
            agreements = self.coordinator.data.get("agreements", [])
            agreement_data = None

            for agreement in agreements:
                if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                    agreement_data = agreement
                    break

            attributes: dict[str, Any] = {
                "current_month": self._current_month,
            }

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
                readings = self.coordinator.data.get("electricity", {}).get(
                    "readings", []
                )
                days_with_subscription = 0

                for reading in readings:
                    reading_date = reading.get("startAt")
                    if reading_date:
                        try:
                            date_obj = datetime.fromisoformat(reading_date)
                            if date_obj.strftime("%Y-%m") == self._current_month:
                                statistics = reading.get("metaData", {}).get(
                                    "statistics", []
                                )
                                if any(
                                    s.get("label") == "ABONNEMENT" for s in statistics
                                ):
                                    days_with_subscription += 1
                        except (ValueError, TypeError, AttributeError) as e:
                            _LOGGER.warning(
                                "Error parsing date %s: %s", reading_date, e
                            )

                attributes.update(
                    {
                        "days_counted": days_with_subscription,
                        "readings_count": len(readings),
                        "calculation_method": "Cumul journalier (fallback)",
                    }
                )

            return attributes

        if key.startswith(("energy_", "cost_")):
            readings = self.coordinator.data.get("electricity", {}).get("readings", [])

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / mois",
                "last_imported_date": self._last_imported_date,
            }

        if key.startswith("rate_"):
            agreements = self.coordinator.data.get("agreements", [])

            for agreement in agreements:
                if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                    tariffs = agreement.get("tariffs", {})
                    consumption = tariffs.get("consumption", {})

                    attributes: dict[str, Any] = {
                        "contract_number": agreement.get("contract_number"),
                        "product_name": agreement.get("product", {}).get(
                            "display_name"
                        ),
                        "valid_from": agreement.get("valid_from"),
                    }

                    if key == "rate_base":
                        base_rate = consumption.get("base")
                        if base_rate:
                            attributes["price_ht_eur_kwh"] = base_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = base_rate.get("price_ttc")

                    elif key == "rate_peak_hours":
                        hp_rate = consumption.get("heures_pleines")
                        if hp_rate:
                            attributes["price_ht_eur_kwh"] = hp_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = hp_rate.get("price_ttc")

                    elif key == "rate_off_peak_hours":
                        hc_rate = consumption.get("heures_creuses")
                        if hc_rate:
                            attributes["price_ht_eur_kwh"] = hc_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = hc_rate.get("price_ttc")

                    return attributes

            return {"status": "No agreement found"}

        return {}

    def _get_tariff_rate(self) -> float | None:
        """Get the tariff rate from agreements."""
        key = self._sensor_config.key

        agreements = self.coordinator.data.get("agreements", [])

        for agreement in agreements:
            if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                tariffs = agreement.get("tariffs", {})
                consumption = tariffs.get("consumption", {})

                if key in ("rate_base", "cost_base"):
                    base_rate = consumption.get("base")
                    if base_rate:
                        return base_rate.get("price_ttc")

                elif key in ("rate_peak_hours", "cost_peak_hours"):
                    hp_rate = consumption.get("heures_pleines")
                    if hp_rate:
                        return hp_rate.get("price_ttc")

                elif key in ("rate_off_peak_hours", "cost_off_peak_hours"):
                    hc_rate = consumption.get("heures_creuses")
                    if hc_rate:
                        return hc_rate.get("price_ttc")

        _LOGGER.debug(
            "No tariff rate found in agreements for PRM %s, key %s", self._prm_id, key
        )
        return None

    def _get_meter_data(self) -> dict | None:
        """Get meter data for this PRM ID."""
        supply_points = self.coordinator.data.get("supply_points", {})
        elec_points = supply_points.get("electricity", [])
        return next((m for m in elec_points if m.get("id") == self._prm_id), None)

    def _get_subscribed_power(self) -> float | None:
        """Get the subscribed power in kVA."""
        meter = self._get_meter_data()
        if not meter:
            return None
        value = meter.get("subscribedMaxPower")
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    def _get_contract_type(self) -> str:
        """Get a human-readable contract status."""
        meter = self._get_meter_data()
        if not meter:
            return "Inconnu"
        return meter.get("providerCalendar", {}).get("id", "Inconnu")


class OctopusLatestReadingSensor(CoordinatorEntity, SensorEntity):
    """Sensor for the latest daily electricity reading."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: SensorEntityDescription,
    ) -> None:
        """Initialize the latest reading sensor."""
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_entity_category = sensor_config.entity_category
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})

        if sensor_config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = sensor_config.suggested_display_precision

    @property
    def native_value(self) -> float | None:
        """Return the latest reading value."""
        electricity_data = self.coordinator.data.get("electricity", {})
        readings = electricity_data.get("readings", [])

        if not readings:
            return None

        reading = readings[-1]
        value = reading.get("value")
        return float(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for the latest reading."""
        electricity_data = self.coordinator.data.get("electricity", {})
        readings = electricity_data.get("readings", [])

        if not readings:
            return {}

        reading = readings[-1]
        statistics = reading.get("metaData", {}).get("statistics", [])

        attributes = {"date_releve": reading.get("startAt")}

        for stat in statistics:
            label = stat.get("label")
            value = stat.get("value")
            cost_incl_tax = stat.get("costInclTax")

            if label == "HEURES_BASE":
                attributes["heures_base"] = float(value) if value else None
            elif label == "HEURES_PLEINES":
                attributes["heures_pleines_kwh"] = float(value) if value else None
            elif label == "HEURES_CREUSES":
                attributes["heures_creuses_kwh"] = float(value) if value else None
            elif label == "ABONNEMENT" and cost_incl_tax:
                attributes["cout_abonnement_euro"] = (
                    float(cost_incl_tax.get("estimatedAmount")) / 100
                    if cost_incl_tax.get("estimatedAmount")
                    else None
                )

        # API provides no costInclTax for consumption labels → compute from consumption × tariff.
        base_kwh = attributes.get("heures_base")
        hp_kwh = attributes.get("heures_pleines_kwh")
        hc_kwh = attributes.get("heures_creuses_kwh")
        if base_kwh is not None or hp_kwh is not None or hc_kwh is not None:
            agreements = self.coordinator.data.get("agreements", [])
            for agreement in agreements:
                if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                    consumption = agreement.get("tariffs", {}).get("consumption", {})
                    if base_kwh is not None:
                        base_rate = consumption.get("base")
                        if base_rate:
                            attributes["cout_base_euro"] = round(
                                base_kwh * base_rate.get("price_ttc", 0), 4
                            )
                    hp_rate = consumption.get("heures_pleines")
                    hc_rate = consumption.get("heures_creuses")
                    if hp_kwh is not None and hp_rate:
                        attributes["cout_heures_pleines_euro"] = round(
                            hp_kwh * hp_rate.get("price_ttc", 0), 4
                        )
                    if hc_kwh is not None and hc_rate:
                        attributes["cout_heures_creuses_euro"] = round(
                            hc_kwh * hc_rate.get("price_ttc", 0), 4
                        )
                    break

        return attributes


class OctopusElectricityIndexSensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity meter index (Linky counter value)."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: OctopusIndexSensorDescription,
    ) -> None:
        """Initialize the index sensor."""
        super().__init__(coordinator)

        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._index_type = sensor_config.index_type
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_entity_category = sensor_config.entity_category
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})

        if sensor_config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = sensor_config.suggested_display_precision

    @property
    def native_value(self) -> float | None:
        """Return the index end value."""
        index_data = self.coordinator.data.get("electricity", {}).get("index")

        if not index_data:
            return None

        type_data = index_data.get(self._index_type, {})
        return type_data.get("index_end")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        index_data = self.coordinator.data.get("electricity", {}).get("index")

        if not index_data:
            return {}

        type_data = index_data.get(self._index_type, {})

        return {
            "prm_id": self._prm_id,
            "index_start": type_data.get("index_start"),
            "consumption": type_data.get("consumption"),
            "period_start": index_data.get("period_start"),
            "period_end": index_data.get("period_end"),
            "index_reliability": type_data.get("index_reliability"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        index_data = self.coordinator.data.get("electricity", {}).get("index")
        if not index_data:
            return False
        return self._index_type in index_data
