"""Sensors for OctopusFrench Energy integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OctopusFrenchSensorEntityDescription(SensorEntityDescription):
    """Describes OctopusFrench sensor entity."""

    ledger_type: str | None = None


class OctopusFrenchBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for OctopusFrench sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._account_number = account_number
        self._attr_unique_id = f"{account_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._account_number)},
            name="Octopus Energy",
            entry_type=DeviceEntryType.SERVICE,
        )


class OctopusBalanceSensor(OctopusFrenchBaseSensor):
    """Sensor for pot balance (cagnotte)."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the balance sensor."""
        super().__init__(coordinator, description, account_number)
        self._ledger_type = description.ledger_type
        self._attr_translation_key = "balance"
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._ledger_type in self.coordinator.data.get("ledgers", {})
        )

    @property
    def native_value(self) -> float | None:
        """Return the balance in euros."""
        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type)

        if not ledger:
            return None

        balance = ledger.get("balance")
        if balance is None:
            return None

        # Convert cents to euros
        return round(balance / 100, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type)

        if not ledger:
            return {}

        return {
            "ledger_type": self._ledger_type,
            "ledger_name": ledger.get("name", ""),
            "ledger_number": ledger.get("number", ""),
        }


class OctopusElectricityMeterSensor(OctopusFrenchBaseSensor):
    """Sensor for individual electricity meter."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._prm_id = self.coordinator.data.get("prm_id")
        self._attr_unique_id = f"{account_number}_elec_meter"
        self._attr_translation_key = "electricity_meter"
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = {"prm_id": self._prm_id}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )

    @property
    def native_value(self) -> str:
        """Return the PRM ID."""
        return self._prm_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meter information."""
        supply_points = self.coordinator.data.get("supply_points", {})
        elec_points = supply_points.get("electricity", [])

        meter = next(
            (
                m
                for m in elec_points
                if m.get("id") == self.coordinator.data.get("prm_id")
            ),
            None,
        )

        if not meter:
            return {}

        return {
            "prm_id": meter.get("id"),
            "meter_kind": meter.get("meterKind"),
            "subscribed_max_power": meter.get("subscribedMaxPower"),
            "off_peak_label": meter.get("offPeakLabel"),
            "is_teleoperable": meter.get("isTeleoperable"),
            "powered_status": meter.get("poweredStatus"),
            "distributor_status": meter.get("distributorStatus"),
        }


class OctopusGasMeterSensor(OctopusFrenchBaseSensor):
    """Sensor for individual gas meter."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._pce_ref = self.coordinator.data.get("pce_ref")
        self._attr_unique_id = f"{account_number}_gas_meter_{self._pce_ref}"
        self._attr_translation_key = "gas_meter"
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = {"pce_ref": self._pce_ref}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )

    @property
    def native_value(self) -> str:
        """Return the PCE reference."""
        return self._pce_ref

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return meter information."""
        supply_points = self.coordinator.data.get("supply_points", {})
        gas_points = supply_points.get("gas", [])

        meter = next((m for m in gas_points if m.get("id") == self._pce_ref), None)

        if not meter:
            return {}

        return {
            "pce_ref": meter.get("id"),
            "gas_nature": meter.get("gasNature"),
            "annual_consumption": meter.get("annualConsumption"),
            "is_smart_meter": meter.get("isSmartMeter"),
        }


class OctopusElectricityIndexSensor(OctopusFrenchBaseSensor):
    """Sensor for electricity meter index (HC or HP)."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
        calendar_class: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._calendar_class = calendar_class
        self._attr_unique_id = f"{account_number}_{description.key}_{calendar_class}"
        self._attr_translation_key = "electricity_index"
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = {"calendar_class": calendar_class}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "electricity_readings" in self.coordinator.data
        )

    def _get_filtered_readings(self) -> list[dict]:
        """Get readings filtered by calendar class."""
        readings = self.coordinator.data.get("electricity_readings", [])
        return [
            r
            for r in readings
            if r.get("calendarTempClass") == self._calendar_class
            and r.get("calendarType") == "PROVIDER"
        ]

    @property
    def native_value(self) -> float | None:
        """Return the current meter index."""
        readings = self._get_filtered_readings()
        if not readings:
            return None

        latest = readings[0]
        index_end = latest.get("indexEndValue")
        return float(index_end) if index_end is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self._get_filtered_readings()
        if not readings:
            return {}

        latest = readings[0]
        calendar_label = (
            "Heures Creuses" if self._calendar_class == "HC" else "Heures Pleines"
        )

        return {
            "prm_id": self.coordinator.data.get("prm_id"),
            "calendar_type": calendar_label,
            "index_start": latest.get("indexStartValue"),
            "index_end": latest.get("indexEndValue"),
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
            "calendar_temp_class": latest.get("calendarTempClass"),
            "status": latest.get("statusProcessed"),
        }


class OctopusElectricityConsumptionSensor(OctopusFrenchBaseSensor):
    """Sensor for electricity consumption (HC or HP)."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
        calendar_class: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._calendar_class = calendar_class
        self._attr_unique_id = f"{account_number}_{description.key}_{calendar_class}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "electricity_readings" in self.coordinator.data
        )

    def _get_filtered_readings(self) -> list[dict]:
        """Get readings filtered by calendar class."""
        readings = self.coordinator.data.get("electricity_readings", [])
        return [
            r
            for r in readings
            if r.get("calendarTempClass") == self._calendar_class
            and r.get("calendarType") == "PROVIDER"
        ]

    @property
    def native_value(self) -> float | None:
        """Return the consumption for the period."""
        readings = self._get_filtered_readings()
        if not readings:
            return None

        latest = readings[0]
        consumption = latest.get("consumption")
        return float(consumption) if consumption is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self._get_filtered_readings()
        if not readings:
            return {}

        latest = readings[0]
        calendar_label = (
            "Heures Creuses" if self._calendar_class == "HC" else "Heures Pleines"
        )

        return {
            "prm_id": self.coordinator.data.get("prm_id"),
            "calendar_type": calendar_label,
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
            "reliability": latest.get("consumptionReliability"),
            "status": latest.get("statusProcessed"),
        }


class OctopusGasIndexSensor(OctopusFrenchBaseSensor):
    """Sensor for gas meter index."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._attr_translation_key = "gas_index"
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "gas_readings" in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        """Return the current meter index."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return None

        latest = readings[0]
        index_end = latest.get("indexEndValue")
        return float(index_end) if index_end is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return {}

        latest = readings[0]
        return {
            "pce_ref": self.coordinator.data.get("pce_ref"),
            "index_start": latest.get("indexStartValue"),
            "index_end": latest.get("indexEndValue"),
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
            "reading_date": latest.get("readingDate"),
            "reading_type": latest.get("readingType"),
            "status": latest.get("statusProcessed"),
        }


class OctopusGasConsumptionSensor(OctopusFrenchBaseSensor):
    """Sensor for gas consumption."""

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "gas_readings" in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        """Return the consumption for the period."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return None

        latest = readings[0]
        consumption = latest.get("consumption")
        return float(consumption) if consumption is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return {}

        latest = readings[0]
        return {
            "pce_ref": self.coordinator.data.get("pce_ref"),
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
            "reading_type": latest.get("readingType"),
            "status": latest.get("statusProcessed"),
        }


class OctopusElectricityCostSensor(OctopusFrenchBaseSensor):
    """Sensor for electricity cost (HC or HP)."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
        calendar_class: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._calendar_class = calendar_class
        self._attr_unique_id = f"{account_number}_{description.key}_{calendar_class}"
        self._attr_translation_key = "cost_electricity"
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = {"calendar_class": calendar_class}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "electricity_readings" in self.coordinator.data
            and "tarifs" in self.coordinator.data
        )

    def _get_filtered_readings(self) -> list[dict]:
        """Get readings filtered by calendar class."""
        readings = self.coordinator.data.get("electricity_readings", [])
        return [
            r
            for r in readings
            if r.get("calendarTempClass") == self._calendar_class
            and r.get("calendarType") == "PROVIDER"
        ]

    @property
    def native_value(self) -> float | None:
        """Return the cost for the period."""
        readings = self._get_filtered_readings()
        if not readings:
            return None

        latest = readings[0]
        consumption = latest.get("consumption")

        if consumption is None:
            return None

        # Get tarif
        tarifs = self.coordinator.data.get("tarifs", {})
        elec_tarifs = tarifs.get("electricity", {})

        tarif_key = "hc" if self._calendar_class == "HC" else "hp"
        price_per_kwh = elec_tarifs.get(tarif_key, 0)

        if price_per_kwh == 0:
            return None

        # Calculate cost (price is in euro cents)
        cost_euros = (consumption * price_per_kwh) / 100
        return round(cost_euros, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self._get_filtered_readings()
        if not readings:
            return {}

        latest = readings[0]
        tarifs = self.coordinator.data.get("tarifs", {})
        elec_tarifs = tarifs.get("electricity", {})

        tarif_key = "hc" if self._calendar_class == "HC" else "hp"
        price_per_kwh = elec_tarifs.get(tarif_key, 0)

        return {
            "prm_id": self.coordinator.data.get("prm_id"),
            "consumption_kwh": latest.get("consumption"),
            "price_per_kwh_cents": price_per_kwh,
            "price_per_kwh_euros": round(price_per_kwh / 100, 4),
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
        }


class OctopusGasCostSensor(OctopusFrenchBaseSensor):
    """Sensor for gas cost."""

    def __init__(
        self,
        coordinator,
        description: OctopusFrenchSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, account_number)
        self._attr_unique_id = f"{account_number}_{description.key}"
        self._attr_translation_key = "cost_gas"
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and "gas_readings" in self.coordinator.data
            and "tarifs" in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        """Return the cost for the period."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return None

        latest = readings[0]
        consumption = latest.get("consumption")

        if consumption is None:
            return None

        # Get tarif
        tarifs = self.coordinator.data.get("tarifs", {})
        gas_price = tarifs.get("gas", {}).get("price", 0)

        if gas_price == 0:
            return None

        # Convert m³ to kWh (approximation: 1 m³ ≈ 10-11 kWh, on utilise 10.5)
        consumption_kwh = consumption * 10.5

        # Calculate cost (price is in euro cents per kWh)
        cost_euros = (consumption_kwh * gas_price) / 100
        return round(cost_euros, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        readings = self.coordinator.data.get("gas_readings", [])
        if not readings:
            return {}

        latest = readings[0]
        tarifs = self.coordinator.data.get("tarifs", {})
        gas_price = tarifs.get("gas", {}).get("price", 0)

        consumption_m3 = latest.get("consumption", 0)
        consumption_kwh = consumption_m3 * 10.5

        return {
            "pce_ref": self.coordinator.data.get("pce_ref"),
            "consumption_m3": consumption_m3,
            "consumption_kwh": round(consumption_kwh, 2),
            "price_per_kwh_cents": gas_price,
            "price_per_kwh_euros": round(gas_price / 100, 4),
            "period_start": latest.get("periodStartAt"),
            "period_end": latest.get("periodEndAt"),
        }


# Sensor descriptions
BALANCE_SENSOR = OctopusFrenchSensorEntityDescription(
    key="balance",
    name="Cagnotte",
    icon="mdi:piggy-bank",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement=CURRENCY_EURO,
    suggested_display_precision=2,
    ledger_type="POT_LEDGER",
)

CONTRACT_SENSOR = OctopusFrenchSensorEntityDescription(
    key="contract",
    name="Contrat",
    icon="mdi:file-document-outline",
)

ELECTRICITY_SENSORS: tuple[OctopusFrenchSensorEntityDescription, ...] = (
    OctopusFrenchSensorEntityDescription(
        key="electricity_index_hc",
        name="Index Électricité HC",
        icon="mdi:counter",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
    OctopusFrenchSensorEntityDescription(
        key="electricity_index_hp",
        name="Index Électricité HP",
        icon="mdi:counter",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
    ),
    OctopusFrenchSensorEntityDescription(
        key="electricity_consumption_hc",
        name="Électricité HC",
        icon="mdi:weather-night",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
    ),
    OctopusFrenchSensorEntityDescription(
        key="electricity_consumption_hp",
        name="Électricité HP",
        icon="mdi:weather-sunny",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
    ),
)

GAS_SENSORS: tuple[OctopusFrenchSensorEntityDescription, ...] = (
    OctopusFrenchSensorEntityDescription(
        key="gas_index",
        name="Index Gaz",
        icon="mdi:counter",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=0,
    ),
    OctopusFrenchSensorEntityDescription(
        key="gas_consumption",
        name="Gaz",
        icon="mdi:fire",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=2,
    ),
)

COST_SENSORS: tuple[OctopusFrenchSensorEntityDescription, ...] = (
    OctopusFrenchSensorEntityDescription(
        key="electricity_cost_hc",
        name="Coût Électricité HC",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
    ),
    OctopusFrenchSensorEntityDescription(
        key="electricity_cost_hp",
        name="Coût Électricité HP",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
    ),
    OctopusFrenchSensorEntityDescription(
        key="gas_cost",
        name="Coût Gaz",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus French sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    if not (data := coordinator.data):
        _LOGGER.warning("No coordinator data available for sensors")
        return

    account_number = data.get("account_number")
    if not account_number:
        _LOGGER.error("No account number found in coordinator data")
        return

    sensors: list[SensorEntity] = []

    # Create balance sensor (cagnotte)
    ledgers = data.get("ledgers", {})
    if "POT_LEDGER" in ledgers:
        sensors.append(
            OctopusBalanceSensor(
                coordinator,
                BALANCE_SENSOR,
                account_number,
            )
        )
        _LOGGER.info("Created balance sensor for account %s", account_number)

    # Create contract Electricity sensor
    sensors.append(
        OctopusElectricityMeterSensor(
            coordinator,
            CONTRACT_SENSOR,
            account_number,
        )
    )
    # Create contract Gas sensor
    sensors.append(
        OctopusGasMeterSensor(
            coordinator,
            CONTRACT_SENSOR,
            account_number,
        )
    )
    _LOGGER.info("Created contract sensor for account %s", account_number)

    # Create electricity sensors (index + consumption & cost for HC and HP)
    if data.get("electricity_readings") and data.get("prm_id"):
        # Index HC
        sensors.append(
            OctopusElectricityIndexSensor(
                coordinator,
                ELECTRICITY_SENSORS[0],
                account_number,
                "HC",
            )
        )
        # Index HP
        sensors.append(
            OctopusElectricityIndexSensor(
                coordinator,
                ELECTRICITY_SENSORS[1],
                account_number,
                "HP",
            )
        )
        # Cost HC
        sensors.append(
            OctopusElectricityCostSensor(
                coordinator,
                COST_SENSORS[0],
                account_number,
                "HC",
            )
        )
        # Cost HP
        sensors.append(
            OctopusElectricityCostSensor(
                coordinator,
                COST_SENSORS[1],
                account_number,
                "HP",
            )
        )

        _LOGGER.info(
            "Created 4 electricity sensors (2 index + 2 consumption) for account %s",
            account_number,
        )

    # Create gas sensors (index + consumption + cost)
    if data.get("gas_readings") and data.get("pce_ref"):
        # Index Gaz
        sensors.append(
            OctopusGasIndexSensor(
                coordinator,
                GAS_SENSORS[0],
                account_number,
            )
        )
        # Consumption Gaz
        sensors.append(
            OctopusGasConsumptionSensor(
                coordinator,
                GAS_SENSORS[1],
                account_number,
            )
        )
        # Cost Gaz
        sensors.append(
            OctopusGasCostSensor(
                coordinator,
                COST_SENSORS[2],
                account_number,
            )
        )
        _LOGGER.info(
            "Created 2 gas sensors (index + consumption) for account %s",
            account_number,
        )

    if sensors:
        async_add_entities(sensors)
    else:
        _LOGGER.debug("No sensors created for account %s", account_number)
