"""Sensor platform for Octopus Energy France - FULL RESTORED & CALCULATED COST VERSION."""

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

# --- CONFIGURATIONS DES CAPTEURS ---

ELECTRICITY_SENSORS = [
    {"key": "conso_base", "icon": "mdi:lightning-bolt", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 2},
    {"key": "conso_hp", "icon": "mdi:lightning-bolt", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 2},
    {"key": "conso_hc", "icon": "mdi:lightning-bolt-outline", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 2},
    {"key": "cout_base", "icon": "mdi:currency-eur", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "cout_hp", "icon": "mdi:currency-eur", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "cout_hc", "icon": "mdi:currency-eur", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "contract", "icon": "mdi:file-document-outline", "device_class": None, "state_class": None, "unit": None, "precision": None},
    {"key": "subscription", "icon": "mdi:calendar-month", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "subscribed_power", "icon": "mdi:flash", "device_class": SensorDeviceClass.APPARENT_POWER, "state_class": None, "unit": "kVA", "precision": 1},
    {"key": "tarif_base", "icon": "mdi:cash", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": f"{CURRENCY_EURO}/kWh", "precision": 4},
    {"key": "tarif_hp", "icon": "mdi:cash-plus", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": f"{CURRENCY_EURO}/kWh", "precision": 4},
    {"key": "tarif_hc", "icon": "mdi:cash-minus", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": f"{CURRENCY_EURO}/kWh", "precision": 4},
]

ELECTRICITY_INDEX_SENSORS = [
    {"key": "index_base", "index_type": "base", "icon": "mdi:counter", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "entity_category": EntityCategory.DIAGNOSTIC, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 0},
    {"key": "index_hp", "index_type": "hp", "icon": "mdi:counter", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "entity_category": EntityCategory.DIAGNOSTIC, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 0},
    {"key": "index_hc", "index_type": "hc", "icon": "mdi:counter", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL_INCREASING, "entity_category": EntityCategory.DIAGNOSTIC, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 0},
]

GAS_SENSORS = [
    {"key": "consumption", "icon": "mdi:fire", "device_class": SensorDeviceClass.ENERGY, "state_class": None, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 2},
    {"key": "cost", "icon": "mdi:currency-eur", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "contract", "icon": "mdi:file-document-outline", "device_class": None, "state_class": None, "unit": None, "precision": None},
    {"key": "subscription", "icon": "mdi:calendar-month", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "tarif_base", "icon": "mdi:cash", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": f"{CURRENCY_EURO}/kWh", "precision": 4},
]

LEDGER_SENSORS = [
    {"key": "pot_ledger", "ledger_type": "POT_LEDGER", "icon": "mdi:piggy-bank", "device_class": SensorDeviceClass.MONETARY, "state_class": SensorStateClass.TOTAL, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "electricity_bill", "ledger_type": "FRA_ELECTRICITY_LEDGER", "icon": "mdi:file-document", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": CURRENCY_EURO, "precision": 2},
    {"key": "gas_bill", "ledger_type": "FRA_GAS_LEDGER", "icon": "mdi:file-document", "device_class": SensorDeviceClass.MONETARY, "state_class": None, "unit": CURRENCY_EURO, "precision": 2},
]

LATEST_READING_SENSOR = {"key": "latest_reading", "icon": "mdi:calendar-clock", "device_class": SensorDeviceClass.ENERGY, "state_class": SensorStateClass.TOTAL, "entity_category": EntityCategory.DIAGNOSTIC, "unit": UnitOfEnergy.KILO_WATT_HOUR, "precision": 2}

# --- SETUP ---

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Octopus Energy France sensors."""
    coordinator: OctopusFrenchDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    account_number = hass.data[DOMAIN][entry.entry_id]["account_number"]

    await coordinator.async_config_entry_first_refresh()

    entities = []
    supply_points = coordinator.data.get("supply_points", {})
    ledgers = coordinator.data.get("ledgers", {})

    if ledgers:
        for sensor_config in LEDGER_SENSORS:
            if sensor_config["ledger_type"] in ledgers:
                entities.append(OctopusLedgerSensor(coordinator, account_number, sensor_config))

    for elec_meter in supply_points.get("electricity", []):
        prm_id = elec_meter.get("id")
        tariff_type = _detect_tariff_type_for_meter(coordinator.data, prm_id)
        
        for sensor_config in ELECTRICITY_SENSORS:
            sensor_key = sensor_config["key"]
            if (sensor_key in {"contract", "subscription", "subscribed_power"} or 
                (tariff_type == "BASE" and sensor_key in ["conso_base", "cout_base", "tarif_base"]) or 
                (tariff_type == "HPHC" and sensor_key in ["conso_hp", "conso_hc", "cout_hp", "cout_hc", "tarif_hp", "tarif_hc"])):
                entities.append(OctopusElectricitySensor(coordinator, prm_id, sensor_config))

        entities.append(OctopusLatestReadingSensor(coordinator, prm_id, LATEST_READING_SENSOR))

        index_data = coordinator.data.get("electricity", {}).get("index")
        if index_data:
            idx_tariff = index_data.get("tariff_type")
            for index_config in ELECTRICITY_INDEX_SENSORS:
                idx_type = index_config.get("index_type")
                if (idx_tariff == "BASE" and idx_type == "base") or (idx_tariff == "HPHC" and idx_type in ["hp", "hc"]):
                    entities.append(OctopusElectricityIndexSensor(coordinator, prm_id, index_config))

    for gas_meter in supply_points.get("gas", []):
        for sensor_config in GAS_SENSORS:
            entities.append(OctopusGasSensor(coordinator, gas_meter.get("id"), sensor_config))

    async_add_entities(entities)

def _detect_tariff_type_for_meter(data: dict, prm_id: str) -> str:
    """Détection robuste du type de tarif."""
    elec_data = data.get("electricity", {})
    tariffs = elec_data.get("tariffs")
    if tariffs:
        conso = tariffs.get("consumption", {})
        if conso.get("heures_pleines") and conso.get("heures_creuses"): return "HPHC"
        if conso.get("base"): return "BASE"
    return "UNKNOWN"

# --- CLASSES CAPTEURS ---

class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity data with calculated costs."""
    def __init__(self, coordinator, prm_id, sensor_config) -> None:
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

    @property
    def native_value(self) -> float | str | None:
        key = self._sensor_config["key"]
        if key == "contract": return self._get_contract_type()
        if key == "subscription": return self._calculate_subscription()
        if key == "subscribed_power": return self._get_subscribed_power()
        if key.startswith("tarif_"): return self._get_tariff_rate()
        if key.startswith(("conso_", "cout_")): return self._calculate_monthly_total()
        return None

    def _get_subscribed_power(self) -> float | None:
        meter = self._get_meter_data()
        return meter.get("subscribedMaxPower") if meter else None

    def _get_tariff_rate(self) -> float | None:
        """Récupère le tarif TTC correspondant à la catégorie du capteur."""
        tariffs = self.coordinator.data.get("electricity", {}).get("tariffs")
        if not tariffs: return None
        conso = tariffs.get("consumption", {})
        k = self._sensor_config["key"]
        if "base" in k: return (conso.get("base") or {}).get("price_ttc")
        if "hp" in k: return (conso.get("heures_pleines") or {}).get("price_ttc")
        if "hc" in k: return (conso.get("heures_creuses") or {}).get("price_ttc")
        return None

    def _calculate_monthly_total(self) -> float:
        """Calcule la consommation ou le coût mensuel localement."""
        key = self._sensor_config["key"]
        readings = self.coordinator.data.get("electricity", {}).get("readings", [])
        if not readings: return 0.0
        
        current_month = dt_util.now().strftime("%Y-%m")
        total_conso = 0.0
        
        mapping = {
            "conso_base": "BASE", "cout_base": "BASE",
            "conso_hp": "HEURES_PLEINES", "cout_hp": "HEURES_PLEINES",
            "conso_hc": "HEURES_CREUSES", "cout_hc": "HEURES_CREUSES"
        }
        if key not in mapping: return 0.0
        label = mapping[key]

        for r in readings:
            try:
                if datetime.fromisoformat(r.get("startAt")).strftime("%Y-%m") != current_month: continue
                for s in r.get("metaData", {}).get("statistics", []):
                    if s.get("label") == label:
                        total_conso += float(s.get("value") or 0)
            except: continue

        if key.startswith("conso_"):
            return round(total_conso, 2)
            
        rate = self._get_tariff_rate()
        if rate:
            return round(total_conso * rate, 2)
            
        return 0.0

    def _get_meter_data(self) -> dict | None:
        supply = self.coordinator.data.get("supply_points", {}).get("electricity", [])
        return next((m for m in supply if m.get("id") == self._prm_id), None)

    def _get_contract_type(self) -> str:
        meter = self._get_meter_data()
        return meter.get("providerCalendar", {}).get("id", "Inconnu") if meter else "Inconnu"

    def _calculate_subscription(self) -> float:
        agreements = self.coordinator.data.get("agreements", [])
        for agg in agreements:
            if agg.get("prm") == self._prm_id and agg.get("is_active"):
                val = agg.get("tariffs", {}).get("subscription", {}).get("monthly_ttc_eur")
                if val: return round(float(val), 2)
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {"prm_id": self._prm_id}
        elec = self.coordinator.data.get("electricity", {})
        if elec.get("tariffs"): attrs["tariffs"] = elec["tariffs"]
        if self._sensor_config["key"] == "contract":
            meter = self._get_meter_data()
            if meter:
                attrs.update({
                    "distributor_status": meter.get("distributorStatus"),
                    "meter_kind": meter.get("meterKind"),
                    "subscribed_max_power": f"{meter.get('subscribedMaxPower')} kVA",
                })
        return attrs

class OctopusLatestReadingSensor(CoordinatorEntity, SensorEntity):
    """Capteur du dernier relevé."""
    def __init__(self, coordinator, prm_id, config):
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_latest"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_has_entity_name = True
        self._attr_translation_key = "latest_reading"

    @property
    def native_value(self) -> float | None:
        readings = self.coordinator.data.get("electricity", {}).get("readings", [])
        return float(readings[-1].get("value")) if readings else None

class OctopusElectricityIndexSensor(CoordinatorEntity, SensorEntity):
    """Capteur d'index Linky optimisé pour le Dashboard Énergie."""
    def __init__(self, coordinator, prm_id, config):
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._type = config["index_type"]
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_{config['key']}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prm_id)})
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_has_entity_name = True
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        idx = self.coordinator.data.get("electricity", {}).get("index", {})
        return idx.get(self._type, {}).get("index_end")

class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Capteur Gaz."""
    def __init__(self, coordinator, pce_ref, config):
        super().__init__(coordinator)
        self._pce_ref = pce_ref
        self._attr_unique_id = f"{DOMAIN}_{pce_ref}_{config['key']}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, pce_ref)})
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_has_entity_name = True

    @property
    def native_value(self) -> float | str | None:
        return 0.0

class OctopusLedgerSensor(CoordinatorEntity, SensorEntity):
    """Capteur de solde/facture."""
    def __init__(self, coordinator, account_number, config):
        super().__init__(coordinator)
        self._type = config["ledger_type"]
        self._attr_unique_id = f"{DOMAIN}_{account_number}_{config['key']}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, account_number)})
        self._attr_native_unit_of_measurement = config["unit"]
        self._attr_has_entity_name = True
        self._attr_state_class = config.get("state_class")

    @property
    def native_value(self) -> float | None:
        ledgers = self.coordinator.data.get("ledgers", {})
        val = ledgers.get(self._type, {}).get("balance")
        return val / 100 if val is not None else None
