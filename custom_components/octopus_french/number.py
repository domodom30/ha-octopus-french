"""Number platform for Octopus Intelligent target state of charge."""

from homeassistant.components.number import NumberEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OctopusFrenchConfigEntry
from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OctopusFrenchConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = config_entry.runtime_data.intelligent_coordinator

    if coordinator is None:
        return

    entities = [
        OctopusIntelligentTargetSocNumber(
            coordinator,
            device["id"],
            device.get("name", "Véhicule"),
        )
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    ]

    if entities:
        async_add_entities(entities)


class OctopusIntelligentTargetSocNumber(
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], NumberEntity
):
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
        self._attr_unique_id = f"{DOMAIN}_{device_id}_target_soc"
        self._attr_has_entity_name = True
        self._attr_translation_key = "target_soc"
        self._attr_icon = "mdi:battery-charging"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 5.0
        self._attr_native_unit_of_measurement = PERCENTAGE
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
        value = preferences.get("weekdayTargetSoc")
        self._attr_native_value = float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the target SOC."""
        preferences = self.coordinator.data.get("preferences", {})
        current_time = preferences.get("weekdayTargetTime", "07:00")

        success = await self.coordinator.intelligent_client.set_target_soc(
            self._device_id, int(value), current_time
        )
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_target_soc_failed",
                translation_placeholders={"device_id": self._device_id},
            )
        await self.coordinator.async_request_refresh()
