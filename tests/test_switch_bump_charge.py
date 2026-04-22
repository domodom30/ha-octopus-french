"""Test the bump charge switch."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.octopus_french.coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator
from custom_components.octopus_french.switch import OctopusIntelligentBumpChargeSwitch


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
                "status": {"current": "LIVE", "currentState": "SMART_CONTROL_IN_PROGRESS"},
            }
        ],
        "boost_refusal_reasons": [],
    }
    coordinator.intelligent_client = MagicMock()
    coordinator.intelligent_client.trigger_boost_charge = AsyncMock(return_value=({"id": "abc-123", "name": "Tesla Model 3"}, []))
    coordinator.intelligent_client.cancel_boost_charge = AsyncMock(return_value=({"id": "abc-123", "name": "Tesla Model 3"}, []))
    coordinator.async_refresh_devices = AsyncMock()
    coordinator.get_device.side_effect = lambda device_id: next(
        (device for device in coordinator.data["devices"] if device.get("id") == device_id), None
    )
    coordinator.is_device_active.side_effect = lambda device_id: (
        (device := next(
            (device for device in coordinator.data["devices"] if device.get("id") == device_id),
            None,
        ))
        and device.get("status", {}).get("currentState")
        in OctopusIntelligentDataUpdateCoordinator.ACTIVE_CHARGING_STATES
    )
    return coordinator


@pytest.fixture
def bump_charge_switch(mock_coordinator):
    """Create bump charge switch."""
    return OctopusIntelligentBumpChargeSwitch(
        mock_coordinator,
        "abc-123",
        "Tesla Model 3",
    )


@pytest.mark.asyncio
async def test_bump_charge_switch_on(bump_charge_switch, mock_coordinator):
    """Test turning on bump charge."""
    await bump_charge_switch.async_turn_on()

    mock_coordinator.intelligent_client.trigger_boost_charge.assert_called_once_with("abc-123")
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_bump_charge_switch_off(bump_charge_switch, mock_coordinator):
    """Test turning off bump charge."""
    await bump_charge_switch.async_turn_off()

    mock_coordinator.intelligent_client.cancel_boost_charge.assert_called_once_with("abc-123")
    mock_coordinator.async_refresh_devices.assert_called_once()


@pytest.mark.asyncio
async def test_bump_charge_switch_on_refused(bump_charge_switch, mock_coordinator):
    """Test turning on boost charge when refused."""
    mock_coordinator.intelligent_client.trigger_boost_charge.return_value = (
        None,
        ["BC_DEVICE_FULLY_CHARGED"],
    )

    await bump_charge_switch.async_turn_on()

    mock_coordinator.intelligent_client.trigger_boost_charge.assert_called_once_with("abc-123")
    # No refresh should be called on error
    mock_coordinator.async_refresh_devices.assert_not_called()


@pytest.mark.asyncio
async def test_bump_charge_switch_off_refused(bump_charge_switch, mock_coordinator):
    """Test turning off boost charge when refused."""
    mock_coordinator.intelligent_client.cancel_boost_charge.return_value = (
        None,
        ["BC_NO_ACTIVE_BOOST"],
    )

    await bump_charge_switch.async_turn_off()

    mock_coordinator.intelligent_client.cancel_boost_charge.assert_called_once_with("abc-123")
    # No refresh should be called on error
    mock_coordinator.async_refresh_devices.assert_not_called()


def test_bump_charge_switch_is_on_boosting(bump_charge_switch, mock_coordinator):
    """Test is_on when boosting."""
    mock_coordinator.data["devices"][0]["status"]["currentState"] = "BOOSTING"
    assert bump_charge_switch.is_on is True


def test_bump_charge_switch_is_on_smart_control(bump_charge_switch, mock_coordinator):
    """Test is_on for smart control in progress (should be off for bump charge switch)."""
    mock_coordinator.data["devices"][0]["status"]["currentState"] = "SMART_CONTROL_IN_PROGRESS"
    assert bump_charge_switch.is_on is False


def test_bump_charge_switch_is_on_not_boosting(bump_charge_switch, mock_coordinator):
    """Test is_on when not boosting."""
    mock_coordinator.data["devices"][0]["status"]["currentState"] = "SMART_CONTROL_CAPABLE"
    assert bump_charge_switch.is_on is False


def test_bump_charge_switch_attributes(bump_charge_switch, mock_coordinator):
    """Test extra state attributes."""
    mock_coordinator.data["boost_refusal_reasons"] = ["BC_DEVICE_DISCONNECTED"]
    assert bump_charge_switch.extra_state_attributes == {
        "current": "LIVE",
        "current_state": "SMART_CONTROL_IN_PROGRESS",
        "refusal_reasons": ["BC_DEVICE_DISCONNECTED"],
    }
