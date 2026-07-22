"""Tests for the Octopus French Energy config flow."""

from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.octopus_french.config_flow import OctopusFrenchConfigFlow
from custom_components.octopus_french.const import CONF_ACCOUNT_NUMBER
from custom_components.octopus_french.octopus_french import (
    OctopusAuthError,
    OctopusConnectionError,
)

_USER_INPUT = {"email": "user@example.fr", "password": "s3cret"}


@pytest.fixture(autouse=True)
def _mock_clientsession():
    """Avoid building a real aiohttp session (which would create a shared Zeroconf
    instance and trip HA's frame helper) since the API client is mocked anyway."""
    with patch(
        "custom_components.octopus_french.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield


@pytest.fixture
def flow() -> OctopusFrenchConfigFlow:
    """Return a config flow instance with a mocked hass and unique-id helpers."""
    instance = OctopusFrenchConfigFlow()
    instance.hass = MagicMock()
    instance.async_set_unique_id = AsyncMock()
    instance._abort_if_unique_id_configured = MagicMock()
    return instance


def _patch_client(
    *, authenticate: object = True, accounts: object = None
) -> AbstractContextManager[MagicMock]:
    """Patch OctopusFrenchApiClient with an async mock client."""
    client = MagicMock()
    if isinstance(authenticate, Exception):
        client.authenticate = AsyncMock(side_effect=authenticate)
    else:
        client.authenticate = AsyncMock(return_value=authenticate)
    if isinstance(accounts, Exception):
        client.get_accounts = AsyncMock(side_effect=accounts)
    else:
        client.get_accounts = AsyncMock(return_value=accounts or [])
    return patch(
        "custom_components.octopus_french.config_flow.OctopusFrenchApiClient",
        return_value=client,
    )


async def test_user_step_shows_form(flow: OctopusFrenchConfigFlow) -> None:
    """The initial step shows the user form."""
    result = await flow.async_step_user(None)

    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_single_account_creates_entry(flow: OctopusFrenchConfigFlow) -> None:
    """A single account creates the entry directly."""
    with _patch_client(accounts=[{"number": "A-123"}]):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["type"] == "create_entry"
    assert result["data"][CONF_ACCOUNT_NUMBER] == "A-123"
    flow.async_set_unique_id.assert_awaited_once_with("A-123")


async def test_multiple_accounts_show_account_step(
    flow: OctopusFrenchConfigFlow,
) -> None:
    """Multiple accounts route to the account selection step."""
    with _patch_client(accounts=[{"number": "A-1"}, {"number": "A-2"}]):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["type"] == "form"
    assert result["step_id"] == "account"


async def test_account_step_creates_entry(flow: OctopusFrenchConfigFlow) -> None:
    """Selecting an account in the account step creates the entry."""
    flow.email = _USER_INPUT["email"]
    flow.password = _USER_INPUT["password"]
    flow.accounts = [{"number": "A-1"}, {"number": "A-2"}]

    result = await flow.async_step_account({CONF_ACCOUNT_NUMBER: "A-2"})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_ACCOUNT_NUMBER] == "A-2"
    # The unique_id must track the account actually selected, not accounts[0].
    flow.async_set_unique_id.assert_awaited_once_with("A-2")


async def test_invalid_auth(flow: OctopusFrenchConfigFlow) -> None:
    """Failed authentication surfaces invalid_auth."""
    with _patch_client(authenticate=False):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_no_accounts(flow: OctopusFrenchConfigFlow) -> None:
    """An account list without entries surfaces no_accounts."""
    with _patch_client(accounts=[]):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["type"] == "form"
    assert result["errors"] == {"base": "no_accounts"}


async def test_auth_error_surfaces_invalid_auth(
    flow: OctopusFrenchConfigFlow,
) -> None:
    """An OctopusAuthError raised while fetching accounts maps to invalid_auth."""
    with _patch_client(accounts=OctopusAuthError("bad token")):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["errors"] == {"base": "invalid_auth"}


async def test_connection_error_surfaces_cannot_connect(
    flow: OctopusFrenchConfigFlow,
) -> None:
    """An OctopusConnectionError maps to cannot_connect (not an uncaught crash)."""
    with _patch_client(authenticate=OctopusConnectionError("no network")):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_value_error_surfaces_invalid_auth(
    flow: OctopusFrenchConfigFlow,
) -> None:
    """A ValueError while fetching accounts maps to invalid_auth."""
    with _patch_client(accounts=ValueError("bad payload")):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["errors"] == {"base": "invalid_auth"}


async def test_parsing_error_surfaces_unknown(flow: OctopusFrenchConfigFlow) -> None:
    """An unexpected parsing error (KeyError…) maps to unknown."""
    with _patch_client(accounts=KeyError("number")):
        result = await flow.async_step_user(_USER_INPUT)

    assert result["errors"] == {"base": "unknown"}


async def test_reauth_step_routes_to_confirm(flow: OctopusFrenchConfigFlow) -> None:
    """The reauth entry point routes to the confirm step."""
    result = await flow.async_step_reauth({})

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_confirm_shows_form(flow: OctopusFrenchConfigFlow) -> None:
    """The reauth confirm step shows its form."""
    result = await flow.async_step_reauth_confirm(None)

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_confirm_success(flow: OctopusFrenchConfigFlow) -> None:
    """A successful reauth updates and reloads the entry."""
    reauth_entry = MagicMock()
    reauth_entry.data = {"email": _USER_INPUT["email"]}
    flow._get_reauth_entry = MagicMock(return_value=reauth_entry)
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reauth_successful"}
    )

    with _patch_client(authenticate=True):
        result = await flow.async_step_reauth_confirm({"password": "new-pw"})

    assert result["reason"] == "reauth_successful"
    flow.async_update_reload_and_abort.assert_called_once()


async def test_reauth_confirm_invalid_auth(flow: OctopusFrenchConfigFlow) -> None:
    """A failed reauth surfaces invalid_auth."""
    reauth_entry = MagicMock()
    reauth_entry.data = {"email": _USER_INPUT["email"]}
    flow._get_reauth_entry = MagicMock(return_value=reauth_entry)

    with _patch_client(authenticate=False):
        result = await flow.async_step_reauth_confirm({"password": "new-pw"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_confirm_auth_error(flow: OctopusFrenchConfigFlow) -> None:
    """An OctopusAuthError during reauth maps to invalid_auth."""
    reauth_entry = MagicMock()
    reauth_entry.data = {"email": _USER_INPUT["email"]}
    flow._get_reauth_entry = MagicMock(return_value=reauth_entry)

    with _patch_client(authenticate=OctopusAuthError("bad token")):
        result = await flow.async_step_reauth_confirm({"password": "new-pw"})

    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_confirm_connection_error(flow: OctopusFrenchConfigFlow) -> None:
    """An OctopusConnectionError during reauth maps to cannot_connect."""
    reauth_entry = MagicMock()
    reauth_entry.data = {"email": _USER_INPUT["email"]}
    flow._get_reauth_entry = MagicMock(return_value=reauth_entry)

    with _patch_client(authenticate=OctopusConnectionError("no network")):
        result = await flow.async_step_reauth_confirm({"password": "new-pw"})

    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_confirm_purges_persisted_refresh_token(
    flow: OctopusFrenchConfigFlow,
) -> None:
    """A successful reauth drops the refresh token of the old session."""
    reauth_entry = MagicMock()
    reauth_entry.data = {
        "email": _USER_INPUT["email"],
        "password": "old-pw",
        "refresh_token": "stale",
        "refresh_token_expiry": 123.0,
    }
    flow._get_reauth_entry = MagicMock(return_value=reauth_entry)
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reauth_successful"}
    )

    with _patch_client(authenticate=True):
        await flow.async_step_reauth_confirm({"password": "new-pw"})

    new_data = flow.async_update_reload_and_abort.call_args.kwargs["data"]
    assert new_data["password"] == "new-pw"
    assert "refresh_token" not in new_data
    assert "refresh_token_expiry" not in new_data
