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
    """Configuration des capteurs Octopus Energy French."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    account_number = data[CONF_ACCOUNT_NUMBER]

    LOGGER.debug("Démarrage de la configuration des capteurs pour le compte %s", account_number)

    # Actualisation des données du coordinateur
    await coordinator.async_request_refresh()
    
    sensors: list[SensorEntity] = []
    created_sensors = set()

    # Vérification du format des données
    if not coordinator.data or not isinstance(coordinator.data, list):
        LOGGER.error("Format de données invalide pour le compte %s", account_number)
        return

    # Création des capteurs basés sur les types de ledger disponibles
    for ledger_type, config in SUPPORTED_LEDGER_TYPES.items():
        
        # Recherche du solde dans les données
        balance = 0
        for ledger in coordinator.data:
            if isinstance(ledger, dict) and ledger.get("ledgerType") == ledger_type:
                balance = ledger.get("balance", 0)
                break

        # Gestion des doublons et soldes à zéro
        sensor_id = f"{ledger_type}_{account_number}"
        if sensor_id in created_sensors:
            continue
        if balance == 0 and not config.get("create_if_zero", False):
            continue
        if not config.get("create_sensor", True):
            continue

        # Création du capteur approprié
        if ledger_type == "POT_LEDGER":
            sensors.append(OctopusPotSensor(coordinator, account_number))
        elif ledger_type == "FRA_ELECTRICITY_LEDGER":
            sensors.append(OctopusElectricitySensor(coordinator, account_number))
        elif ledger_type == "FRA_GAS_LEDGER":
            sensors.append(OctopusGasSensor(coordinator, account_number))
        
        created_sensors.add(sensor_id)

    async_add_entities(sensors, True)
    LOGGER.info("%d capteurs créés pour le compte %s", len(sensors), account_number)


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

    def _get_pot_balance(self) -> float:
        """Récupère le solde de la cagnotte de manière sécurisée."""
        try:
            if not self.coordinator.data or not isinstance(self.coordinator.data, list):
                return 0.0
                
            for ledger in self.coordinator.data:
                if isinstance(ledger, dict) and ledger.get("ledgerType") == "POT_LEDGER":
                    balance = ledger.get("balance", 0)
                    return round(balance / 100, 2)
            return 0.0
        except (TypeError, ValueError, AttributeError) as e:
            LOGGER.error("Erreur lors de la récupération du solde de la cagnotte: %s", e)
            return 0.0

    @property
    def native_value(self) -> float:
        """Return the current pot balance."""
        return self._get_pot_balance()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        balance_raw = 0
        try:
            if self.coordinator.data and isinstance(self.coordinator.data, list):
                for ledger in self.coordinator.data:
                    if isinstance(ledger, dict) and ledger.get("ledgerType") == "POT_LEDGER":
                        balance_raw = ledger.get("balance", 0)
                        break
        except (TypeError, AttributeError) as e:
            LOGGER.error("Erreur lors de l'extraction des attributs de la cagnotte: %s", e)

        return {
            "account_number": self.account_number,
            "currency": CURRENCY_EURO,
            "balance_raw": balance_raw,
            "balance_euros": self.native_value,
            "last_update": datetime.now().isoformat()
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

    def _validate_reading_data(self, reading: dict) -> bool:
        """Valide la structure des données de lecture."""
        required_fields = {"consumption", "periodEndAt"}
        return all(field in reading for field in required_fields)

    def _extract_month_key(self, date_string: str) -> str | None:
        """Extrait la clé de mois de manière sécurisée."""
        try:
            if date_string and len(date_string) >= 7:
                return date_string[:7]
        except (TypeError, IndexError):
            pass
        return None

    def _get_electricity_ledger(self) -> dict[str, Any] | None:
        """Récupère le ledger électrique de manière sécurisée."""
        try:
            if not self.coordinator.data or not isinstance(self.coordinator.data, list):
                return None
                
            for ledger in self.coordinator.data:
                if isinstance(ledger, dict) and ledger.get("ledgerType") == "FRA_ELECTRICITY_LEDGER":
                    return ledger
            return None
        except (TypeError, AttributeError) as e:
            LOGGER.error("Erreur lors du traitement des données électriques: %s", e)
            return None

    def _get_monthly_breakdown(self) -> tuple[float, dict]:
        """Calcule la ventilation mensuelle HP/HC et le total global."""
        ledger = self._get_electricity_ledger()
        if not ledger or not isinstance(ledger.get("additional_data", {}).get("readings"), list):
            return 0.0, {}
            
        readings = ledger["additional_data"]["readings"]
        monthly_data = {}
        total_consumption = 0.0
        
        for reading in readings:
            if not self._validate_reading_data(reading):
                continue
                
            consumption = reading.get("consumption")
            period_end = reading.get("periodEndAt")
            temp_class = reading.get("calendarTempClass", "").upper()
            
            if consumption is not None and period_end:
                month_key = self._extract_month_key(period_end)
                if not month_key:
                    continue
                
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
                else:
                    # Par défaut, considérer comme HP si non spécifié
                    monthly_data[month_key]["hp"] += consumption
                
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
        """Return detailed monthly HP/HC breakdown with safe data handling."""
        try:
            total_consumption, monthly_data = self._get_monthly_breakdown()
            ledger = self._get_electricity_ledger()
            
            attributes = {
                "account_number": self.account_number,
                "total_consumption": round(total_consumption, 1) if total_consumption is not None else 0,
                "last_update": datetime.now().isoformat()
            }
            
            # Traitement sécurisé des données mensuelles
            if monthly_data:
                for month_key in sorted(monthly_data.keys(), reverse=True)[:12]:  # Limite à 12 mois
                    month_data = monthly_data[month_key]
                    attributes.update({
                        f"{month_key}_hp": round(month_data.get("hp", 0), 1),
                        f"{month_key}_hc": round(month_data.get("hc", 0), 1),
                        f"{month_key}_total": round(month_data.get("total", 0), 1)
                    })
            
            # Extraction sécurisée des infos du ledger
            if ledger:
                attributes["ledger_balance"] = ledger.get("balance", 0)
                
                if meter_point := ledger.get("meterPoint"):
                    if isinstance(meter_point, dict) and (meter_id := meter_point.get("external_identifier")):
                        attributes["meter_point_id"] = meter_id
            
            return attributes
            
        except Exception as e:
            LOGGER.error("Erreur lors de la génération des attributs électriques: %s", e)
            return {"error": "Erreur de traitement des données", "account_number": self.account_number}

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

    def _validate_reading_data(self, reading: dict) -> bool:
        """Valide la structure des données de lecture gaz."""
        required_fields = {"consumption", "readingDate"}
        return all(field in reading for field in required_fields)

    def _extract_month_key(self, date_string: str) -> str | None:
        """Extrait la clé de mois de manière sécurisée."""
        try:
            if date_string and len(date_string) >= 7:
                return date_string[:7]
        except (TypeError, IndexError):
            pass
        return None

    def _get_gas_ledger(self) -> dict[str, Any] | None:
        """Récupère le ledger gaz de manière sécurisée."""
        try:
            if not self.coordinator.data or not isinstance(self.coordinator.data, list):
                return None
                
            for ledger in self.coordinator.data:
                if isinstance(ledger, dict) and ledger.get("ledgerType") == "FRA_GAS_LEDGER":
                    return ledger
            return None
        except (TypeError, AttributeError) as e:
            LOGGER.error("Erreur lors du traitement des données gaz: %s", e)
            return None

    def _get_monthly_consumption(self) -> tuple[float, dict]:
        """Calcule la consommation mensuelle à partir des lectures."""
        ledger = self._get_gas_ledger()
        if not ledger or not isinstance(ledger.get("additional_data", {}).get("readings"), list):
            return 0.0, {}
            
        readings = ledger["additional_data"]["readings"]
        monthly_data = {}
        total_consumption = 0.0
        
        for reading in readings:
            if not self._validate_reading_data(reading):
                continue
                
            consumption = reading.get("consumption")
            reading_date = reading.get("readingDate")
            
            # Ignorer les lectures de type "S" (souscription)
            if reading.get("readingType") == "S":
                continue
                
            if consumption is not None and reading_date:
                month_key = self._extract_month_key(reading_date)
                if not month_key:
                    continue
                
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
        try:
            total_consumption, monthly_data = self._get_monthly_consumption()
            ledger = self._get_gas_ledger()
            
            attributes = {
                "account_number": self.account_number,
                "total_consumption": round(total_consumption, 1) if total_consumption is not None else 0,
                "last_update": datetime.now().isoformat()
            }
            
            # Ajouter les données mensuelles détaillées
            if monthly_data:
                for month_key in sorted(monthly_data.keys(), reverse=True)[:12]:  # Limite à 12 mois
                    month_consumption = monthly_data[month_key]
                    attributes[f"{month_key}"] = round(month_consumption, 1)
            
            # Ajouter les infos du ledger si disponibles
            if ledger:
                attributes["ledger_balance"] = ledger.get("balance", 0)
                
                if meter_point := ledger.get("meterPoint"):
                    if isinstance(meter_point, dict) and (meter_id := meter_point.get("external_identifier")):
                        attributes["meter_point_id"] = meter_id
            
            # Ajouter des statistiques sur les lectures
            if ledger and isinstance(ledger.get("additional_data", {}).get("readings"), list):
                readings = ledger["additional_data"]["readings"]
                if readings:
                    # Filtrer les lectures valides
                    valid_readings = [r for r in readings if self._validate_reading_data(r)]
                    if valid_readings:
                        attributes["first_reading_date"] = valid_readings[-1].get("readingDate")
                        attributes["last_reading_date"] = valid_readings[0].get("readingDate")
                        attributes["reading_count"] = len(valid_readings)
            
            return attributes
            
        except Exception as e:
            LOGGER.error("Erreur lors de la génération des attributs gaz: %s", e)
            return {"error": "Erreur de traitement des données", "account_number": self.account_number}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def icon(self) -> str:
        return "mdi:fire"