"""Test d'intégration « smoke » : setup puis unload d'une config entry.

Ce test prouve que l'infrastructure pytest-homeassistant-custom-component est câblée :
il utilise la vraie fixture ``hass`` et ``MockConfigEntry`` (au lieu d'un ``MagicMock``),
monte réellement l'intégration jusqu'à l'état LOADED, puis la décharge.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.octopus_french.const import (
    DOMAIN,
    SERVICE_FORCE_UPDATE,
    SERVICE_PURGE_ORPHAN_STATISTICS,
    SERVICE_RECOMPUTE_STATISTICS,
)
from custom_components.octopus_french.octopus_french import OctopusAuthError

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


async def test_setup_and_unload_entry(recorder_mock, hass: HomeAssistant) -> None:
    """L'entry monte jusqu'à LOADED puis se décharge proprement."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="A-123")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.octopus_french.OctopusFrenchApiClient",
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "A-123"}])
        client.get_account_data = AsyncMock(return_value=dict(_ACCOUNT_DATA))
        client.get_all_payment_requests = AsyncMock(return_value={})

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.account_number == "A-123"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_restores_persisted_refresh_token(
    recorder_mock, hass: HomeAssistant
) -> None:
    """Le setup restaure le refresh token persisté et branche la persistance."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **_ENTRY_DATA,
            "refresh_token": "persisted-refresh",
            "refresh_token_expiry": 4102444800.0,
        },
        unique_id="A-123",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.octopus_french.OctopusFrenchApiClient",
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "A-123"}])
        client.get_account_data = AsyncMock(return_value=dict(_ACCOUNT_DATA))
        client.get_all_payment_requests = AsyncMock(return_value={})

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    client.token_manager.restore_refresh_token.assert_called_once_with(
        "persisted-refresh", 4102444800.0
    )
    assert client.on_token_update is not None


async def test_auth_error_on_first_refresh_triggers_reauth(
    recorder_mock,
    hass: HomeAssistant,
) -> None:
    """Une erreur d'auth au premier refresh doit déclencher le flow de reauth.

    Régression : _async_fetch_initial_data convertissait ConfigEntryAuthFailed
    en ConfigEntryNotReady, donc HA retentait en boucle sans jamais proposer la
    ré-authentification.
    """
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="A-123")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.octopus_french.OctopusFrenchApiClient",
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "A-123"}])
        client.get_account_data = AsyncMock(
            side_effect=OctopusAuthError("token rejected")
        )

        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"].get("source") == "reauth" for flow in flows)


async def test_configured_account_missing_fails_setup(
    recorder_mock, hass: HomeAssistant
) -> None:
    """Un compte configuré absent de l'API ne doit pas être substitué en silence."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="A-123")
    entry.add_to_hass(hass)

    with patch(
        "custom_components.octopus_french.OctopusFrenchApiClient",
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "AUTRE-999"}])
        client.get_account_data = AsyncMock(return_value=dict(_ACCOUNT_DATA))

        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    client.get_account_data.assert_not_awaited()


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Monte une entry jusqu'à LOADED, services compris."""
    assert await async_setup_component(hass, DOMAIN, {})

    entry = MockConfigEntry(domain=DOMAIN, data=_ENTRY_DATA, unique_id="A-123")
    entry.add_to_hass(hass)

    with patch("custom_components.octopus_french.OctopusFrenchApiClient") as client_cls:
        client = client_cls.return_value
        client.authenticate = AsyncMock(return_value=True)
        client.get_accounts = AsyncMock(return_value=[{"number": "A-123"}])
        client.get_account_data = AsyncMock(return_value=dict(_ACCOUNT_DATA))
        client.get_all_payment_requests = AsyncMock(return_value={})

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.parametrize(
    "service",
    [
        pytest.param(SERVICE_FORCE_UPDATE, id="force_update"),
        pytest.param(SERVICE_RECOMPUTE_STATISTICS, id="recompute_statistics"),
        pytest.param(SERVICE_PURGE_ORPHAN_STATISTICS, id="purge_orphan_statistics"),
    ],
)
async def test_services_are_registered(
    recorder_mock, hass: HomeAssistant, service: str
) -> None:
    """Les trois services de l'intégration sont exposés après le setup."""
    await _setup_entry(hass)

    assert hass.services.has_service(DOMAIN, service)


async def test_recompute_rejects_a_future_start_date(
    recorder_mock, hass: HomeAssistant
) -> None:
    """Une date de début future ne recalculerait rien : erreur explicite."""
    await _setup_entry(hass)
    tomorrow = (dt_util.now() + timedelta(days=1)).date()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RECOMPUTE_STATISTICS,
            {"start_date": tomorrow.isoformat()},
            blocking=True,
        )


async def test_purge_lists_without_deleting_by_default(
    recorder_mock, hass: HomeAssistant
) -> None:
    """Sans confirmation, la purge ne fait que lister : rien n'est supprimé."""
    entry = await _setup_entry(hass)
    importer = entry.runtime_data.coordinator.statistics_importer

    with (
        patch.object(
            importer,
            "async_find_orphan_statistic_ids",
            AsyncMock(return_value=["octopus_french:PRM_PARTI_energy_base"]),
        ),
        patch.object(importer, "async_purge_orphan_statistics", AsyncMock()) as purge,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_PURGE_ORPHAN_STATISTICS,
            {},
            blocking=True,
            return_response=True,
        )

    assert response == {
        "statistic_ids": ["octopus_french:PRM_PARTI_energy_base"],
        "deleted": False,
    }
    purge.assert_not_called()


async def test_purge_deletes_only_once_confirmed(
    recorder_mock, hass: HomeAssistant
) -> None:
    """La suppression est irréversible : elle exige une confirmation explicite."""
    entry = await _setup_entry(hass)
    importer = entry.runtime_data.coordinator.statistics_importer
    orphans = ["octopus_french:PRM_PARTI_energy_base"]

    with (
        patch.object(
            importer,
            "async_find_orphan_statistic_ids",
            AsyncMock(return_value=orphans),
        ),
        patch.object(importer, "async_purge_orphan_statistics", AsyncMock()) as purge,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PURGE_ORPHAN_STATISTICS,
            {"confirm": True},
            blocking=True,
            return_response=True,
        )

    purge.assert_awaited_once_with(orphans)
