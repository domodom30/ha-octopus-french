"""API client for Octopus Intelligent features."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..octopus_french import OctopusFrenchApiClient

MUTATION_TRIGGER_BOOST_CHARGE = """
mutation updateBoostCharge($deviceId: String!) {
  updateBoostCharge(input: { deviceId: $deviceId, action: BOOST }) {
    id
    name
  }
}
"""

MUTATION_CANCEL_BOOST_CHARGE = """
mutation updateBoostCharge($deviceId: String!) {
  updateBoostCharge(input: { deviceId: $deviceId, action: CANCEL }) {
    id
    name
  }
}
"""

MUTATION_UPDATE_DEVICE_SMART_CONTROL = """
mutation updateDeviceSmartControl($deviceId: ID!, $action: SmartControlAction!) {
  updateDeviceSmartControl(input: { deviceId: $deviceId, action: $action }) {
    id
    name
    status {
      isSuspended
    }
  }
}
"""

QUERY_DEVICES = """
query devices($accountNumber: String!) {
  devices(accountNumber: $accountNumber) {
    id
    name
    status {
      current
      currentState
      isSuspended
    }
  }
}
"""

QUERY_VEHICLE_CHARGING_PREFERENCES = """
query vehicleChargingPreferences($accountNumber: String!) {
  vehicleChargingPreferences(accountNumber: $accountNumber) {
    weekdayTargetSoc
    weekdayTargetTime
    weekendTargetSoc
    weekendTargetTime
  }
}
"""

QUERY_FLEX_PLANNED_DISPATCHES = """
query flexPlannedDispatches($deviceId: String!) {
  flexPlannedDispatches(deviceId: $deviceId) {
    start
    end
  }
}
"""

# Les 7 jours sont écrits en littéral : ce sont des enums GraphQL (pas des valeurs
# interpolées). Seuls time/max varient et passent par des variables réutilisées.
MUTATION_SET_DEVICE_PREFERENCES = """
mutation setDevicePreferences($deviceId: ID!, $time: Time!, $max: Decimal!) {
  setDevicePreferences(input: {
    deviceId: $deviceId
    mode: CHARGE
    unit: PERCENTAGE
    schedules: [
      { dayOfWeek: MONDAY, time: $time, max: $max }
      { dayOfWeek: TUESDAY, time: $time, max: $max }
      { dayOfWeek: WEDNESDAY, time: $time, max: $max }
      { dayOfWeek: THURSDAY, time: $time, max: $max }
      { dayOfWeek: FRIDAY, time: $time, max: $max }
      { dayOfWeek: SATURDAY, time: $time, max: $max }
      { dayOfWeek: SUNDAY, time: $time, max: $max }
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

    async def _update_boost_charge(
        self, device_id: str, mutation: str
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Update boost charge (trigger or cancel). Returns (data, refusal_reasons)."""
        response = await self.api_client.execute_with_auth(
            mutation, {"deviceId": device_id}
        )

        refusal_reasons: list[str] = []
        if response and "errors" in response:
            for error in response.get("errors", []):
                extensions = error.get("extensions", {})
                refusal_reasons.extend(extensions.get("boostChargeRefusalReasons", []))

        data = (response.get("data") or {}).get("updateBoostCharge") if response else None
        return data, refusal_reasons

    async def trigger_boost_charge(
        self, device_id: str
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Trigger boost charge. Returns (data, refusal_reasons)."""
        return await self._update_boost_charge(device_id, MUTATION_TRIGGER_BOOST_CHARGE)

    async def cancel_boost_charge(
        self, device_id: str
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Cancel boost charge. Returns (data, refusal_reasons)."""
        return await self._update_boost_charge(device_id, MUTATION_CANCEL_BOOST_CHARGE)

    async def _update_smart_control(self, device_id: str, action: str) -> bool:
        """Suspend or unsuspend Octopus's automatic smart control of a device."""
        response = await self.api_client.execute_with_auth(
            MUTATION_UPDATE_DEVICE_SMART_CONTROL,
            {"deviceId": device_id, "action": action},
        )
        if response and "errors" in response:
            return False
        return response is not None and "data" in response

    async def suspend_smart_control(self, device_id: str) -> bool:
        """Suspend Octopus's automatic smart control (stops it interrupting charging)."""
        return await self._update_smart_control(device_id, "SUSPEND")

    async def unsuspend_smart_control(self, device_id: str) -> bool:
        """Restore Octopus's automatic smart control."""
        return await self._update_smart_control(device_id, "UNSUSPEND")

    async def get_devices(self, account_number: str) -> list[dict[str, Any]]:
        """Get list of Intelligent devices for an account."""
        response = await self.api_client.execute_with_auth(
            QUERY_DEVICES, {"accountNumber": account_number}
        )
        return (response.get("data") or {}).get("devices", []) if response else []

    async def get_vehicle_charging_preferences(
        self, account_number: str
    ) -> dict[str, Any]:
        """Get vehicle charging preferences for an account."""
        response = await self.api_client.execute_with_auth(
            QUERY_VEHICLE_CHARGING_PREFERENCES, {"accountNumber": account_number}
        )
        return (
            (response.get("data") or {}).get("vehicleChargingPreferences", {})
            if response
            else {}
        )

    async def get_flex_planned_dispatches(self, device_id: str) -> list[dict[str, Any]]:
        """Get planned flex dispatch windows for a device."""
        response = await self.api_client.execute_with_auth(
            QUERY_FLEX_PLANNED_DISPATCHES, {"deviceId": device_id}
        )
        return (
            (response.get("data") or {}).get("flexPlannedDispatches", [])
            if response
            else []
        )

    async def _send_device_preferences(
        self, device_id: str, target_time: str, target_soc: int
    ) -> bool:
        """Send device preferences mutation (same value for all 7 days)."""
        response = await self.api_client.execute_with_auth(
            MUTATION_SET_DEVICE_PREFERENCES,
            {"deviceId": device_id, "time": target_time, "max": target_soc},
        )
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
