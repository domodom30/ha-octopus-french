"""Test the intelligent API client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.octopus_french.api.intelligent import (
    MUTATION_SET_DEVICE_PREFERENCES,
    OctopusIntelligentApiClient,
)


@pytest.fixture
def mock_api_client():
    """Mock the main API client."""
    client = MagicMock()
    client.execute_with_auth = AsyncMock()
    return client


@pytest.fixture
def intelligent_client(mock_api_client):
    """Create intelligent client."""
    return OctopusIntelligentApiClient(mock_api_client)


@pytest.mark.asyncio
async def test_trigger_boost_charge_success(intelligent_client, mock_api_client):
    """Test successful boost charge trigger."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "updateBoostCharge": {
                "id": "abc-123",
                "name": "Tesla Model 3"
            }
        }
    }

    result, refusal_reasons = await intelligent_client.trigger_boost_charge("abc-123")

    assert result == {"id": "abc-123", "name": "Tesla Model 3"}
    assert refusal_reasons == []
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_boost_charge_refused(intelligent_client, mock_api_client):
    """Test boost charge refused."""
    mock_api_client.execute_with_auth.return_value = {
        "errors": [{
            "message": "Unable to trigger boost charge.",
            "extensions": {
                "errorCode": "KT-CT-4357",
                "boostChargeRefusalReasons": ["BC_DEVICE_DISCONNECTED"]
            }
        }],
        "data": {"updateBoostCharge": None}
    }

    result, refusal_reasons = await intelligent_client.trigger_boost_charge("abc-123")

    assert result is None
    assert refusal_reasons == ["BC_DEVICE_DISCONNECTED"]
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_boost_charge_fully_charged(intelligent_client, mock_api_client):
    """Test boost charge refused when device is already fully charged."""
    mock_api_client.execute_with_auth.return_value = {
        "errors": [{
            "message": "Unable to trigger boost charge.",
            "locations": [{"line": 2, "column": 3}],
            "path": ["updateBoostCharge"],
            "extensions": {
                "errorType": "APPLICATION",
                "errorCode": "KT-CT-4357",
                "errorDescription": "An internal error occurred. Please try again later.",
                "boostChargeRefusalReasons": ["BC_DEVICE_FULLY_CHARGED"],
            },
        }],
        "data": {"updateBoostCharge": None},
    }

    result, refusal_reasons = await intelligent_client.trigger_boost_charge("abc-123")

    assert result is None
    assert refusal_reasons == ["BC_DEVICE_FULLY_CHARGED"]
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_boost_charge(intelligent_client, mock_api_client):
    """Test cancel boost charge."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "updateBoostCharge": {
                "id": "abc-123",
                "name": "Tesla Model 3"
            }
        }
    }

    result, refusal_reasons = await intelligent_client.cancel_boost_charge("abc-123")

    assert result == {"id": "abc-123", "name": "Tesla Model 3"}
    assert refusal_reasons == []
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_get_devices(intelligent_client, mock_api_client):
    """Test getting device list."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "devices": [
                {
                    "id": "abc-123",
                    "name": "Tesla Model 3",
                    "status": {"current": "LIVE", "currentState": "SMART_CONTROL_IN_PROGRESS"},
                }
            ]
        }
    }

    result = await intelligent_client.get_devices("A-XXXX")

    assert result == [
        {
            "id": "abc-123",
            "name": "Tesla Model 3",
            "status": {"current": "LIVE", "currentState": "SMART_CONTROL_IN_PROGRESS"},
        }
    ]
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_get_vehicle_charging_preferences(intelligent_client, mock_api_client):
    """Test getting charging preferences."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "vehicleChargingPreferences": {
                "weekdayTargetSoc": 100,
                "weekdayTargetTime": "07:30",
                "weekendTargetSoc": 100,
                "weekendTargetTime": "07:30",
            }
        }
    }

    result = await intelligent_client.get_vehicle_charging_preferences("A-XXXX")

    assert result == {
        "weekdayTargetSoc": 100,
        "weekdayTargetTime": "07:30",
        "weekendTargetSoc": 100,
        "weekendTargetTime": "07:30",
    }
    mock_api_client.execute_with_auth.assert_called_once()


@pytest.mark.asyncio
async def test_suspend_smart_control_success(intelligent_client, mock_api_client):
    """Test suspending smart control."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "updateDeviceSmartControl": {
                "id": "abc-123",
                "name": "Tesla Model 3",
                "status": {"isSuspended": True},
            }
        }
    }

    result = await intelligent_client.suspend_smart_control("abc-123")

    assert result is True
    mock_api_client.execute_with_auth.assert_called_once()
    _, variables = mock_api_client.execute_with_auth.call_args[0]
    assert variables == {"deviceId": "abc-123", "action": "SUSPEND"}


@pytest.mark.asyncio
async def test_unsuspend_smart_control_success(intelligent_client, mock_api_client):
    """Test restoring smart control."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "updateDeviceSmartControl": {
                "id": "abc-123",
                "name": "Tesla Model 3",
                "status": {"isSuspended": False},
            }
        }
    }

    result = await intelligent_client.unsuspend_smart_control("abc-123")

    assert result is True
    mock_api_client.execute_with_auth.assert_called_once()
    _, variables = mock_api_client.execute_with_auth.call_args[0]
    assert variables == {"deviceId": "abc-123", "action": "UNSUSPEND"}


@pytest.mark.asyncio
async def test_update_smart_control_error(intelligent_client, mock_api_client):
    """Test smart control update failing."""
    mock_api_client.execute_with_auth.return_value = {
        "errors": [{"message": "Unauthorized."}],
        "data": {"updateDeviceSmartControl": None},
    }

    result = await intelligent_client.suspend_smart_control("abc-123")

    assert result is False


def test_mutation_set_device_preferences_uses_correct_graphql_types():
    """setDevicePreferences must declare deviceId/time/max as ID!/Time!/Decimal!.

    Regression test for a bug where these were declared String!/String!/Int!,
    which Kraken rejected with an HTTP 400 on every call.
    """
    assert "$deviceId: ID!" in MUTATION_SET_DEVICE_PREFERENCES
    assert "$time: Time!" in MUTATION_SET_DEVICE_PREFERENCES
    assert "$max: Decimal!" in MUTATION_SET_DEVICE_PREFERENCES


@pytest.mark.asyncio
async def test_set_target_soc_success(intelligent_client, mock_api_client):
    """Test setting target state of charge."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "setDevicePreferences": {
                "id": "abc-123",
                "preferences": {"schedules": []},
            }
        }
    }

    result = await intelligent_client.set_target_soc("abc-123", 100, "07:00")

    assert result is True
    mock_api_client.execute_with_auth.assert_called_once()
    _, variables = mock_api_client.execute_with_auth.call_args[0]
    assert variables == {"deviceId": "abc-123", "time": "07:00", "max": 100}


@pytest.mark.asyncio
async def test_set_target_time_success(intelligent_client, mock_api_client):
    """Test setting target charging time."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "setDevicePreferences": {
                "id": "abc-123",
                "preferences": {"schedules": []},
            }
        }
    }

    result = await intelligent_client.set_target_time("abc-123", "22:30", 80)

    assert result is True
    mock_api_client.execute_with_auth.assert_called_once()
    _, variables = mock_api_client.execute_with_auth.call_args[0]
    assert variables == {"deviceId": "abc-123", "time": "22:30", "max": 80}


@pytest.mark.asyncio
async def test_set_device_preferences_error(intelligent_client, mock_api_client):
    """Test setDevicePreferences failing (e.g. the wrong-GraphQL-type 400 this guards against)."""
    mock_api_client.execute_with_auth.return_value = {
        "errors": [{"message": "Variable '$deviceId' of type 'String!' used in position expecting type 'ID!'."}],
        "data": {"setDevicePreferences": None},
    }

    result = await intelligent_client.set_target_soc("abc-123", 100, "07:00")

    assert result is False


@pytest.mark.asyncio
async def test_get_flex_planned_dispatches(intelligent_client, mock_api_client):
    """Test getting planned dispatch windows."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "flexPlannedDispatches": [
                {"start": "2026-04-22T21:00:00+00:00", "end": "2026-04-22T22:00:00+00:00"}
            ]
        }
    }

    result = await intelligent_client.get_flex_planned_dispatches("abc-123")

    assert result == [
        {"start": "2026-04-22T21:00:00+00:00", "end": "2026-04-22T22:00:00+00:00"}
    ]
    mock_api_client.execute_with_auth.assert_called_once()
