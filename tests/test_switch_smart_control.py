"""Test the Smart Control suspend/restore switch."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.octopus_french.coordinator_intelligent import (
    OctopusIntelligentDataUpdateCoordinator,
)
from custom_components.octopus_french.switch import (
    OctopusIntelligentSmartControlSwitch,
)


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    coordinator = MagicMock(spec=OctopusIntelligentDataUpdateCoordinator)
    coordinator.account_number = "A-XXXX"
    coordinator.data = {
        "devices": [
            {
                "id": "abc-123",
                "name": "Tesla Model 3",
                "status": {
                    "current": "LIVE",
                    "currentState": "SMART_CONTROL_CAPABLE",
                    "isSuspended": False,
                },
            }
        ],
    }
    coordinator.intelligent_client = MagicMock()
    coordinator.intelligent_client.suspend_smart_control = AsyncMock(return_value=True)
    coordinator.intelligent_client.unsuspend_smart_control = AsyncMock(
        return_value=True
    )
    coordinator.async_refresh_devices = AsyncMock()
    coordinator.get_device.side_effect = lambda device_id: next(
        (d for d in coordinator.data["devices"] if d.get("id") == device_id),
        None,
    )
    return coordinator


@pytest.fixture
def smart_control_switch(mock_coordinator):
    """Create the smart control switch."""
    return OctopusIntelligentSmartControlSwitch(
        mock_coordinator,
        "abc-123",
        "Tesla Model 3",
    )


def test_unique_id_is_domain_prefixed(smart_control_switch):
    """L'unique_id suit la convention DOMAIN_{device}_smart_control."""
    assert smart_control_switch.unique_id == "octopus_french_abc-123_smart_control"


def test_is_on_when_not_suspended(smart_control_switch):
    """Smart control actif (non suspendu) → switch on."""
    assert smart_control_switch.is_on is True


def test_is_on_when_suspended(smart_control_switch, mock_coordinator):
    """Smart control suspendu → switch off."""
    mock_coordinator.data["devices"][0]["status"]["isSuspended"] = True
    assert smart_control_switch.is_on is False


@pytest.mark.asyncio
async def test_turn_off_suspends(smart_control_switch, mock_coordinator):
    """Éteindre le switch suspend le smart control."""
    await smart_control_switch.async_turn_off()

    mock_coordinator.intelligent_client.suspend_smart_control.assert_called_once_with(
        "abc-123"
    )
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_turn_on_unsuspends(smart_control_switch, mock_coordinator):
    """Allumer le switch rétablit le smart control."""
    await smart_control_switch.async_turn_on()

    mock_coordinator.intelligent_client.unsuspend_smart_control.assert_called_once_with(
        "abc-123"
    )
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_turn_off_failure_raises(smart_control_switch, mock_coordinator):
    """Un échec de suspension lève HomeAssistantError et ne rafraîchit pas."""
    mock_coordinator.intelligent_client.suspend_smart_control.return_value = False

    with pytest.raises(HomeAssistantError):
        await smart_control_switch.async_turn_off()

    mock_coordinator.async_refresh_devices.assert_not_called()


@pytest.mark.asyncio
async def test_turn_on_failure_raises(smart_control_switch, mock_coordinator):
    """Un échec de rétablissement lève HomeAssistantError et ne rafraîchit pas."""
    mock_coordinator.intelligent_client.unsuspend_smart_control.return_value = False

    with pytest.raises(HomeAssistantError):
        await smart_control_switch.async_turn_on()

    mock_coordinator.async_refresh_devices.assert_not_called()
