"""Tests pour l'authentification : refresh token et rate limit Kraken."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest

from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.octopus_french import _async_authenticate
from custom_components.octopus_french.octopus_french import (
    DEFAULT_REFRESH_EXPIRY,
    RATE_LIMIT_ERROR_CODE,
    OctopusFrenchApiClient,
    OctopusRateLimitError,
    TokenManager,
)

RATE_LIMIT_RESPONSE = {
    "data": {"obtainKrakenToken": None},
    "errors": [
        {
            "message": "Too many requests",
            "extensions": {"errorCode": RATE_LIMIT_ERROR_CODE},
        }
    ],
}


def _make_jwt(expires_in: int = 3600) -> str:
    """Build an unsigned JWT expiring in expires_in seconds."""
    exp = datetime.now(UTC).timestamp() + expires_in
    return jwt.encode({"exp": exp}, "x" * 32, algorithm="HS256")


def _login_response(
    token: str,
    refresh_token: str,
    refresh_expires_in: int = 604800,
) -> dict[str, Any]:
    """Build a successful obtainKrakenToken response."""
    return {
        "data": {
            "obtainKrakenToken": {
                "token": token,
                "refreshToken": refresh_token,
                "refreshExpiresIn": refresh_expires_in,
            }
        }
    }


@pytest.fixture
def client() -> OctopusFrenchApiClient:
    """Return an API client whose transport is mocked."""
    api_client = OctopusFrenchApiClient(
        email="user@example.com",
        password="hunter2",
        session=MagicMock(),
    )
    api_client._async_execute = AsyncMock()
    return api_client


def test_set_token_decodes_jwt_expiry() -> None:
    """The access token expiry is read from the JWT itself."""
    manager = TokenManager()

    manager.set_token(_make_jwt(expires_in=3600))

    assert manager.is_valid
    assert 3500 < manager.expires_in <= 3600


def test_set_token_falls_back_when_jwt_is_undecodable() -> None:
    """An opaque token still gets a one-hour expiry rather than none."""
    manager = TokenManager()

    manager.set_token("not-a-jwt")

    assert manager.is_valid


def test_refresh_expiry_defaults_when_api_omits_it() -> None:
    """A refresh token without refreshExpiresIn gets the documented 7-day expiry."""
    manager = TokenManager()

    manager.set_token(_make_jwt(), refresh_token="refresh-1")

    assert manager.is_refresh_valid
    assert manager._refresh_expiry == pytest.approx(
        datetime.now(UTC).timestamp() + DEFAULT_REFRESH_EXPIRY, abs=5
    )


def test_expired_refresh_token_is_not_valid() -> None:
    """An expired refresh token is refused, forcing a full login."""
    manager = TokenManager()

    manager.set_token(_make_jwt(), refresh_token="refresh-1", refresh_expires_in=-1)

    assert not manager.is_refresh_valid


def test_clear_keeps_refresh_token_but_clear_all_drops_it() -> None:
    """clear() only drops the access token, so the refresh token stays reusable."""
    manager = TokenManager()
    manager.set_token(_make_jwt(), refresh_token="refresh-1")

    manager.clear()

    assert not manager.is_valid
    assert manager.is_refresh_valid

    manager.clear_all()

    assert not manager.is_refresh_valid
    assert manager.refresh_token is None


async def test_authenticate_skips_network_when_token_is_valid(
    client: OctopusFrenchApiClient,
) -> None:
    """A valid access token is reused as-is."""
    client.token_manager.set_token(_make_jwt())

    assert await client.authenticate()
    client._async_execute.assert_not_called()


async def test_authenticate_refreshes_without_sending_credentials(
    client: OctopusFrenchApiClient,
) -> None:
    """An expired access token is renewed via the refresh token, not a full login."""
    client.token_manager.set_token(_make_jwt(expires_in=-1), refresh_token="refresh-1")
    client._async_execute.return_value = _login_response(
        _make_jwt(), refresh_token="refresh-2"
    )

    assert await client.authenticate()

    sent_input = client._async_execute.call_args.kwargs["variables"]["input"]
    assert sent_input == {"refreshToken": "refresh-1"}
    assert client.token_manager.refresh_token == "refresh-2"


async def test_authenticate_falls_back_to_login_when_refresh_is_rejected(
    client: OctopusFrenchApiClient,
) -> None:
    """A rejected refresh token is discarded and a full login is attempted."""
    client.token_manager.set_token(
        _make_jwt(expires_in=-1), refresh_token="stale-refresh"
    )
    client._async_execute.side_effect = [
        {"data": {"obtainKrakenToken": None}, "errors": [{"message": "Invalid token"}]},
        _login_response(_make_jwt(), refresh_token="refresh-2"),
    ]

    assert await client.authenticate()

    first_input, second_input = (
        call.kwargs["variables"]["input"]
        for call in client._async_execute.call_args_list
    )
    assert first_input == {"refreshToken": "stale-refresh"}
    assert second_input == {"email": "user@example.com", "password": "hunter2"}
    assert client.token_manager.refresh_token == "refresh-2"


async def test_authenticate_returns_false_on_invalid_credentials(
    client: OctopusFrenchApiClient,
) -> None:
    """Genuinely wrong credentials still report an authentication failure."""
    client._async_execute.return_value = {
        "data": {"obtainKrakenToken": None},
        "errors": [{"message": "Invalid data"}],
    }

    assert not await client.authenticate()


async def test_authenticate_raises_on_rate_limit(
    client: OctopusFrenchApiClient,
) -> None:
    """A rate limited login is an error, not an invalid-credentials verdict."""
    client._async_execute.return_value = RATE_LIMIT_RESPONSE

    with pytest.raises(OctopusRateLimitError):
        await client.authenticate()


async def test_execute_with_auth_raises_on_rate_limit(
    client: OctopusFrenchApiClient,
) -> None:
    """A rate limited query is not retried as an expired token."""
    client.token_manager.set_token(_make_jwt())
    client._async_execute.return_value = RATE_LIMIT_RESPONSE

    with pytest.raises(OctopusRateLimitError):
        await client.execute_with_auth(query="query { viewer { id } }")

    assert client._async_execute.call_count == 1


async def test_setup_retries_later_when_rate_limited(
    client: OctopusFrenchApiClient,
) -> None:
    """Setup backs off on a rate limit instead of prompting for re-authentication."""
    client._async_execute.return_value = RATE_LIMIT_RESPONSE

    with pytest.raises(ConfigEntryNotReady):
        await _async_authenticate(client)
