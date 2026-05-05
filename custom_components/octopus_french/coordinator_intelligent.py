"""Data update coordinator for Octopus Intelligent features."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.intelligent import OctopusIntelligentApiClient

if TYPE_CHECKING:
    from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)


class OctopusIntelligentDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Intelligent API."""

    ACTIVE_CHARGING_STATES = {
        "BOOSTING",
        "SMART_CONTROL_IN_PROGRESS",
        "TEST_CHARGE_IN_PROGRESS",
    }

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OctopusFrenchApiClient,
        account_number: str,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Octopus Intelligent",
            update_interval=timedelta(minutes=1),
        )
        self.intelligent_client = OctopusIntelligentApiClient(api_client)
        self.account_number = account_number

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Return a device by its id."""
        if not self.data:
            return None
        for device in self.data.get("devices", []):
            if device.get("id") == device_id:
                return device
        return None

    def is_device_active(self, device_id: str) -> bool:
        """Return whether a device is currently charging."""
        device = self.get_device(device_id) or {}
        status_data = device.get("status", {})
        current_state = status_data.get("currentState") or status_data.get("current")
        return current_state in self.ACTIVE_CHARGING_STATES

    async def async_refresh_devices(self) -> None:
        """Refresh only device list, not all coordinator data."""
        try:
            devices = await self.intelligent_client.get_devices(self.account_number)
            if self.data is not None:
                self.data["devices"] = devices
                self.async_set_updated_data(self.data)
        except Exception as err:
            _LOGGER.error("Error refreshing device list: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all intelligent data from API."""
        try:
            devices = await self.intelligent_client.get_devices(self.account_number)

            preferences: dict[str, Any] = {}
            dispatches: dict[str, list[dict[str, Any]]] = {}

            if devices:
                preferences = await self.intelligent_client.get_vehicle_charging_preferences(
                    self.account_number
                )
                for device in devices:
                    device_id = device.get("id")
                    if not device_id:
                        continue
                    dispatches[device_id] = (
                        await self.intelligent_client.get_flex_planned_dispatches(device_id)
                    )

            return {
                "devices": devices,
                "preferences": preferences,
                "dispatches": dispatches,
                "boost_refusal_reasons": [],
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Intelligent API: {err}") from err
