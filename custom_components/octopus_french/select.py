"""Select platform for Octopus Intelligent target charging time."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: OctopusIntelligentDataUpdateCoordinator = (
        config_entry.runtime_data.intelligent_coordinator
    )

    if coordinator is None:
        return

    entities = [
        OctopusIntelligentTargetTimeSelect(
            coordinator,
            device["id"],
            device.get("name", "Véhicule"),
        )
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    ]

    if entities:
        async_add_entities(entities)


class OctopusIntelligentTargetTimeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for target charging time (30-minute intervals)."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_target_time"
        self._attr_has_entity_name = True
        self._attr_translation_key = "target_time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_options = TIME_OPTIONS
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )

    @property
    def current_option(self) -> str | None:
        """Return the current target time."""
        preferences = self.coordinator.data.get("preferences", {})
        return preferences.get("weekdayTargetTime")

    async def async_select_option(self, option: str) -> None:
        """Set the target time."""
        preferences = self.coordinator.data.get("preferences", {})
        current_soc = preferences.get("weekdayTargetSoc", 100)

        success = await self.coordinator.intelligent_client.set_target_time(
            self._device_id, option, current_soc
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set target time for device %s", self._device_id)
