"""Switches for Octopus Intelligent features."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator: OctopusIntelligentDataUpdateCoordinator = (
        config_entry.runtime_data.intelligent_coordinator
    )

    if coordinator is None:
        return

    entities = [
        OctopusIntelligentBumpChargeSwitch(
            coordinator,
            device["id"],
            device.get("name", "Véhicule"),
        )
        for device in coordinator.data.get("devices", [])
        if device.get("id")
    ]

    if entities:
        async_add_entities(entities)


class OctopusIntelligentBumpChargeSwitch(CoordinatorEntity, SwitchEntity):
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
        self._attr_unique_id = f"{device_id}_bump_charge"
        self._attr_has_entity_name = True
        self._attr_translation_key = "bump_charge"
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
        """Return true if the switch is on."""
        device = self._get_device_status()
        status_data = device.get("status", {})
        current_state = status_data.get("currentState") or status_data.get("current")
        return current_state == "BOOSTING"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        device = self._get_device_status()
        status_data = device.get("status", {})
        return {
            "current": status_data.get("current"),
            "current_state": status_data.get("currentState"),
            "refusal_reasons": self.coordinator.data.get("boost_refusal_reasons", []),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _, refusal_reasons = await self.coordinator.intelligent_client.trigger_boost_charge(
            self._device_id
        )
        self.coordinator.data["boost_refusal_reasons"] = refusal_reasons
        if refusal_reasons and refusal_reasons != ["BC_BOOST_CHARGE_IN_PROGRESS"]:
            _LOGGER.warning(
                "Boost charge refused for device %s: %s",
                self._device_id,
                ", ".join(refusal_reasons),
            )
        else:
            await self.coordinator.async_refresh_devices()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _, refusal_reasons = await self.coordinator.intelligent_client.cancel_boost_charge(
            self._device_id
        )
        self.coordinator.data["boost_refusal_reasons"] = refusal_reasons
        if not refusal_reasons:
            await self.coordinator.async_refresh_devices()
        else:
            _LOGGER.warning(
                "Cancel boost charge for device %s: %s",
                self._device_id,
                ", ".join(refusal_reasons),
            )
