"""Test the number and select entities + set_target_soc/set_target_time API."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.octopus_french.api.intelligent import (
    OctopusIntelligentApiClient,
)
from custom_components.octopus_french.coordinator_intelligent import (
    OctopusIntelligentDataUpdateCoordinator,
)
from custom_components.octopus_french.number import OctopusIntelligentTargetSocNumber
from custom_components.octopus_french.select import (
    OctopusIntelligentTargetTimeSelect,
    TIME_OPTIONS,
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
