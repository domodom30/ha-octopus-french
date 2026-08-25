"""Data update coordinator for Octopus Intelligent features."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.intelligent import OctopusIntelligentApiClient
from .const import INTELLIGENT_SCAN_INTERVAL
from .octopus_french import OctopusAuthError, OctopusConnectionError

if TYPE_CHECKING:
    from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)

_WEEKEND_DAYS = frozenset({"SATURDAY", "SUNDAY"})


def _normalise_target_time(value: Any) -> Any:
    """Ramène une heure `Time` GraphQL au format HH:MM des options du select."""
    if isinstance(value, str) and value.count(":") >= 2:
        return value[:5]
    return value


def preferences_from_schedules(preferences: dict[str, Any] | None) -> dict[str, Any]:
    """
    Convertit les `schedules` d'un appareil en cibles semaine / week-end.

    L'API expose un créneau par jour ; les entités raisonnent en semaine et
    week-end, comme le faisait vehicleChargingPreferences. Le premier créneau
    rencontré de chaque groupe fait foi.
    """
    result: dict[str, Any] = {}
    for schedule in (preferences or {}).get("schedules") or []:
        day = (schedule.get("dayOfWeek") or "").upper()
        prefix = "weekend" if day in _WEEKEND_DAYS else "weekday"
        if f"{prefix}TargetTime" in result:
            continue
        result[f"{prefix}TargetTime"] = _normalise_target_time(schedule.get("time"))
        result[f"{prefix}TargetSoc"] = schedule.get("max")
    return result


class OctopusIntelligentDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Intelligent API."""

    ACTIVE_CHARGING_STATES: ClassVar[set[str]] = {
        "BOOSTING",
        "SMART_CONTROL_IN_PROGRESS",
        "TEST_CHARGE_IN_PROGRESS",
    }

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OctopusFrenchApiClient,
        account_number: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Octopus Intelligent",
            update_interval=timedelta(minutes=INTELLIGENT_SCAN_INTERVAL),
            config_entry=config_entry,
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

    def get_preferences(self, device_id: str) -> dict[str, Any]:
        """
        Préférences de charge d'un appareil.

        Les valeurs propres à l'appareil priment ; celles du compte servent de
        repli pour les comptes dont les appareils n'exposent pas de `schedules`.
        """
        data = self.data or {}
        account_preferences = data.get("preferences") or {}
        device_preferences = (data.get("device_preferences") or {}).get(device_id) or {}
        return {
            **account_preferences,
            **{k: v for k, v in device_preferences.items() if v is not None},
        }

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
        except (OctopusAuthError, OctopusConnectionError, RuntimeError) as err:
            _LOGGER.error("Error refreshing device list: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all intelligent data from API."""
        try:
            devices = await self.intelligent_client.get_devices(self.account_number)

            preferences: dict[str, Any] = {}
            dispatches: dict[str, list[dict[str, Any]]] = {}

            if devices:
                device_ids = [
                    device_id for device in devices if (device_id := device.get("id"))
                ]
                preferences, dispatch_lists = await asyncio.gather(
                    self.intelligent_client.get_vehicle_charging_preferences(
                        self.account_number
                    ),
                    asyncio.gather(
                        *(
                            self.intelligent_client.get_flex_planned_dispatches(
                                device_id
                            )
                            for device_id in device_ids
                        )
                    ),
                )
                dispatches = dict(zip(device_ids, dispatch_lists, strict=True))

            return {
                "devices": devices,
                "preferences": preferences,
                "device_preferences": {
                    device_id: preferences_from_schedules(device.get("preferences"))
                    for device in devices
                    if (device_id := device.get("id"))
                },
                "dispatches": dispatches,
                "boost_refusal_reasons": [],
            }
        except OctopusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (OctopusConnectionError, RuntimeError) as err:
            raise UpdateFailed(
                f"Error communicating with Intelligent API: {err}"
            ) from err
