"""Sensor platform for Octopus Energy France - CORRECTED VERSION."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

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

# Sensor configurations
ELECTRICITY_SENSORS = [
    {
        "key": "conso_base",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "conso_hp",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "conso_hc",
        "icon": "mdi:lightning-bolt-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "cout_base",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "cout_hp",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "cout_hc",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
    },
    {
        "key": "contrat",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
    },
]

# Configuration des sensors d'index
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
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 2,
    },
    {
        "key": "contrat",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
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

    # Ledger sensors
    if ledgers:
        entities.extend(
            OctopusLedgerSensor(coordinator, account_number, sensor_config)
            for sensor_config in LEDGER_SENSORS
            if sensor_config["ledger_type"] in ledgers
        )

    # Electricity sensors
    for elec_meter in supply_points.get("electricity", []):
        if (
            elec_meter.get("distributorStatus") == "RESIL"
            and elec_meter.get("poweredStatus") == "LIMI"
        ):
            continue

        prm_id = elec_meter.get("id")
        tariff_type = _detect_tariff_type_for_meter(coordinator.data, prm_id)

        # Sensors de consommation/coût
        for sensor_config in ELECTRICITY_SENSORS:
            sensor_key = sensor_config["key"]

            if (
                sensor_key == "contrat"
                or (tariff_type == "BASE" and sensor_key in ["conso_base", "cout_base"])
                or (
                    tariff_type == "HPHC"
                    and sensor_key in ["conso_hp", "conso_hc", "cout_hp", "cout_hc"]
                )
            ):
                entities.append(
                    OctopusElectricitySensor(coordinator, prm_id, sensor_config)
                )

        # Sensors d'index (compteur Linky)
        index_data = coordinator.data.get("electricity", {}).get("index")
        if index_data:
            index_tariff_type = index_data.get("tariff_type")

            for index_config in ELECTRICITY_INDEX_SENSORS:
                index_type = index_config["index_type"]

                # Créer le sensor si le type correspond au tarif
                if (index_tariff_type == "BASE" and index_type == "base") or (
                    index_tariff_type == "HPHC" and index_type in ["hp", "hc"]
                ):
                    entities.append(
                        OctopusElectricityIndexSensor(coordinator, prm_id, index_config)
                    )

    # Gas sensors
    entities.extend(
        OctopusGasSensor(coordinator, gas_meter.get("id"), sensor_config)
        for gas_meter in supply_points.get("gas", [])
        for sensor_config in GAS_SENSORS
    )

    async_add_entities(entities)


def _detect_tariff_type_for_meter(data: dict, prm_id: str) -> str:
    """Détecte le type de tarif pour un compteur spécifique."""
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
        _LOGGER.error("Erreur détection tarif %s: %s", prm_id, e)
        return "UNKNOWN"
    return "UNKNOWN"


class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity data with FIXED cumulative logic."""

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

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

    def _calculate_monthly_total(self) -> float:
        """Calcul monthly total."""
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

        # Mapping pour consommations
        consumption_mapping = {
            "conso_base": "BASE",
            "conso_hp": "HEURES_PLEINES",
            "conso_hc": "HEURES_CREUSES",
        }

        # Mapping pour coûts
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

                # Ignorer les lectures des mois précédents
                if reading_month != current_month:
                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing date %s: %s", reading_date, e)
                continue

            statistics = reading.get("metaData", {}).get("statistics", [])

            for stat in statistics:
                label = stat.get("label", "")

                # Pour les consommations (kWh)
                if key.startswith("conso_"):
                    expected_label = consumption_mapping.get(key)
                    value = stat.get("value")

                    if value is not None and label == expected_label:
                        total += float(value)

                # Pour les coûts (EUR)
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

        if key == "contrat":
            return self._get_contract_type()

        if key.startswith(("conso_", "cout_")):
            current_month = self._get_current_month()

            # Détecter changement de mois
            if self._current_month != current_month:
                self._current_month = current_month

            return self._calculate_monthly_total()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config["key"]

        if key == "contrat":
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

        if key.startswith(("conso_", "cout_")):
            readings = self.coordinator.data.get("electricity", {}).get("readings", [])
            readings_count = len(readings)

            return {
                "current_month": self._current_month,
                "readings_count": readings_count,
                "calculation_method": "Cumulée / mois",
            }

        return {}

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

        return meter.get("providerCalendar", {}).get("id")


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

        # Récupérer l'index de fin selon le type
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

        # Le sensor est disponible si les données pour ce type existent
        return self._index_type in index_data


class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Sensor for gas data with FIXED cumulative logic."""

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

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

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

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        key = self._sensor_config["key"]

        if key == "contrat":
            return self._get_contract_status()

        if key == "consumption":
            current_month = self._get_current_month()

            if self._current_month != current_month:
                self._current_month = current_month

            return self._calculate_monthly_total()

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config["key"]

        if key == "contrat":
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

        if key == "consumption":
            readings = self.coordinator.data.get("gas", [])

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / an",
            }

        return {}

    def _get_contract_status(self) -> str:
        """Get a human-readable contract status."""
        supply_points = self.coordinator.data.get("supply_points", {})
        gas_points = supply_points.get("gas", [])
        meter = next((m for m in gas_points if m.get("id") == self._pce_ref), None)

        if not meter:
            return "Inconnu"

        powered = meter.get("poweredStatus", "")
        powered_map = {"non_coupe": "En service", "coupe": "Coupé"}
        return powered_map.get(powered, powered)


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
            last_payment = payment_requests.get(self._ledger_type)

            if last_payment and "customerAmount" in last_payment:
                return last_payment["customerAmount"] / 100
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
            payment_status = last_payment.get("paymentStatus", "").lower()

            if last_payment:
                return {
                    "payment_status": payment_status,
                    "total_amount": last_payment.get("totalAmount", 0) / 100,
                    "customer_amount": last_payment.get("customerAmount", 0) / 100,
                    "expected_payment_date": last_payment.get("expectedPaymentDate"),
                }
            return {}

        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type, {})

        return {
            "ledger_number": ledger.get("number"),
            "ledger_name": ledger.get("name"),
            "balance_cents": ledger.get("balance"),
        }
