"""Select platform for Octopus Intelligent target charging time."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OctopusFrenchConfigEntry
from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

PARALLEL_UPDATES = 0

TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OctopusFrenchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator = config_entry.runtime_data.intelligent_coordinator

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


class OctopusIntelligentTargetTimeSelect(
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SelectEntity
):
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
        self._attr_unique_id = f"{DOMAIN}_{device_id}_target_time"
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
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        preferences = self.coordinator.data.get("preferences", {})
        self._attr_current_option = preferences.get("weekdayTargetTime")

    async def async_select_option(self, option: str) -> None:
        """Set the target time."""
        preferences = self.coordinator.data.get("preferences", {})
        current_soc = preferences.get("weekdayTargetSoc", 100)

        success = await self.coordinator.intelligent_client.set_target_time(
            self._device_id, option, current_soc
        )
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_target_time_failed",
                translation_placeholders={"device_id": self._device_id},
            )
        await self.coordinator.async_request_refresh()
