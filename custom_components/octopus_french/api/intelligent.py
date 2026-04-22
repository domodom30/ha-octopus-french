"""API client for Octopus Intelligent features."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..octopus_french import OctopusFrenchApiClient

MUTATION_UPDATE_BOOST_CHARGE = """
mutation {
  updateBoostCharge(input: { deviceId: "%s", action: %s }) {
    id
    name
  }
}
"""

QUERY_DEVICES = """
query {
  devices(accountNumber: "%s") {
    id
    name
    status {
      current
      currentState
    }
  }
}
"""

QUERY_VEHICLE_CHARGING_PREFERENCES = """
query {
  vehicleChargingPreferences(accountNumber: "%s") {
    weekdayTargetSoc
    weekdayTargetTime
    weekendTargetSoc
    weekendTargetTime
  }
}
"""

QUERY_FLEX_PLANNED_DISPATCHES = """
query {
  flexPlannedDispatches(deviceId: "%s") {
    start
    end
  }
}
"""

DAYS_OF_WEEK = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

MUTATION_SET_DEVICE_PREFERENCES = """
mutation {
  setDevicePreferences(input: {
    deviceId: "%s"
    mode: CHARGE
    unit: PERCENTAGE
    schedules: [
      %s
    ]
  }) {
    id
    preferences {
      schedules { dayOfWeek time max }
    }
  }
}
"""


class OctopusIntelligentApiClient:
    """Client for Octopus Intelligent API."""

    def __init__(self, api_client: OctopusFrenchApiClient) -> None:
        """Initialize the client."""
        self.api_client = api_client

    async def _update_boost_charge(self, device_id: str, action: str) -> tuple[dict[str, Any] | None, list[str]]:
        """Update boost charge (trigger or cancel). Returns (data, refusal_reasons)."""
        query = MUTATION_UPDATE_BOOST_CHARGE % (device_id, action)
        response = await self.api_client._execute_with_auth(query)

        refusal_reasons: list[str] = []
        if response and "errors" in response:
            for error in response.get("errors", []):
                extensions = error.get("extensions", {})
                refusal_reasons.extend(extensions.get("boostChargeRefusalReasons", []))

        data = response.get("data", {}).get("updateBoostCharge") if response else None
        return data, refusal_reasons

    async def trigger_boost_charge(self, device_id: str) -> tuple[dict[str, Any] | None, list[str]]:
        """Trigger boost charge. Returns (data, refusal_reasons)."""
        return await self._update_boost_charge(device_id, "BOOST")

    async def cancel_boost_charge(self, device_id: str) -> tuple[dict[str, Any] | None, list[str]]:
        """Cancel boost charge. Returns (data, refusal_reasons)."""
        return await self._update_boost_charge(device_id, "CANCEL")

    async def get_devices(self, account_number: str) -> list[dict[str, Any]]:
        """Get list of Intelligent devices for an account."""
        query = QUERY_DEVICES % account_number
        response = await self.api_client._execute_with_auth(query)
        return response.get("data", {}).get("devices", []) if response else []

    async def get_vehicle_charging_preferences(self, account_number: str) -> dict[str, Any]:
        """Get vehicle charging preferences for an account."""
        query = QUERY_VEHICLE_CHARGING_PREFERENCES % account_number
        response = await self.api_client._execute_with_auth(query)
        return response.get("data", {}).get("vehicleChargingPreferences", {}) if response else {}

    async def get_flex_planned_dispatches(self, device_id: str) -> list[dict[str, Any]]:
        """Get planned flex dispatch windows for a device."""
        query = QUERY_FLEX_PLANNED_DISPATCHES % device_id
        response = await self.api_client._execute_with_auth(query)
        return response.get("data", {}).get("flexPlannedDispatches", []) if response else []

    async def _send_device_preferences(
        self, device_id: str, target_time: str, target_soc: int
    ) -> bool:
        """Send device preferences mutation (same value for all 7 days)."""
        schedules = ", ".join(
            '{ dayOfWeek: %s, time: "%s", max: %d }' % (day, target_time, target_soc)
            for day in DAYS_OF_WEEK
        )
        query = MUTATION_SET_DEVICE_PREFERENCES % (device_id, schedules)
        response = await self.api_client._execute_with_auth(query)
        if response and "errors" in response:
            return False
        return response is not None and "data" in response

    async def set_target_soc(
        self, device_id: str, target_soc: int, current_time: str
    ) -> bool:
        """Set target state of charge, keeping current target time."""
        return await self._send_device_preferences(device_id, current_time, target_soc)

    async def set_target_time(
        self, device_id: str, target_time: str, current_soc: int
    ) -> bool:
        """Set target charging time, keeping current target SOC."""
        return await self._send_device_preferences(device_id, target_time, current_soc)


