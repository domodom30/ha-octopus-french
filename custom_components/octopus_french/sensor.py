"""Sensor platform for Octopus Energy France."""

import json
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    TARIFF_TYPE_TEMPO,
    TEMPO_PRODUCT_CODE_KEYWORDS,
    TEMPO_STATISTICS_LABELS,
    TEMPO_TEMPORAL_CLASS_CODES,
)
from .coordinator import OctopusFrenchDataUpdateCoordinator
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator
from .sensors.descriptions import (
    ELECTRICITY_INDEX_SENSORS,
    ELECTRICITY_SENSORS,
    GAS_SENSORS,
    LATEST_READING_SENSOR,
    LEDGER_SENSORS,
    TEMPO_SENSORS,
)
from .sensors.electricity import (
    OctopusElectricityIndexSensor,
    OctopusElectricitySensor,
    OctopusLatestReadingSensor,
    OctopusTempoColorSensor,
    OctopusTempoCurrentRateSensor,
)
from .sensors.gas import OctopusGasSensor
from .sensors.ledger import OctopusLedgerSensor

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Energy France sensors."""
    coordinator: OctopusFrenchDataUpdateCoordinator = entry.runtime_data.coordinator
    account_number = entry.runtime_data.account_number

    entities = []
    supply_points = coordinator.data.get("supply_points", {})
    ledgers = coordinator.data.get("ledgers", {})

    if ledgers:
        entities.extend(
            OctopusLedgerSensor(coordinator, account_number, sensor_config)
            for sensor_config in LEDGER_SENSORS
            if sensor_config.ledger_type in ledgers
        )

    for elec_meter in supply_points.get("electricity", []):
        if (
            elec_meter.get("distributorStatus") == "RESIL"
            and elec_meter.get("poweredStatus") == "LIMI"
        ):
            continue

        prm_id = elec_meter.get("prm")
        tariff_type = _detect_tariff_type_for_meter(coordinator.data, prm_id)

        for sensor_config in ELECTRICITY_SENSORS:
            sensor_key = sensor_config.key

            if (
                sensor_key in {"contract", "subscription", "subscribed_power"}
                or (
                    tariff_type == "BASE"
                    and sensor_key in ["energy_base", "cost_base", "rate_base"]
                )
                or (
                    tariff_type == "HPHC"
                    and sensor_key
                    in [
                        "energy_peak_hours",
                        "energy_off_peak_hours",
                        "cost_peak_hours",
                        "cost_off_peak_hours",
                        "rate_peak_hours",
                        "rate_off_peak_hours",
                    ]
                )
            ):
                entities.append(
                    OctopusElectricitySensor(coordinator, prm_id, sensor_config)
                )

        if tariff_type == TARIFF_TYPE_TEMPO:
            for sensor_config in TEMPO_SENSORS:
                if sensor_config.key == "tempo_color_today":
                    entities.append(
                        OctopusTempoColorSensor(
                            coordinator, prm_id, sensor_config, is_tomorrow=False
                        )
                    )
                elif sensor_config.key == "tempo_color_tomorrow":
                    entities.append(
                        OctopusTempoColorSensor(
                            coordinator, prm_id, sensor_config, is_tomorrow=True
                        )
                    )
                elif sensor_config.key == "tempo_current_rate":
                    entities.append(
                        OctopusTempoCurrentRateSensor(
                            coordinator, prm_id, sensor_config
                        )
                    )
                else:
                    entities.append(
                        OctopusElectricitySensor(coordinator, prm_id, sensor_config)
                    )

        entities.append(
            OctopusLatestReadingSensor(coordinator, prm_id, LATEST_READING_SENSOR)
        )

        index_data = (
            coordinator.data.get("electricity_by_prm", {}).get(prm_id, {}).get("index")
        )
        if index_data:
            index_tariff_type = index_data.get("tariff_type")

            for index_config in ELECTRICITY_INDEX_SENSORS:
                index_type = index_config.index_type

                if not index_type:
                    continue

                if index_tariff_type == TARIFF_TYPE_TEMPO:
                    continue

                if (index_tariff_type == "BASE" and index_type == "base") or (
                    index_tariff_type == "HPHC" and index_type in ["hp", "hc"]
                ):
                    entities.append(
                        OctopusElectricityIndexSensor(coordinator, prm_id, index_config)
                    )

    entities.extend(
        OctopusGasSensor(coordinator, gas_meter.get("prm"), sensor_config)
        for gas_meter in supply_points.get("gas", [])
        for sensor_config in GAS_SENSORS
    )

    intelligent_coordinator: OctopusIntelligentDataUpdateCoordinator | None = (
        entry.runtime_data.intelligent_coordinator
    )
    if intelligent_coordinator and intelligent_coordinator.data:
        for device in intelligent_coordinator.data.get("devices", []):
            device_id = device.get("id")
            if not device_id:
                continue
            device_name = device.get("name", "Véhicule")
            entities.extend(
                [
                    OctopusIntelligentVehicleStatusSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                    OctopusIntelligentWeekdayTargetSocSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                    OctopusIntelligentWeekdayTargetTimeSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                    OctopusIntelligentWeekendTargetSocSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                    OctopusIntelligentWeekendTargetTimeSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                    OctopusIntelligentPlannedDispatchesSensor(
                        intelligent_coordinator, device_id, device_name
                    ),
                ]
            )

    async_add_entities(entities)


def _detect_tariff_type_for_meter(data: dict, prm_id: str) -> str:
    """Détecte le type de tarif pour un compteur spécifique."""
    try:
        for meter in data.get("supply_points", {}).get("electricity", []):
            if meter.get("prm") != prm_id:
                continue
            classes = meter.get("provider_temporal_classes") or []
            codes = {c.get("code") for c in classes if c.get("code")}
            if codes & TEMPO_TEMPORAL_CLASS_CODES:
                return TARIFF_TYPE_TEMPO
            if len(codes) == 2:
                return "HPHC"
            if len(codes) == 1:
                return "BASE"

        electricity_readings = (
            data.get("electricity_by_prm", {}).get(prm_id, {}).get("readings", [])
        )
        if electricity_readings:
            latest_reading = electricity_readings[-1]
            statistics = (latest_reading.get("metaData") or {}).get("statistics", [])
            if statistics:
                labels = {stat.get("label", "") for stat in statistics}
                if labels & TEMPO_STATISTICS_LABELS:
                    return TARIFF_TYPE_TEMPO
                if "BASE" in labels:
                    return "BASE"
                if "HEURES_PLEINES" in labels and "HEURES_CREUSES" in labels:
                    return "HPHC"

        for agreement in data.get("agreements", []):
            if agreement.get("prm") == prm_id and agreement.get("is_active"):
                code = ((agreement.get("product") or {}).get("code") or "").upper()
                if any(kw in code for kw in TEMPO_PRODUCT_CODE_KEYWORDS):
                    return TARIFF_TYPE_TEMPO

        index = data.get("electricity_by_prm", {}).get(prm_id, {}).get("index") or {}
        tariff_type = index.get("tariff_type")
        if tariff_type in ("BASE", "HPHC", TARIFF_TYPE_TEMPO):
            return tariff_type

    except (KeyError, IndexError, TypeError) as e:
        _LOGGER.debug("Erreur détection tarif %s: %s", prm_id, e)
    return "UNKNOWN"


class OctopusIntelligentVehicleStatusSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for vehicle charging status."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_vehicle_status"
        self._attr_has_entity_name = True
        self._attr_translation_key = "vehicle_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    def _device_data(self) -> dict[str, Any]:
        return self.coordinator.get_device(self._device_id) or {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        device = self._device_data()
        status = device.get("status", {})
        self._attr_native_value = status.get("currentState") or status.get("current")
        self._attr_extra_state_attributes = {
            "device_id": self._device_id,
            "name": device.get("name"),
            "current": status.get("current"),
        }


class OctopusIntelligentWeekdayTargetSocSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for weekday target state of charge."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_weekday_target_soc"
        self._attr_has_entity_name = True
        self._attr_translation_key = "weekday_target_soc"
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self.coordinator.data.get("preferences", {}).get(
            "weekdayTargetSoc"
        )


class OctopusIntelligentWeekdayTargetTimeSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for weekday target charging time."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_weekday_target_time"
        self._attr_has_entity_name = True
        self._attr_translation_key = "weekday_target_time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self.coordinator.data.get("preferences", {}).get(
            "weekdayTargetTime"
        )


class OctopusIntelligentWeekendTargetSocSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for weekend target state of charge."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_weekend_target_soc"
        self._attr_has_entity_name = True
        self._attr_translation_key = "weekend_target_soc"
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self.coordinator.data.get("preferences", {}).get(
            "weekendTargetSoc"
        )


class OctopusIntelligentWeekendTargetTimeSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for weekend target charging time."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_weekend_target_time"
        self._attr_has_entity_name = True
        self._attr_translation_key = "weekend_target_time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self.coordinator.data.get("preferences", {}).get(
            "weekendTargetTime"
        )


class OctopusIntelligentPlannedDispatchesSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SensorEntity
):
    """Sensor for planned charging dispatches."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_planned_dispatches"
        self._attr_has_entity_name = True
        self._attr_translation_key = "planned_dispatches"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _format_dispatch(self, timestamp: str | None) -> str | None:
        if not timestamp:
            return None
        dt = dt_util.parse_datetime(timestamp)
        if not dt:
            return timestamp
        return dt_util.as_local(dt).strftime("%d/%m %H:%M")

    def _calculate_duration(self, dispatch: dict) -> int | None:
        try:
            start_dt = dt_util.parse_datetime(dispatch.get("start") or "")
            end_dt = dt_util.parse_datetime(dispatch.get("end") or "")
            if not start_dt or not end_dt:
                return None
            return int((end_dt - start_dt).total_seconds() / 60)
        except (ValueError, AttributeError, TypeError):
            return None

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self._compute_native_value()
        self._attr_extra_state_attributes = self._compute_attributes()

    def _compute_native_value(self) -> str | None:
        """Return a summary of the planned charging dispatches."""
        dispatches = self.coordinator.data.get("dispatches", {}).get(
            self._device_id, []
        )
        if not dispatches:
            return "Aucune"
        n = len(dispatches)
        return f"{n} programmée{'s' if n > 1 else ''}"

    def _compute_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        dispatches = self.coordinator.data.get("dispatches", {}).get(
            self._device_id, []
        )
        formatted = [
            f"{self._format_dispatch(d.get('start'))} → {self._format_dispatch(d.get('end'))}"
            for d in dispatches
            if d.get("start") and d.get("end")
        ]
        dispatches_detail = [
            {
                "start": d.get("start"),
                "end": d.get("end"),
                "start_local": self._format_dispatch(d.get("start")),
                "end_local": self._format_dispatch(d.get("end")),
                "duration_minutes": self._calculate_duration(d),
            }
            for d in dispatches
        ]
        return {
            "count": len(dispatches),
            "has_dispatches": len(dispatches) > 0,
            "next_dispatch": dispatches[0] if dispatches else None,
            "formatted_list": formatted,
            "summary": "\n".join(formatted)
            if formatted
            else "Aucune fenêtre programmée",
            "dispatches_json": json.dumps(
                dispatches_detail, ensure_ascii=False, indent=2
            ),
        }
