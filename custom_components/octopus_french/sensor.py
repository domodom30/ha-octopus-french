"""Sensor platform for Octopus Energy France."""

from __future__ import annotations

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

from .const import DOMAIN, LEDGER_TYPE_ELECTRICITY, LEDGER_TYPE_GAS
from .coordinator import OctopusFrenchDataUpdateCoordinator

# Sensor configurations
ELECTRICITY_SENSORS = [
    # ========== CONSOMMATION ==========
    {
        "key": "consumption_hp",
        "name": "Consommation HP",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
        "entity_category": None,  # Visible dans Energy Dashboard
    },
    {
        "key": "consumption_hc",
        "name": "Consommation HC",
        "icon": "mdi:flash-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
        "entity_category": None,  # Visible dans Energy Dashboard
    },
    # ========== INDEX (diagnostic) ==========
    {
        "key": "index_hp",
        "name": "Index HP",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "index_hc",
        "name": "Index HC",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # ========== TARIFS (diagnostic) ==========
    {
        "key": "tarif_hp",
        "name": "Tarif HP",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        "precision": 4,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "tarif_hc",
        "name": "Tarif HC",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        "precision": 4,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # ========== CONTRAT (diagnostic) ==========
    {
        "key": "contrat",
        "name": "Contrat",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
        "entity_category": None,
    },
]

GAS_SENSORS = [
    {
        "key": "consumption",
        "name": "Consommation",
        "icon": "mdi:fire",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": None,
        "entity_category": None,
    },
    {
        "key": "index",
        "name": "Index",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "precision": 0,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "tarif",
        "name": "Tarif",
        "icon": "mdi:currency-eur",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
        "precision": 4,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "contrat",
        "name": "Contrat",
        "icon": "mdi:file-document-outline",
        "device_class": None,
        "state_class": None,
        "unit": None,
        "precision": None,
        "entity_category": None,
    },
]

LEDGER_SENSORS = [
    # ========== CAGNOTTE ==========
    {
        "key": "pot_ledger",
        "ledger_type": "POT_LEDGER",
        "name": "Cagnotte",
        "icon": "mdi:piggy-bank",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
        "entity_category": None,
    },
    # ========== ÉLECTRICITÉ ==========
    {
        "key": "electricity_ledger",
        "ledger_type": "FRA_ELECTRICITY_LEDGER",
        "name": "Solde électricité",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
        "entity_category": None,
    },
    {
        "key": "electricity_bill",
        "ledger_type": "FRA_ELECTRICITY_LEDGER",
        "name": "Facture électricité",
        "icon": "mdi:file-document",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
        "entity_category": None,
    },
    # ========== GAZ ==========
    {
        "key": "gas_ledger",
        "ledger_type": "FRA_GAS_LEDGER",
        "name": "Solde gaz",
        "icon": "mdi:fire",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
        "unit": CURRENCY_EURO,
        "precision": 2,
        "entity_category": None,
    },
    {
        "key": "gas_bill",
        "ledger_type": "FRA_GAS_LEDGER",
        "name": "Facture gaz",
        "icon": "mdi:file-document",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": None,
        "unit": CURRENCY_EURO,
        "precision": 2,
        "entity_category": None,
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
    entities = []
    supply_points = coordinator.data.get("supply_points", {})

    ledgers = coordinator.data.get("ledgers", {})
    if ledgers:
        for sensor_config in LEDGER_SENSORS:
            if sensor_config["ledger_type"] in ledgers:
                entities.append(
                    OctopusLedgerSensor(
                        coordinator,
                        account_number,
                        sensor_config,
                    )
                )

    # Créer les sensors pour chaque compteur électrique
    for elec_meter in supply_points.get("electricity", []):
        prm_id = elec_meter.get("id")
        status = elec_meter.get("distributorStatus")
        powered = elec_meter.get("poweredStatus")

        # Ignorer les compteurs résiliés
        if status == "RESIL" and powered == "LIMI":
            continue

        for sensor_config in ELECTRICITY_SENSORS:
            entities.append(
                OctopusElectricitySensor(
                    coordinator,
                    prm_id,
                    sensor_config,
                )
            )

    # Créer les sensors pour chaque compteur gaz
    for gas_meter in supply_points.get("gas", []):
        pce_ref = gas_meter.get("id")

        for sensor_config in GAS_SENSORS:
            entities.append(
                OctopusGasSensor(
                    coordinator,
                    pce_ref,
                    sensor_config,
                )
            )
    async_add_entities(entities)


class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Sensor for electricity data."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        prm_id: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the sensor."""
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prm_id)},
        )

        if sensor_config["entity_category"] is not None:
            self._attr_entity_category = sensor_config["entity_category"]
        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        key = self._sensor_config["key"]

        # Sensor Contrat
        if key == "contrat":
            return self._get_contract_status()

        # Tarifs - Convertir centimes → euros ET diviser par 100 pour le prix par kWh
        if key == "tarif_hp":
            tarif_cents = (
                self.coordinator.data.get("tarifs", {}).get("electricity", {}).get("hp")
            )
            return round(tarif_cents / 100, 4) if tarif_cents else None

        if key == "tarif_hc":
            tarif_cents = (
                self.coordinator.data.get("tarifs", {}).get("electricity", {}).get("hc")
            )
            return round(tarif_cents / 100, 4) if tarif_cents else None

        # Relevés
        readings = self.coordinator.data.get("electricity_readings", [])
        if not readings:
            return None

        # Filtrer les relevés pour HP et HC
        hp_readings = [r for r in readings if r.get("calendarTempClass") == "HP"]
        hc_readings = [r for r in readings if r.get("calendarTempClass") == "HC"]

        if key == "consumption_hp" and hp_readings:
            return hp_readings[0].get("consumption")
        if key == "consumption_hc" and hc_readings:
            return hc_readings[0].get("consumption")
        if key == "index_hp" and hp_readings:
            return hp_readings[0].get("indexEndValue")
        if key == "index_hc" and hc_readings:
            return hc_readings[0].get("indexEndValue")

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        readings = self.coordinator.data.get("electricity_readings", [])
        key = self._sensor_config["key"]

        # Attributes pour le sensor Contrat
        if key == "contrat":
            supply_points = self.coordinator.data.get("supply_points", {})
            elec_points = supply_points.get("electricity", [])
            meter = next(
                (m for m in elec_points if m.get("id") == self._prm_id),
                None,
            )

            if not meter:
                return {}

            ledgers = self.coordinator.data.get("ledgers", {})

            return {
                "ledger_id": ledgers.get(LEDGER_TYPE_ELECTRICITY).get("number"),
                "prm_id": meter.get("id"),
                "distributor_status": meter.get("distributorStatus"),
                "meter_kind": meter.get("meterKind"),
                "subscribed_max_power": f"{meter.get('subscribedMaxPower')} kVA",
                "is_teleoperable": meter.get("isTeleoperable"),
                "off_peak_label": meter.get("offPeakLabel"),
                "powered_status": meter.get("poweredStatus"),
            }

        if "consumption" in key or "index" in key:
            temp_class = "HP" if "hp" in key else "HC"
            relevant_readings = [
                r for r in readings if r.get("calendarTempClass") == temp_class
            ]

            if relevant_readings:
                latest = relevant_readings[0]
                return {
                    "period_start": latest.get("periodStartAt"),
                    "period_end": latest.get("periodEndAt"),
                    "reliability": latest.get("consumptionReliability"),
                    "status": latest.get("statusProcessed"),
                }

        return {}

    def _get_contract_status(self) -> str:
        """Get a human-readable contract status."""

        supply_points = self.coordinator.data.get("supply_points", {})
        elec_points = supply_points.get("electricity", [])

        meter = next(
            (m for m in elec_points if m.get("id") == self._prm_id),
            None,
        )

        if not meter:
            return "Inconnu"

        status = meter.get("distributorStatus", "")

        # Traduire les statuts
        status_map = {
            "SERVC": "En service",
            "RESIL": "Résilié",
        }

        return f"{status_map.get(status, status)}"


class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Sensor for gas data."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        pce_ref: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the sensor."""
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pce_ref)},
        )
        if sensor_config["entity_category"] is not None:
            self._attr_entity_category = sensor_config["entity_category"]

        if sensor_config["precision"] is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        key = self._sensor_config["key"]

        # Sensor Contrat
        if key == "contrat":
            return self._get_contract_status()

        # Tarif
        if key == "tarif":
            tarif_cents = (
                self.coordinator.data.get("tarifs", {}).get("gas", {}).get("price")
            )
            return round(tarif_cents / 100, 4) if tarif_cents else None

        # Relevés
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return None

        latest = readings[0]

        if key == "consumption":
            return latest.get("consumption")
        if key == "index":
            return latest.get("indexEndValue")

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config["key"]

        # Attributes pour le sensor Contrat
        if key == "contrat":
            supply_points = self.coordinator.data.get("supply_points", {})
            gas_points = supply_points.get("gas", [])

            meter = next(
                (m for m in gas_points if m.get("id") == self._pce_ref),
                None,
            )

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
                "price_level": meter.get("priceLevel"),
                "tariff_option": meter.get("tariffOption"),
            }

        if "consumption" in key or "index" in key:
            readings = self.coordinator.data.get("gas_readings", [])

            if readings:
                latest = readings[0]
                return {
                    "period_start": latest.get("periodStartAt"),
                    "period_end": latest.get("periodEndAt"),
                    "reading_date": latest.get("readingDate"),
                    "reading_type": latest.get("readingType"),
                    "status": latest.get("statusProcessed"),
                }

        return {}

    def _get_contract_status(self) -> str:
        """Get a human-readable contract status."""
        supply_points = self.coordinator.data.get("supply_points", {})
        gas_points = supply_points.get("gas", [])

        meter = next(
            (m for m in gas_points if m.get("id") == self._pce_ref),
            None,
        )

        if not meter:
            return "Inconnu"

        powered = meter.get("poweredStatus", "")

        powered_map = {
            "non_coupe": "En service",
            "coupe": "Coupé",
        }

        return powered_map.get(powered, powered)


class OctopusLedgerSensor(CoordinatorEntity, SensorEntity):
    """Sensor for account ledgers (balances)."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        account_number: str,
        sensor_config: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._account_number = account_number
        self._sensor_config = sensor_config
        self._ledger_type = sensor_config["ledger_type"]
        self._attr_unique_id = f"{DOMAIN}_{account_number}_{sensor_config['key']}"
        self._attr_translation_key = sensor_config["key"]
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config["icon"]
        self._attr_device_class = sensor_config["device_class"]
        self._attr_state_class = sensor_config["state_class"]
        self._attr_native_unit_of_measurement = sensor_config["unit"]

        # Entity category
        entity_category = sensor_config.get("entity_category")
        if entity_category is not None:
            self._attr_entity_category = entity_category

        # Précision d'affichage
        if sensor_config.get("precision") is not None:
            self._attr_suggested_display_precision = sensor_config["precision"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_number)},
        )

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

        # Le solde est en centimes, convertir en euros
        balance_cents = ledger.get("balance")
        if balance_cents is not None:
            return balance_cents / 100
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return ledger information."""
        key = self._sensor_config["key"]

        if "bill" in key:
            payment_requests = self.coordinator.data.get("payment_requests", {})
            last_payment = payment_requests.get(self._ledger_type)

            if last_payment:
                return {
                    "payment_status": last_payment.get("paymentStatus"),
                    "total_amount": f"{last_payment.get('totalAmount', 0) / 100:.2f} €",
                    "customer_amount": f"{last_payment.get('customerAmount', 0) / 100:.2f} €",
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
