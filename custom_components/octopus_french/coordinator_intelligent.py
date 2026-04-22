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
        self.api_client = api_client
        self.intelligent_client = OctopusIntelligentApiClient(api_client)
        self.account_number = account_number

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Return a device by its id."""
        for device in self.data.get("devices", []):
            if device.get("id") == device_id:
                return device
        return None

    def is_device_active(self, device_id: str) -> bool:
        """Return whether a device is currently charging."""
        status = self.get_device(device_id) or {}
        status_data = status.get("status", {})
        current_state = status_data.get("currentState") or status_data.get("current")
        return current_state in self.ACTIVE_CHARGING_STATES

    async def async_refresh_devices(self) -> None:
        """Refresh only device list, not all coordinator data."""
        try:
            devices = await self.intelligent_client.get_devices(self.account_number)
            if self.data:
                self.data["devices"] = devices
                _LOGGER.debug("Device list refreshed: %d devices", len(devices))
                self.async_set_updated_data(self.data)
        except Exception as err:
            _LOGGER.error("Error refreshing device list: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all intelligent data from API."""
        try:
            _LOGGER.info("Fetching intelligent data for account %s", self.account_number)
            devices = await self.intelligent_client.get_devices(self.account_number)
            _LOGGER.debug("Fetched %d devices", len(devices))

            preferences = await self.intelligent_client.get_vehicle_charging_preferences(
                self.account_number
            )
            _LOGGER.debug("Fetched preferences: %s", preferences)

            dispatches: dict[str, list[dict[str, Any]]] = {}
            for device in devices:
                device_id = device.get("id")
                if not device_id:
                    continue
                device_dispatches = await self.intelligent_client.get_flex_planned_dispatches(device_id)
                dispatches[device_id] = device_dispatches
                _LOGGER.debug("Fetched dispatches for device %s: %d dispatches", device_id, len(device_dispatches))

            result = {
                "devices": devices,
                "preferences": preferences,
                "dispatches": dispatches,
                "boost_refusal_reasons": [],
            }
            _LOGGER.info("Intelligent data update complete: %d devices", len(devices))
            return result
        except Exception as err:
            _LOGGER.error("Error communicating with Intelligent API: %s", err)
            raise UpdateFailed(f"Error communicating with Intelligent API: {err}") from err
