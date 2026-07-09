"""Tests for the Octopus French Energy config flow."""

from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.octopus_french.config_flow import OctopusFrenchConfigFlow
from custom_components.octopus_french.const import CONF_ACCOUNT_NUMBER
from custom_components.octopus_french.octopus_french import (
    OctopusAuthError,
    OctopusConnectionError,
)
import pytest

_USER_INPUT = {"email": "user@example.fr", "password": "s3cret"}


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
