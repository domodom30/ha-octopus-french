"""Sensor platform for Octopus Energy France - CORRECTED VERSION."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    async_add_external_statistics,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LEDGER_TYPE_ELECTRICITY, LEDGER_TYPE_GAS
from .coordinator import OctopusFrenchDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

ELECTRICITY_SENSORS = [
    {
        "key": "conso_base",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "conso_hp",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "conso_hc",
        "icon": "mdi:lightning-bolt-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "cout_base",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "cout_hp",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "cout_hc",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "contract",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
    },
    {
        "key": "subscription",
        "icon": "mdi:calendar-month",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "tarif_base",
        "icon": "mdi:cash",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/kWh",
        "precision": 4,
    },
    {
        "key": "tarif_hp",
        "icon": "mdi:cash-plus",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/kWh",
        "precision": 4,
    },
    {
        "key": "tarif_hc",
        "icon": "mdi:cash-minus",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/kWh",
        "precision": 4,
    },
]

LATEST_READING_SENSOR = {
    "key": "latest_reading",
    "icon": "mdi:calendar-clock",
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": SensorStateClass.TOTAL,
    "entity_category": EntityCategory.DIAGNOSTIC,
    "unit": UnitOfEnergy.KILO_WATT_HOUR,
    "precision": 2,
}

ELECTRICITY_INDEX_SENSORS = [
    {
        "key": "index_base",
        "index_type": "base",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
    },
    {
        "key": "index_hp",
        "index_type": "hp",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
    },
    {
        "key": "index_hc",
        "index_type": "hc",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
    },
]

GAS_SENSORS = [
    {
        "key": "consumption",
        "icon": "mdi:fire",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": None,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "cost",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "contract",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
    },
    {
        "key": "subscription",
        "icon": "mdi:calendar-month",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "tarif_base",
        "icon": "mdi:cash",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/kWh",
        "precision": 4,
    },
]

LEDGER_SENSORS = [
    {
        "key": "pot_ledger",
        "ledger_type": "POT_LEDGER",
        "icon": "mdi:piggy-bank",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "electricity_bill",
        "ledger_type": "FRA_ELECTRICITY_LEDGER",
        "icon": "mdi:file-document",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "gas_bill",
        "ledger_type": "FRA_GAS_LEDGER",
        "icon": "mdi:file-document",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Energy France sensors."""
    coordinator: OctopusFrenchDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    account_number = hass.data[DOMAIN][entry.entry_id]["account_number"]

    await coordinator.async_config_entry_first_refresh()

    entities = []
    supply_points = coordinator.data.get("supply_points", {})
    ledgers = coordinator.data.get("ledgers", {})

    if ledgers:
        entities.extend(
            OctopusLedgerSensor(coordinator, account_number, sensor_config)
            for sensor_config in LEDGER_SENSORS
            if sensor_config["ledger_type"] in ledgers
        )

    for elec_meter in supply_points.get("electricity", []):
        if (
            elec_meter.get("distributorStatus") == "RESIL"
            and elec_meter.get("poweredStatus") == "LIMI"
        ):
            continue

        prm_id = elec_meter.get("id")
        tariff_type = _detect_tariff_type_for_meter(coordinator.data, prm_id)

        for sensor_config in ELECTRICITY_SENSORS:
            sensor_key = sensor_config["key"]

            if (
                sensor_key in {"contract", "subscription"}
                or (
                    tariff_type == "BASE"
                    and sensor_key in ["conso_base", "cout_base", "tarif_base"]
                )
                or (
                    tariff_type == "HPHC"
                    and sensor_key
                    in [
                        "conso_hp",
                        "conso_hc",
                        "cout_hp",
                        "cout_hc",
                        "tarif_hp",
                        "tarif_hc",
                    ]
                )
            ):
                entities.append(
                    OctopusElectricitySensor(coordinator, prm_id, sensor_config)
                )

        entities.append(
            OctopusLatestReadingSensor(coordinator, prm_id, LATEST_READING_SENSOR)
        )

        index_data = coordinator.data.get("electricity", {}).get("index")
        if index_data:
            index_tariff_type = index_data.get("tariff_type")

            for index_config in ELECTRICITY_INDEX_SENSORS:
                index_type = index_config.get("index_type")

                if not index_type:
                    continue

                if (index_tariff_type == "BASE" and index_type == "base") or (
                    index_tariff_type == "HPHC" and index_type in ["hp", "hc"]
                ):
                    entities.append(
                        OctopusElectricityIndexSensor(coordinator, prm_id, index_config)
                    )

    entities.extend(
        OctopusGasSensor(coordinator, gas_meter.get("id"), sensor_config)
        for gas_meter in supply_points.get("gas", [])
        for sensor_config in GAS_SENSORS
    )

    async_add_entities(entities)


def _detect_tariff_type_for_meter(data: dict, prm_id: str) -> str:
    """DÃ©tecte le type de tarif pour un compteur spÃ©cifique."""
    try:
        electricity_readings = data.get("electricity", {}).get("readings", [])
        if not electricity_readings:
            return "UNKNOWN"

        latest_reading = electricity_readings[-1]
        statistics = latest_reading.get("metaData", {}).get("statistics", [])
        if not statistics:
            return "UNKNOWN"

        labels = {stat.get("label", "") for stat in statistics}

        if "CONSO_BASE" in labels:
            return "BASE"
        if "CONSO_HEURES_PLEINES" in labels and "CONSO_HEURES_CREUSES" in labels:
            return "HPHC"

    except (KeyError, IndexError, TypeError) as e:
        _LOGGER.error("Erreur dÃ©tection tarif %s: %s", prm_id, e)
        return "UNKNOWN"
    return "UNKNOWN"


class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity data with statistics support."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the electricity sensor."""
        super().__init__(coordinator)

        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

        self._current_month: str | None = None
        self._last_imported_date: str | None = None
        self._statistics_imported = False

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        if (
            self._sensor_config["key"].startswith(("conso_", "cout_"))
            and self.entity_id
        ):
            self.hass.async_create_task(self._async_import_statistics())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (
            self.entity_id
            and self._sensor_config["key"].startswith(("conso_", "cout_"))
            and self._statistics_imported
        ):
            self.hass.async_create_task(self._async_import_statistics())

        super()._handle_coordinator_update()

    async def _async_import_statistics(self) -> None:
        """Import statistics with correct dates from readings."""
        key = self._sensor_config["key"]
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
            "conso_base": "BASE",
            "conso_hp": "HEURES_PLEINES",
            "conso_hc": "HEURES_CREUSES",
        }

        cost_mapping = {
            "cout_base": "CONSO_BASE",
            "cout_hp": "CONSO_HEURES_PLEINES",
            "cout_hc": "CONSO_HEURES_CREUSES",
        }

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting readings: %s", e)
            return

        statistics = []
        cumulative_sum = 0.0

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

                if (
                    self._statistics_imported
                    and self._last_imported_date
                    and reading_date <= self._last_imported_date
                ):
                    stat_list = reading.get("metaData", {}).get("statistics", [])
                    reading_value = 0.0

                    for stat in stat_list:
                        label = stat.get("label", "")

                        if key.startswith("conso_"):
                            expected_label = consumption_mapping.get(key)
                            value = stat.get("value")
                            if value is not None and label == expected_label:
                                reading_value = float(value)

                        elif key.startswith("cout_"):
                            expected_label = cost_mapping.get(key)
                            cost_data = stat.get("costInclTax")
                            if (
                                cost_data
                                and "estimatedAmount" in cost_data
                                and label == expected_label
                            ):
                                reading_value = (
                                    float(cost_data.get("estimatedAmount")) / 100
                                )

                    if reading_value > 0:
                        cumulative_sum += reading_value

                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing date %s: %s", reading_date, e)
                continue

            stat_list = reading.get("metaData", {}).get("statistics", [])
            reading_value = 0.0

            for stat in stat_list:
                label = stat.get("label", "")

                if key.startswith("conso_"):
                    expected_label = consumption_mapping.get(key)
                    value = stat.get("value")

                    if value is not None and label == expected_label:
                        reading_value = float(value)

                elif key.startswith("cout_"):
                    expected_label = cost_mapping.get(key)
                    cost_data = stat.get("costInclTax")

                    if (
                        cost_data
                        and "estimatedAmount" in cost_data
                        and label == expected_label
                    ):
                        reading_value = float(cost_data.get("estimatedAmount")) / 100

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

        unit_class = "energy" if key.startswith("conso_") else None

        metadata = StatisticMetaData(
            has_mean=False,
            mean_type=StatisticMeanType.ARITHMETIC,
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
        key = self._sensor_config["key"]
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
            "conso_base": "BASE",
            "conso_hp": "HEURES_PLEINES",
            "conso_hc": "HEURES_CREUSES",
        }

        cost_mapping = {
            "cout_base": "CONSO_BASE",
            "cout_hp": "CONSO_HEURES_PLEINES",
            "cout_hc": "CONSO_HEURES_CREUSES",
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

                if key.startswith("conso_"):
                    expected_label = consumption_mapping.get(key)
                    value = stat.get("value")

                    if value is not None and label == expected_label:
                        total += float(value)

                elif key.startswith("cout_"):
                    expected_label = cost_mapping.get(key)
                    cost_data = stat.get("costInclTax")

                    if (
                        cost_data
                        and "estimatedAmount" in cost_data
                        and label == expected_label
                    ):
                        total += float(cost_data.get("estimatedAmount")) / 100

        return round(total, 2)

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        key = self._sensor_config["key"]

        if key == "contract":
            return self._get_contract_type()

        if key == "subscription":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_subscription()

        if key.startswith("tarif_"):
            return self._get_tariff_rate()

        if key.startswith(("conso_", "cout_")):
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_total()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config["key"]

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
                        except (ValueError, TypeError, AttributeError):
                            pass

                attributes.update(
                    {
                        "days_counted": days_with_subscription,
                        "readings_count": len(readings),
                        "calculation_method": "Cumul journalier (fallback)",
                    }
                )

            return attributes

        if key.startswith(("conso_", "cout_")):
            readings = self.coordinator.data.get("electricity", {}).get("readings", [])

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "CumulÃ©e / mois",
                "last_imported_date": self._last_imported_date,
            }

        if key.startswith("tarif_"):
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

                    if key == "tarif_base":
                        base_rate = consumption.get("base")
                        if base_rate:
                            attributes["price_ht_eur_kwh"] = base_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = base_rate.get("price_ttc")

                    elif key == "tarif_hp":
                        hp_rate = consumption.get("heures_pleines")
                        if hp_rate:
                            attributes["price_ht_eur_kwh"] = hp_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = hp_rate.get("price_ttc")

                    elif key == "tarif_hc":
                        hc_rate = consumption.get("heures_creuses")
                        if hc_rate:
                            attributes["price_ht_eur_kwh"] = hc_rate.get("price_ht")
                            attributes["price_ttc_eur_kwh"] = hc_rate.get("price_ttc")

                    return attributes

            return {"status": "No agreement found"}

        return {}

    def _get_tariff_rate(self) -> float | None:
        """Get the tariff rate from agreements."""
        key = self._sensor_config["key"]

        agreements = self.coordinator.data.get("agreements", [])

        for agreement in agreements:
            if agreement.get("prm") == self._prm_id and agreement.get("is_active"):
                tariffs = agreement.get("tariffs", {})
                consumption = tariffs.get("consumption", {})

                if key == "tarif_base":
                    base_rate = consumption.get("base")
                    if base_rate:
                        return base_rate.get("price_ttc")

                elif key == "tarif_hp":
                    hp_rate = consumption.get("heures_pleines")
                    if hp_rate:
                        return hp_rate.get("price_ttc")

                elif key == "tarif_hc":
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
        sensor_config: dict,
    ) -> None:
        """Initialize the latest reading sensor."""
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_entity_category = sensor_config.get("entity_category")
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

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
            elif label == "CONSO_BASE" and cost_incl_tax:
                attributes["cout_base_euro"] = (
                    float(cost_incl_tax.get("estimatedAmount")) / 100
                    if cost_incl_tax.get("estimatedAmount")
                    else None
                )
            elif label == "CONSO_HEURES_PLEINES" and cost_incl_tax:
                attributes["cout_heures_pleines_euro"] = (
                    float(cost_incl_tax.get("estimatedAmount")) / 100
                    if cost_incl_tax.get("estimatedAmount")
                    else None
                )
            elif label == "CONSO_HEURES_CREUSES" and cost_incl_tax:
                attributes["cout_heures_creuses_euro"] = (
                    float(cost_incl_tax.get("estimatedAmount")) / 100
                    if cost_incl_tax.get("estimatedAmount")
                    else None
                )
            elif label == "ABONNEMENT" and cost_incl_tax:
                attributes["cout_abonnement_euro"] = (
                    float(cost_incl_tax.get("estimatedAmount")) / 100
                    if cost_incl_tax.get("estimatedAmount")
                    else None
                )

        return attributes


class OctopusElectricityIndexSensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity meter index (Linky counter value)."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the index sensor."""
        super().__init__(coordinator)

        self._prm_id = prm_id
        self._sensor_config = sensor_config
        self._index_type = sensor_config["index_type"]
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_entity_category = sensor_config.get("entity_category")
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

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
        index_data = self.coordinator.data.get("electricity", {}).get("index")

        if not index_data:
            return False

        return self._index_type in index_data


class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Sensor for gas data."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        pce_ref: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the gas sensor."""
        super().__init__(coordinator)

        self._pce_ref = pce_ref
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{pce_ref}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, pce_ref)})

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

        self._current_month: str | None = None
        self._last_imported_date: str | None = None
        self._statistics_imported = False

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        key = self._sensor_config["key"]
        if key in ["consumption", "cost"] and self.entity_id:
            self.hass.async_create_task(self._async_import_statistics())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        key = self._sensor_config["key"]
        if (
            self.entity_id
            and key in ["consumption", "cost"]
            and self._statistics_imported
        ):
            self.hass.async_create_task(self._async_import_statistics())

        super()._handle_coordinator_update()

    async def _async_import_statistics(self) -> None:
        """Import statistics with correct dates from gas readings."""
        key = self._sensor_config["key"]

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

        statistics = []
        cumulative_sum = 0.0

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

                if (
                    self._statistics_imported
                    and self._last_imported_date
                    and reading_date <= self._last_imported_date
                ):
                    consumption = float(reading.get("value", 0))
                    if consumption > 0:
                        if key == "cost":
                            tariff_rate = self._get_tariff_rate()
                            if tariff_rate:
                                reading_value = consumption * tariff_rate
                            else:
                                reading_value = 0.0
                        else:
                            reading_value = consumption
                        cumulative_sum += reading_value
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
            has_mean=False,
            mean_type=StatisticMeanType.ARITHMETIC,
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
        key = self._sensor_config["key"]

        if key == "contract":
            return self._get_contract_status()

        if key == "subscription":
            return self._calculate_monthly_subscription()

        if key == "tarif_base":
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
        key = self._sensor_config["key"]

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

        if key == "tarif_base":
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
        powered_map = {"non_coupe": "En service", "coupe": "CoupÃ©"}
        return powered_map.get(powered, "Inconnu")


class OctopusLedgerSensor(CoordinatorEntity, SensorEntity):
    """Sensor for account ledgers (balances)."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        account_number: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the ledger sensor."""
        super().__init__(coordinator)
        self._account_number = account_number
        self._ledger_type = sensor_config["ledger_type"]
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{account_number}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, account_number)})

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

    @property
    def native_value(self) -> float | None:
        """Return the balance in euros."""
        key = self._sensor_config["key"]

        if "bill" in key:
            payment_requests = self.coordinator.data.get("payment_requests", {})

            _LOGGER.debug(
                "Looking for payment request with ledger_type: %s in %s",
                self._ledger_type,
                list(payment_requests.keys()),
            )

            last_payment = payment_requests.get(self._ledger_type)

            if last_payment:
                customer_amount = last_payment.get("customerAmount")
                if customer_amount is not None:
                    return customer_amount / 100
                _LOGGER.warning(
                    "Payment request found but no customerAmount for %s",
                    self._ledger_type,
                )
            else:
                _LOGGER.debug(
                    "No payment request found for ledger type: %s", self._ledger_type
                )
            return None

        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type, {})
        balance_cents = ledger.get("balance")

        return balance_cents / 100 if balance_cents is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return ledger information."""
        key = self._sensor_config["key"]

        if "bill" in key:
            payment_requests = self.coordinator.data.get("payment_requests", {})
            last_payment = payment_requests.get(self._ledger_type)

            if last_payment:
                return {
                    "payment_status": last_payment.get("paymentStatus", "").lower(),
                    "total_amount": last_payment.get("totalAmount", 0) / 100,
                    "customer_amount": last_payment.get("customerAmount", 0) / 100,
                    "expected_payment_date": last_payment.get("expectedPaymentDate"),
                    "ledger_type": self._ledger_type,
                }
            return {"ledger_type": self._ledger_type, "status": "no_data"}

        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type, {})

        return {
            "ledger_number": ledger.get("number"),
            "ledger_name": ledger.get("name"),
            "balance_cents": ledger.get("balance"),
            "ledger_type": self._ledger_type,
        }
