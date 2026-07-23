"""Switches for Octopus Intelligent features."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up the switches."""
    coordinator = config_entry.runtime_data.intelligent_coordinator

    if coordinator is None:
        return

    entities: list[SwitchEntity] = []
    for device in coordinator.data.get("devices", []):
        device_id = device.get("id")
        if not device_id:
            continue
        device_name = device.get("name", "Véhicule")
        entities.append(
            OctopusIntelligentBumpChargeSwitch(coordinator, device_id, device_name)
        )
        entities.append(
            OctopusIntelligentSmartControlSwitch(coordinator, device_id, device_name)
        )

    if entities:
        async_add_entities(entities)


class OctopusIntelligentBumpChargeSwitch(
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SwitchEntity
):
    """Switch for boost charge."""

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_bump_charge"
        self._attr_has_entity_name = True
        self._attr_translation_key = "bump_charge"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )
        self._update_attrs()

    def _get_device_status(self) -> dict[str, Any]:
        """Return the device payload from coordinator data."""
        return self.coordinator.get_device(self._device_id) or {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        device = self._get_device_status()
        status_data = device.get("status", {})
        current_state = status_data.get("currentState") or status_data.get("current")
        self._attr_is_on = current_state == "BOOSTING"
        self._attr_extra_state_attributes = {
            "current": status_data.get("current"),
            "current_state": status_data.get("currentState"),
            "refusal_reasons": self.coordinator.data.get("boost_refusal_reasons", []),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        (
            _,
            refusal_reasons,
        ) = await self.coordinator.intelligent_client.trigger_boost_charge(
            self._device_id
        )
        self.coordinator.data["boost_refusal_reasons"] = refusal_reasons
        self.coordinator.async_set_updated_data(self.coordinator.data)
        if refusal_reasons and refusal_reasons != ["BC_BOOST_CHARGE_IN_PROGRESS"]:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="boost_charge_refused",
                translation_placeholders={"reasons": ", ".join(refusal_reasons)},
            )
        await self.coordinator.async_refresh_devices()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        (
            _,
            refusal_reasons,
        ) = await self.coordinator.intelligent_client.cancel_boost_charge(
            self._device_id
        )
        self.coordinator.data["boost_refusal_reasons"] = refusal_reasons
        self.coordinator.async_set_updated_data(self.coordinator.data)
        if refusal_reasons:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cancel_boost_charge_failed",
                translation_placeholders={"reasons": ", ".join(refusal_reasons)},
            )
        await self.coordinator.async_refresh_devices()


class OctopusIntelligentSmartControlSwitch(
    CoordinatorEntity[OctopusIntelligentDataUpdateCoordinator], SwitchEntity
):
    """Switch to suspend/restore Octopus's automatic smart control of a device.

    Unlike boost charge, suspending smart control does not incur the
    Intelligent tariff's boost-usage cost. It stops Octopus from
    interrupting a charging session it did not schedule itself, at the
    cost of losing Octopus's own schedule optimisation while suspended.
    """

    def __init__(
        self,
        coordinator: OctopusIntelligentDataUpdateCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_smart_control"
        self._attr_has_entity_name = True
        self._attr_translation_key = "smart_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            via_device=(DOMAIN, coordinator.account_number),
            name=device_name,
            model=device_name,
        )

    def _get_device_status(self) -> dict[str, Any]:
        """Return the device payload from coordinator data."""
        return self.coordinator.get_device(self._device_id) or {}

    @property
    def is_on(self) -> bool:
        """Return true if Octopus's automatic smart control is active (not suspended)."""
        status_data = self._get_device_status().get("status", {})
        return not status_data.get("isSuspended", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Restore Octopus's automatic smart control."""
        success = await self.coordinator.intelligent_client.unsuspend_smart_control(
            self._device_id
        )
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_smart_control_failed",
                translation_placeholders={"device_id": self._device_id},
            )
        await self.coordinator.async_refresh_devices()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Suspend Octopus's automatic smart control."""
        success = await self.coordinator.intelligent_client.suspend_smart_control(
            self._device_id
        )
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_smart_control_failed",
                translation_placeholders={"device_id": self._device_id},
            )
        await self.coordinator.async_refresh_devices()
