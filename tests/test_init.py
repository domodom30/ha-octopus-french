"""Test d'intégration « smoke » : setup puis unload d'une config entry.

Ce test prouve que l'infrastructure pytest-homeassistant-custom-component est câblée :
il utilise la vraie fixture ``hass`` et ``MockConfigEntry`` (au lieu d'un ``MagicMock``),
monte réellement l'intégration jusqu'à l'état LOADED, puis la décharge.
"""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.octopus_french.const import DOMAIN
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
