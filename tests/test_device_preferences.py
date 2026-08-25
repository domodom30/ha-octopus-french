"""Test the number and select entities + set_target_soc/set_target_time API."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.octopus_french.api.intelligent import (
    MUTATION_SET_DEVICE_PREFERENCES,
    OctopusIntelligentApiClient,
)
from custom_components.octopus_french.coordinator_intelligent import (
    OctopusIntelligentDataUpdateCoordinator,
    preferences_from_schedules,
)
from custom_components.octopus_french.number import OctopusIntelligentTargetSocNumber
from custom_components.octopus_french.select import (
    TIME_OPTIONS,
    OctopusIntelligentTargetTimeSelect,
)

# Les 7 jours sont écrits en littéral dans la mutation (enums GraphQL) ; on les
# réutilise ici pour construire les réponses simulées.
_DAYS_OF_WEEK = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]


def test_set_device_preferences_declares_correct_graphql_types():
    """setDevicePreferences doit déclarer deviceId/time/max en ID!/Time!/Decimal! (issue #55).

    Kraken rejette `String!`/`Int!` en HTTP 400 (« used in position expecting type 'ID!' »),
    ce qui cassait la charge cible / l'heure cible / la recharge rapide.
    """
    assert "$deviceId: ID!" in MUTATION_SET_DEVICE_PREFERENCES
    assert "$time: Time!" in MUTATION_SET_DEVICE_PREFERENCES
    assert "$max: Decimal!" in MUTATION_SET_DEVICE_PREFERENCES


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
async def test_set_target_soc_success(intelligent_client, mock_api_client):
    """Test setting target SOC successfully."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "setDevicePreferences": {
                "id": "abc-123",
                "preferences": {
                    "schedules": [
                        {"dayOfWeek": day, "time": "07:30", "max": 80}
                        for day in _DAYS_OF_WEEK
                    ]
                },
            }
        }
    }

    result = await intelligent_client.set_target_soc("abc-123", 80, "07:30")

    assert result is True
    mock_api_client.execute_with_auth.assert_called_once()
    query, variables = mock_api_client.execute_with_auth.call_args[0]
    assert "setDevicePreferences" in query
    assert "MONDAY" in query
    assert "SUNDAY" in query
    assert variables == {"deviceId": "abc-123", "time": "07:30", "max": 80}


@pytest.mark.asyncio
async def test_set_target_soc_error(intelligent_client, mock_api_client):
    """Test setting target SOC with API error."""
    mock_api_client.execute_with_auth.return_value = {
        "errors": [{"message": "Invalid input"}],
        "data": None,
    }

    result = await intelligent_client.set_target_soc("abc-123", 80, "07:30")

    assert result is False


@pytest.mark.asyncio
async def test_set_target_soc_empty_response(intelligent_client, mock_api_client):
    """Test setting target SOC with empty response."""
    mock_api_client.execute_with_auth.return_value = None

    result = await intelligent_client.set_target_soc("abc-123", 80, "07:30")

    assert result is False


@pytest.mark.asyncio
async def test_set_target_time_success(intelligent_client, mock_api_client):
    """Test setting target time successfully."""
    mock_api_client.execute_with_auth.return_value = {
        "data": {
            "setDevicePreferences": {
                "id": "abc-123",
                "preferences": {
                    "schedules": [
                        {"dayOfWeek": day, "time": "06:00", "max": 100}
                        for day in _DAYS_OF_WEEK
                    ]
                },
            }
        }
    }

    result = await intelligent_client.set_target_time("abc-123", "06:00", 100)

    assert result is True
    query, variables = mock_api_client.execute_with_auth.call_args[0]
    assert "setDevicePreferences" in query
    assert variables == {"deviceId": "abc-123", "time": "06:00", "max": 100}


def _wire_get_preferences(coordinator: MagicMock) -> None:
    """Câble get_preferences sur le mock, comme le fait le vrai coordinator.

    Les entités lisent les préférences par appareil et non plus directement
    coordinator.data["preferences"] (issue #77).
    """
    coordinator.get_preferences = lambda device_id: (
        OctopusIntelligentDataUpdateCoordinator.get_preferences(coordinator, device_id)
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
                "status": {"current": "LIVE", "currentState": "SMART_CONTROL_CAPABLE"},
            }
        ],
        "preferences": {
            "weekdayTargetSoc": 100,
            "weekdayTargetTime": "07:30",
            "weekendTargetSoc": 100,
            "weekendTargetTime": "07:30",
        },
        "boost_refusal_reasons": [],
    }
    _wire_get_preferences(coordinator)
    coordinator.intelligent_client = MagicMock()
    coordinator.intelligent_client.set_target_soc = AsyncMock(return_value=True)
    coordinator.intelligent_client.set_target_time = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def target_soc_number(mock_coordinator):
    """Create target SOC number entity."""
    return OctopusIntelligentTargetSocNumber(
        mock_coordinator,
        "abc-123",
        "Tesla Model 3",
    )


@pytest.fixture
def target_time_select(mock_coordinator):
    """Create target time select entity."""
    return OctopusIntelligentTargetTimeSelect(
        mock_coordinator,
        "abc-123",
        "Tesla Model 3",
    )


def test_target_soc_native_value(target_soc_number):
    """Test reading target SOC value."""
    assert target_soc_number.native_value == 100


def test_target_soc_attributes(target_soc_number):
    """Test target SOC entity attributes."""
    assert target_soc_number._attr_native_min_value == 0
    assert target_soc_number._attr_native_max_value == 100
    assert target_soc_number._attr_native_step == 5
    assert target_soc_number._attr_native_unit_of_measurement == "%"


@pytest.mark.asyncio
async def test_target_soc_set_value(target_soc_number, mock_coordinator):
    """Test setting target SOC value."""
    await target_soc_number.async_set_native_value(80)

    mock_coordinator.intelligent_client.set_target_soc.assert_called_once_with(
        "abc-123", 80, "07:30"
    )
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_target_soc_set_value_failure(target_soc_number, mock_coordinator):
    """Test setting target SOC value when API fails."""
    mock_coordinator.intelligent_client.set_target_soc.return_value = False

    with pytest.raises(HomeAssistantError):
        await target_soc_number.async_set_native_value(80)

    mock_coordinator.intelligent_client.set_target_soc.assert_called_once()
    mock_coordinator.async_request_refresh.assert_not_called()


def test_time_options_count():
    """Test that TIME_OPTIONS has 48 half-hour slots."""
    assert len(TIME_OPTIONS) == 48
    assert TIME_OPTIONS[0] == "00:00"
    assert TIME_OPTIONS[1] == "00:30"
    assert TIME_OPTIONS[-1] == "23:30"


def test_target_time_current_option(target_time_select):
    """Test reading target time value."""
    assert target_time_select.current_option == "07:30"


def test_target_time_current_option_none(target_time_select, mock_coordinator):
    """Test reading target time when not set."""
    mock_coordinator.data["preferences"]["weekdayTargetTime"] = None
    target_time_select._update_attrs()
    assert target_time_select.current_option is None


@pytest.mark.asyncio
async def test_target_time_select_option(target_time_select, mock_coordinator):
    """Test selecting a target time option."""
    await target_time_select.async_select_option("06:00")

    mock_coordinator.intelligent_client.set_target_time.assert_called_once_with(
        "abc-123", "06:00", 100
    )
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_target_time_select_option_failure(target_time_select, mock_coordinator):
    """Test selecting a target time when API fails."""
    mock_coordinator.intelligent_client.set_target_time.return_value = False

    with pytest.raises(HomeAssistantError):
        await target_time_select.async_select_option("06:00")

    mock_coordinator.intelligent_client.set_target_time.assert_called_once()
    mock_coordinator.async_request_refresh.assert_not_called()


_WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
_WEEKEND = ["SATURDAY", "SUNDAY"]


def _schedules(time: str, target: int, days: list[str]) -> list[dict]:
    """Créneaux de préférence tels que renvoyés par l'API pour un appareil."""
    return [{"dayOfWeek": d, "time": time, "min": None, "max": target} for d in days]


def _coordinator_with_devices(devices: list[dict]) -> MagicMock:
    """Coordinator simulé exposant get_preferences comme le vrai."""
    coordinator = MagicMock(spec=OctopusIntelligentDataUpdateCoordinator)
    coordinator.account_number = "A-1"
    coordinator.data = {
        "devices": devices,
        "preferences": {"weekdayTargetTime": "07:00", "weekdayTargetSoc": 80},
        "device_preferences": {
            device["id"]: preferences_from_schedules(device.get("preferences"))
            for device in devices
        },
    }
    coordinator.get_preferences = lambda device_id: (
        OctopusIntelligentDataUpdateCoordinator.get_preferences(coordinator, device_id)
    )
    return coordinator


def test_preferences_from_schedules_splits_weekday_and_weekend() -> None:
    """Les créneaux par jour deviennent des cibles semaine et week-end."""
    preferences = {
        "schedules": _schedules("07:00:00", 80, _WEEKDAYS)
        + _schedules("09:30:00", 90, _WEEKEND)
    }

    assert preferences_from_schedules(preferences) == {
        "weekdayTargetTime": "07:00",
        "weekdayTargetSoc": 80,
        "weekendTargetTime": "09:30",
        "weekendTargetSoc": 90,
    }


def test_preferences_from_schedules_normalises_time_to_select_options() -> None:
    """L'heure est ramenée au format HH:MM attendu par le select."""
    result = preferences_from_schedules(
        {"schedules": _schedules("05:30:00", 70, ["MONDAY"])}
    )

    assert result["weekdayTargetTime"] in TIME_OPTIONS


def test_each_vehicle_exposes_its_own_target_time() -> None:
    """Deux véhicules gardent chacun leur heure cible (issue #77)."""
    devices = [
        {
            "id": "VE1",
            "name": "Zoe",
            "preferences": {"schedules": _schedules("07:00:00", 80, _WEEKDAYS)},
        },
        {
            "id": "VE2",
            "name": "Tesla",
            "preferences": {"schedules": _schedules("05:30:00", 100, _WEEKDAYS)},
        },
    ]
    coordinator = _coordinator_with_devices(devices)

    ve1 = OctopusIntelligentTargetTimeSelect(coordinator, "VE1", "Zoe")
    ve2 = OctopusIntelligentTargetTimeSelect(coordinator, "VE2", "Tesla")
    soc1 = OctopusIntelligentTargetSocNumber(coordinator, "VE1", "Zoe")
    soc2 = OctopusIntelligentTargetSocNumber(coordinator, "VE2", "Tesla")

    assert ve1.current_option == "07:00"
    assert ve2.current_option == "05:30"
    assert soc1.native_value == 80.0
    assert soc2.native_value == 100.0


def test_device_without_schedules_falls_back_to_account_preferences() -> None:
    """Sans créneaux par appareil, on garde les préférences du compte."""
    coordinator = _coordinator_with_devices([{"id": "VE1", "name": "Zoe"}])

    entity = OctopusIntelligentTargetTimeSelect(coordinator, "VE1", "Zoe")

    assert entity.current_option == "07:00"
