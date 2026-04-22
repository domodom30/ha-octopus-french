"""Number platform for Octopus Intelligent target SOC."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator: OctopusIntelligentDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["intelligent_coordinator"]

    devices = coordinator.data.get("devices", [])
    entities = []

    for device in devices:
        device_id = device.get("id")
        if not device_id:
            continue
        entities.append(
            OctopusIntelligentTargetSocNumber(
                coordinator,
                device_id,
                device.get("name", "Véhicule"),
            )
        )

    if entities:
        async_add_entities(entities)


class OctopusIntelligentTargetSocNumber(CoordinatorEntity, NumberEntity):
    """Number entity for target state of charge."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_target_soc"
        self._attr_name = "Charge cible"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current target SOC."""
        preferences = self.coordinator.data.get("preferences", {})
        return preferences.get("weekdayTargetSoc")

    async def async_set_native_value(self, value: float) -> None:
        """Set the target SOC."""
        preferences = self.coordinator.data.get("preferences", {})
        current_time = preferences.get("weekdayTargetTime", "07:00")

        success = await self.coordinator.intelligent_client.set_target_soc(
            self._device_id, int(value), current_time
        )
        if success:
            _LOGGER.info("Target SOC set to %d%% for device %s", int(value), self._device_id)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set target SOC for device %s", self._device_id)
