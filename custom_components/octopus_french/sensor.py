"""Sensor platform for Octopus Energy French integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, CURRENCY_EURO
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTRIBUTION,
    CONF_ACCOUNT_NUMBER,
    SUPPORTED_LEDGER_TYPES,
)
from .coordinator import OctopusDataUpdateCoordinator
from .utils.logger import LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Energy French sensors from a config entry."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    account_number = data[CONF_ACCOUNT_NUMBER]

    LOGGER.debug("Starting sensor setup for account %s", account_number)

    # Récupérer les ledgers
    enhanced_ledgers = await client.get_data_ledgers(account_number)

    coordinator.data = enhanced_ledgers
    
    sensors: list[SensorEntity] = []
    created_sensors = set()

    # Créer les sensors de balance classiques
    for ledger_type, config in SUPPORTED_LEDGER_TYPES.items():
        
        # Récupérer le solde depuis les ledgers
        balance = 0
        for ledger in coordinator.data:  # <- SUPPRIMER .get("ledgers", [])
            if ledger.get("ledgerType") == ledger_type:
                balance = ledger.get("balance", 0)
                break

        # Ignorer les doublons ou balances à 0
        sensor_id = f"{ledger_type}_{account_number}"
        if sensor_id in created_sensors:
            continue
        if balance == 0 and not config.get("create_if_zero", False):
            continue
        if not config.get("create_sensor", True):
            continue

        # Créer le capteur approprié
        if ledger_type == "POT_LEDGER":
            sensors.append(OctopusPotSensor(coordinator, account_number))
        if ledger_type == "FRA_ELECTRICITY_LEDGER":
            sensors.append(OctopusElectricitySensor(coordinator, account_number))
        if ledger_type == "FRA_ELECTRICITY_LEDGER":
            sensors.append(OctopusGasSensor(coordinator, account_number))
        created_sensors.add(sensor_id)

    async_add_entities(sensors, True)
    LOGGER.debug("Total sensors created: %d for account %s", len(sensors), account_number)


class OctopusPotSensor(CoordinatorEntity, SensorEntity):
    """Capteur spécialisé pour afficher le solde de la cagnotte."""

    def __init__(self, coordinator: OctopusDataUpdateCoordinator, account_number: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.account_number = account_number

        self._attr_name = "Octopus Energy Cagnotte"
        self._attr_unique_id = f"octopus_french_pot_{account_number}"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = CURRENCY_EURO
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:piggy-bank"
        self._attr_attribution = ATTRIBUTION

    @property
    def native_value(self):
        # self.coordinator.data est maintenant une liste de ledgers
        for ledger in self.coordinator.data:
            if ledger.get("ledgerType") == "POT_LEDGER":
                balance = ledger.get("balance", 0)
                return round(balance / 100, 2)
        return 0

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        balance = 0
        # Parcourir la liste pour trouver le solde de la cagnotte
        for ledger in self.coordinator.data:
            if ledger.get("ledgerType") == "POT_LEDGER":
                balance = ledger.get("balance", 0)
                break
        
        balance_euros = round(balance / 100, 2)

        return {
            "account_number": self.account_number,
            "currency": CURRENCY_EURO,
            "balance_raw": balance,
            "balance_euros": balance_euros,
        }


class OctopusElectricitySensor(CoordinatorEntity, SensorEntity):
    """Electricity sensor with detailed monthly HP/HC breakdown."""
    
    def __init__(self, coordinator: OctopusDataUpdateCoordinator, account_number: str):
        super().__init__(coordinator)
        self.account_number = account_number
        
        self._attr_name = f"Electricity Energy ({account_number})"
        self._attr_unique_id = f"{DOMAIN}_{account_number}_electricity_energy"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_attribution = ATTRIBUTION

    def _get_electricity_ledger(self) -> dict[str, Any] | None:
        """Récupère le ledger électrique depuis les données du coordinateur."""
        if not self.coordinator.data:
            return None
            
        for ledger in self.coordinator.data:
            if ledger.get("ledgerType") == "FRA_ELECTRICITY_LEDGER":
                return ledger
        return None

    def _get_monthly_breakdown(self) -> tuple[float, dict]:
        """Calcule la ventilation mensuelle HP/HC et le total global."""
        ledger = self._get_electricity_ledger()
        if not ledger or not ledger.get("additional_data", {}).get("readings"):
            return 0.0, {}
            
        readings = ledger["additional_data"]["readings"]
        monthly_data = {}
        total_consumption = 0.0
        
        for reading in readings:
            consumption = reading.get("consumption")
            period_end = reading.get("periodEndAt")
            temp_class = reading.get("calendarTempClass", "").upper()
            
            if consumption is not None and period_end and len(period_end) >= 7:
                # Extraire le mois (format YYYY-MM)
                month_key = period_end[:7]
                
                if month_key not in monthly_data:
                    monthly_data[month_key] = {
                        "hp": 0.0,
                        "hc": 0.0,
                        "total": 0.0
                    }
                
                # Classer en HP ou HC selon le calendarTempClass
                if temp_class in ["HP", "HPB", "HPH"]:
                    monthly_data[month_key]["hp"] += consumption
                elif temp_class in ["HC", "HCB", "HCH"]:
                    monthly_data[month_key]["hc"] += consumption
                
                monthly_data[month_key]["total"] += consumption
                total_consumption += consumption
        
        return total_consumption, monthly_data

    @property
    def native_value(self) -> Optional[float]:
        """Return the cumulative electricity consumption."""
        total_consumption, _ = self._get_monthly_breakdown()
        return total_consumption

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return detailed monthly HP/HC breakdown."""
        total_consumption, monthly_data = self._get_monthly_breakdown()
        ledger = self._get_electricity_ledger()
        
        attributes = {
            "account_number": self.account_number,
            "total_consumption": round(total_consumption, 1),
            "last_update": datetime.now().strftime("%d %B %Y à %H:%M:%S")
        }
        
        # Ajouter les données mensuelles détaillées
        for month_key in sorted(monthly_data.keys(), reverse=True):
            month_data = monthly_data[month_key]
            attributes.update({
                f"Month {month_key} hp": round(month_data["hp"], 1),
                f"Month {month_key} hc": round(month_data["hc"], 1),
                f"Month {month_key}": round(month_data["total"], 1)
            })
        
        # Ajouter les infos du ledger si disponibles
        if ledger:
            attributes.update({
                "ledger_balance": ledger.get("balance", 0)
            })
            
            if meter_point := ledger.get("meterPoint"):
                attributes["meter_point_id"] = meter_point.get("external_identifier")
        
        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def icon(self) -> str:
        return "mdi:lightning-bolt"

class OctopusGasSensor(CoordinatorEntity, SensorEntity):
    """Gas sensor with monthly consumption breakdown."""
    
    def __init__(self, coordinator: OctopusDataUpdateCoordinator, account_number: str):
        super().__init__(coordinator)
        self.account_number = account_number
        
        self._attr_name = f"Gas Energy ({account_number})"
        self._attr_unique_id = f"{DOMAIN}_{account_number}_gas_energy"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_attribution = ATTRIBUTION

    def _get_gas_ledger(self) -> dict[str, Any] | None:
        """Récupère le ledger gaz depuis les données du coordinateur."""
        if not self.coordinator.data:
            return None
            
        for ledger in self.coordinator.data:
            if ledger.get("ledgerType") == "FRA_GAS_LEDGER":
                return ledger
        return None

    def _get_monthly_consumption(self) -> tuple[float, dict]:
        """Calcule la consommation mensuelle à partir des lectures."""
        ledger = self._get_gas_ledger()
        if not ledger or not ledger.get("additional_data", {}).get("readings"):
            return 0.0, {}
            
        readings = ledger["additional_data"]["readings"]
        monthly_data = {}
        total_consumption = 0.0
        
        for reading in readings:
            consumption = reading.get("consumption")
            reading_date = reading.get("readingDate")
            
            # Ignorer les lectures sans consommation ou sans date
            if consumption is None or not reading_date:
                continue
                
            # Ignorer les lectures de type "S" (souscription) qui ont souvent des valeurs aberrantes
            if reading.get("readingType") == "S":
                continue
                
            # Extraire le mois (format YYYY-MM)
            if len(reading_date) >= 7:
                month_key = reading_date[:7]
                
                if month_key not in monthly_data:
                    monthly_data[month_key] = 0.0
                
                monthly_data[month_key] += consumption
                total_consumption += consumption
        
        return total_consumption, monthly_data

    @property
    def native_value(self) -> Optional[float]:
        """Return the cumulative gas consumption."""
        total_consumption, _ = self._get_monthly_consumption()
        return total_consumption

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return detailed monthly consumption breakdown."""
        total_consumption, monthly_data = self._get_monthly_consumption()
        ledger = self._get_gas_ledger()
        
        attributes = {
            "account_number": self.account_number,
            "total_consumption": round(total_consumption, 1),
            "last_update": datetime.now().strftime("%d %B %Y à %H:%M:%S")
        }
        
        # Ajouter les données mensuelles détaillées
        for month_key in sorted(monthly_data.keys(), reverse=True):
            month_consumption = monthly_data[month_key]
            attributes[f"Month {month_key}"] = round(month_consumption, 1)
        
        # Ajouter les infos du ledger si disponibles (avec vérification null)
        if ledger:
            attributes.update({
                "ledger_balance": ledger.get("balance", 0)
            })
            
            # Vérification supplémentaire pour meterPoint
            meter_point = ledger.get("meterPoint")
            if meter_point:
                attributes["meter_point_id"] = meter_point.get("external_identifier")
        
        # Ajouter quelques statistiques sur les lectures (avec vérification null)
        if ledger and ledger.get("additional_data", {}).get("readings"):
            readings = ledger["additional_data"]["readings"]

            # Vérification que la liste n'est pas vide avant d'accéder aux éléments
            if readings:
                attributes["first_reading_date"] = readings[-1].get("readingDate")
                attributes["last_reading_date"] = readings[0].get("readingDate")
        
        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def icon(self) -> str:
        return "mdi:fire"