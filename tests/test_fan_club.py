"""Tests de l'offre Fan Club : réduction liée au parc éolien local (issue #95)."""

from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.octopus_french.api.fan_club import OctopusFanClubApiClient
from custom_components.octopus_french.const import DOMAIN, SERVICE_FORCE_UPDATE
from custom_components.octopus_french.coordinator_fan_club import (
    OctopusFanClubDataUpdateCoordinator,
    discount_percent,
    next_discount_change,
)
from custom_components.octopus_french.octopus_french import (
    OctopusAuthError,
    OctopusConnectionError,
)

_ENTRY_DATA = {
    "email": "user@example.fr",
    "password": "s3cret",
    "account_number": "A-123",
}

_ACCOUNT_DATA = {
    "account_id": "acc-1",
    "account_number": "A-123",
    "supply_points": {"electricity": [], "gas": []},
    "ledgers": {},
}

_SOURCE = "#1 Fan (FRA): Les Touches 2"

_STATUS = {
    "discountSource": _SOURCE,
    "current": {"startAt": "2026-10-30T14:00:00+01:00", "discount": "0.200"},
    "historic": [],
    "forecast": {
        "baseTime": "2026-10-30T14:00:00+01:00",
        "data": [
            {"validTime": "2026-10-30T15:00:00+01:00", "projectedDiscount": "0.200"},
            {"validTime": "2026-10-30T14:30:00+01:00", "projectedDiscount": "0.200"},
            {"validTime": "2026-10-30T15:30:00+01:00", "projectedDiscount": "0.500"},
        ],
    },
}

_NOW = datetime.fromisoformat("2026-10-30T14:10:00+01:00")


@pytest.fixture(autouse=True)
def mock_intelligent_client() -> Generator[MagicMock]:
    """Compte sans appareil Intelligent."""
    with patch(
        "custom_components.octopus_french.coordinator_intelligent.OctopusIntelligentApiClient",
    ) as client_cls:
        client_cls.return_value.get_devices = AsyncMock(return_value=[])
        yield client_cls.return_value


@pytest.fixture
def mock_fan_club_client() -> Generator[MagicMock]:
    """Compte abonné à l'offre Fan Club."""
    with patch(
        "custom_components.octopus_french.coordinator_fan_club.OctopusFanClubApiClient",
    ) as client_cls:
        client_cls.return_value.get_fan_club_status = AsyncMock(return_value=[_STATUS])
        yield client_cls.return_value


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Monte une entry ; l'état final est vérifié par chaque test."""
    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="A-123")
    entry.add_to_hass(hass)

    with patch("custom_components.octopus_french.OctopusFrenchApiClient") as client_cls:
        client = client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "A-123"}])
        client.get_account_data = AsyncMock(return_value=dict(_ACCOUNT_DATA))
        client.get_all_payment_requests = AsyncMock(return_value={})

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


_DISCOUNT_UNIQUE_ID = (
    f"{DOMAIN}_A-123_fan_club_1_fan_fra_les_touches_2_fan_club_discount"
)


def _discount_entity_id(hass: HomeAssistant) -> str | None:
    """Retrouve l'entité réduction des Touches 2 par son unique_id."""
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, _DISCOUNT_UNIQUE_ID)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("0.000", 0.0, id="0%"),
        pytest.param("0.200", 20.0, id="20%"),
        pytest.param("0.500", 50.0, id="50%"),
        pytest.param(0.5, 50.0, id="nombre"),
        pytest.param(None, None, id="absent"),
        pytest.param("n/a", None, id="invalide"),
    ],
)
def test_discount_percent(value, expected) -> None:
    """Le ratio API est converti en pourcentage."""
    assert discount_percent(value) == expected


def test_next_discount_change_skips_unchanged_points() -> None:
    """Le prochain changement est le premier point futur de réduction différente."""
    change = next_discount_change(_STATUS, _NOW)

    assert change is not None
    assert change["discount"] == 50.0
    assert change["valid_time"] == datetime.fromisoformat("2026-10-30T15:30:00+01:00")


def test_next_discount_change_without_forecast() -> None:
    """Sans prévision, aucun changement annoncé."""
    status = {**_STATUS, "forecast": None}

    assert next_discount_change(status, _NOW) is None


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        pytest.param({"data": {"fanClubStatus": [_STATUS]}}, [_STATUS], id="abonne"),
        pytest.param({"data": {"fanClubStatus": []}}, [], id="non-abonne"),
        pytest.param(
            {"data": None, "errors": [{"message": "Not found"}]}, [], id="erreur"
        ),
        pytest.param(
            {"data": {"fanClubStatus": [{"discountSource": None}]}},
            [],
            id="sans-source",
        ),
    ],
)
async def test_get_fan_club_status(response: dict, expected: list) -> None:
    """Une réponse vide ou en erreur donne une liste vide, sans exception."""
    api_client = MagicMock()
    api_client.execute_with_auth = AsyncMock(return_value=response)

    statuses = await OctopusFanClubApiClient(api_client).get_fan_club_status("A-123")

    assert statuses == expected


async def test_auth_error_raises_config_entry_auth_failed(
    hass: HomeAssistant, mock_fan_club_client: MagicMock
) -> None:
    """Une erreur d'authentification déclenche le reauth."""
    mock_fan_club_client.get_fan_club_status.side_effect = OctopusAuthError("expired")
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA)
    coordinator = OctopusFanClubDataUpdateCoordinator(hass, MagicMock(), "A-123", entry)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_setup_with_fan_club_creates_discount_sensor(
    recorder_mock,
    hass: HomeAssistant,
    mock_fan_club_client: MagicMock,
    freezer,
) -> None:
    """Un compte Fan Club expose la réduction en cours et la prévision."""
    freezer.move_to(_NOW)
    entry = await _setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.fan_club_coordinator is not None

    entity_id = _discount_entity_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 20.0
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["discount_source"] == _SOURCE
    assert state.attributes["next_discount"] == 50.0
    assert state.attributes["next_discount_start"] == "2026-10-30T15:30:00+01:00"
    assert [point["discount"] for point in state.attributes["forecast"]] == [
        20.0,
        20.0,
        50.0,
    ]


async def test_setup_without_fan_club(recorder_mock, hass: HomeAssistant) -> None:
    """Un compte sans offre Fan Club n'a ni coordinator ni capteur."""
    with patch(
        "custom_components.octopus_french.coordinator_fan_club.OctopusFanClubApiClient",
    ) as client_cls:
        client_cls.return_value.get_fan_club_status = AsyncMock(return_value=[])
        entry = await _setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.fan_club_coordinator is None
    assert _discount_entity_id(hass) is None


async def test_fan_club_error_at_setup_does_not_block_integration(
    recorder_mock,
    hass: HomeAssistant,
    mock_fan_club_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Une panne de l'API Fan Club désactive l'offre sans bloquer l'intégration."""
    mock_fan_club_client.get_fan_club_status.side_effect = OctopusConnectionError(
        "timeout"
    )
    entry = await _setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.fan_club_coordinator is None
    assert "Fan Club status unavailable" in caplog.text


async def test_one_sensor_per_discount_source(
    recorder_mock, hass: HomeAssistant, mock_fan_club_client: MagicMock
) -> None:
    """Chaque parc éolien a son propre capteur, avec un unique_id distinct."""
    other = {**_STATUS, "discountSource": "#2 Fan (FRA): Autre parc"}
    mock_fan_club_client.get_fan_club_status.return_value = [_STATUS, other]
    entry = await _setup_entry(hass)

    unique_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if "fan_club" in entity.unique_id
    }
    assert unique_ids == {
        _DISCOUNT_UNIQUE_ID,
        f"{DOMAIN}_A-123_fan_club_2_fan_fra_autre_parc_fan_club_discount",
    }


async def test_discount_source_removed_makes_sensor_unavailable(
    recorder_mock, hass: HomeAssistant, mock_fan_club_client: MagicMock
) -> None:
    """Une source qui disparaît de la réponse rend son capteur indisponible."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data.fan_club_coordinator
    entity_id = _discount_entity_id(hass)
    assert entity_id is not None

    coordinator.async_set_updated_data({"statuses": {}})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unavailable"


async def test_force_update_refreshes_fan_club(
    recorder_mock, hass: HomeAssistant, mock_fan_club_client: MagicMock
) -> None:
    """Le service force_update rafraîchit aussi la réduction Fan Club."""
    await _setup_entry(hass)
    calls = mock_fan_club_client.get_fan_club_status.await_count

    await hass.services.async_call(DOMAIN, SERVICE_FORCE_UPDATE, blocking=True)
    await hass.async_block_till_done()

    assert mock_fan_club_client.get_fan_club_status.await_count > calls
