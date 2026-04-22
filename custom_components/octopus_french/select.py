"""Select platform for Octopus Intelligent target charging time."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
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
            OctopusIntelligentTargetTimeSelect(
                coordinator,
                device_id,
                device.get("name", "Véhicule"),
            )
        )

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
        self._attr_name = "Heure cible"
        self._attr_has_entity_name = True
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
            _LOGGER.info("Target time set to %s for device %s", option, self._device_id)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set target time for device %s", self._device_id)
