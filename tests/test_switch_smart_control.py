"""Test the smart control switch."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.octopus_french.coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator
from custom_components.octopus_french.switch import OctopusIntelligentSmartControlSwitch


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
                    "currentState": "SMART_CONTROL_IN_PROGRESS",
                    "isSuspended": False,
                },
            }
        ],
    }
    coordinator.intelligent_client = MagicMock()
    coordinator.intelligent_client.suspend_smart_control = AsyncMock(return_value=True)
    coordinator.intelligent_client.unsuspend_smart_control = AsyncMock(return_value=True)
    coordinator.async_refresh_devices = AsyncMock()
    coordinator.get_device.side_effect = lambda device_id: next(
        (device for device in coordinator.data["devices"] if device.get("id") == device_id), None
    )
    return coordinator


@pytest.fixture
def smart_control_switch(mock_coordinator):
    """Create smart control switch."""
    return OctopusIntelligentSmartControlSwitch(
        mock_coordinator,
        "abc-123",
        "Tesla Model 3",
    )


@pytest.mark.asyncio
async def test_smart_control_switch_on_restores_control(smart_control_switch, mock_coordinator):
    """Turning the switch on unsuspends Octopus's smart control."""
    await smart_control_switch.async_turn_on()

    mock_coordinator.intelligent_client.unsuspend_smart_control.assert_called_once_with("abc-123")
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_smart_control_switch_off_suspends_control(smart_control_switch, mock_coordinator):
    """Turning the switch off suspends Octopus's smart control."""
    await smart_control_switch.async_turn_off()

    mock_coordinator.intelligent_client.suspend_smart_control.assert_called_once_with("abc-123")
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_smart_control_switch_on_failure_raises(smart_control_switch, mock_coordinator):
    """A failed unsuspend raises and does not refresh."""
    mock_coordinator.intelligent_client.unsuspend_smart_control.return_value = False

    with pytest.raises(HomeAssistantError):
        await smart_control_switch.async_turn_on()

    mock_coordinator.async_refresh_devices.assert_not_called()


@pytest.mark.asyncio
async def test_smart_control_switch_off_failure_raises(smart_control_switch, mock_coordinator):
    """A failed suspend raises and does not refresh."""
    mock_coordinator.intelligent_client.suspend_smart_control.return_value = False

    with pytest.raises(HomeAssistantError):
        await smart_control_switch.async_turn_off()

    mock_coordinator.async_refresh_devices.assert_not_called()


def test_smart_control_switch_is_on_when_not_suspended(smart_control_switch, mock_coordinator):
    """is_on is True when Octopus's control is active (not suspended)."""
    mock_coordinator.data["devices"][0]["status"]["isSuspended"] = False
    assert smart_control_switch.is_on is True


def test_smart_control_switch_is_off_when_suspended(smart_control_switch, mock_coordinator):
    """is_on is False once smart control has been suspended."""
    mock_coordinator.data["devices"][0]["status"]["isSuspended"] = True
    assert smart_control_switch.is_on is False


def test_smart_control_switch_is_on_defaults_true_when_unknown(smart_control_switch, mock_coordinator):
    """Absent isSuspended defaults to control-active (fail-safe: don't assume suspended)."""
    del mock_coordinator.data["devices"][0]["status"]["isSuspended"]
    assert smart_control_switch.is_on is True
