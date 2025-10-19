"""The Octopus French Energy integration."""

from __future__ import annotations

from contextlib import suppress

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import OctopusFrenchDataUpdateCoordinator
from .octopus_french import OctopusFrenchApiClient

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus French Energy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize API client
    api_client = OctopusFrenchApiClient(
        email=entry.data["email"],
        password=entry.data["password"],
    )

    # Authenticate
    await _async_authenticate(api_client)

    # Get account number
    account_number = await _async_get_account_number(
        api_client, entry.data.get("account_number", "")
    )

    # Initialize coordinator
    coordinator = OctopusFrenchDataUpdateCoordinator(
        hass=hass,
        api_client=api_client,
        account_number=account_number,
    )

    # Fetch initial data
    await _async_fetch_initial_data(coordinator, api_client)

    # Store data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api_client,
        "account_number": account_number,
    }

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_authenticate(api_client: OctopusFrenchApiClient) -> None:
    """Authenticate with the API."""
    try:
        if not await api_client.authenticate():
            raise ConfigEntryAuthFailed("Authentication failed - invalid credentials")
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Authentication error: {err}") from err


async def _async_fetch_initial_data(
    coordinator: OctopusFrenchDataUpdateCoordinator,
    api_client: OctopusFrenchApiClient,
) -> None:
    """Fetch initial data from the coordinator."""
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        await api_client.close()
        raise ConfigEntryNotReady(f"Initial data fetch failed: {err}") from err


async def _async_get_account_number(
    api_client: OctopusFrenchApiClient, configured_account: str
) -> str:
    """Get and validate account number."""
    with suppress(Exception):
        accounts = await api_client.get_accounts()
        if not accounts:
            return configured_account or ""

        account_numbers = [account["number"] for account in accounts]

        # Use configured account if valid, otherwise use first available
        if configured_account and configured_account in account_numbers:
            return configured_account

        if account_numbers:
            return account_numbers[0]

    return configured_account or ""


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up data
        data = hass.data[DOMAIN].pop(entry.entry_id)

        # Close API client
        if api_client := data.get("api"):
            with suppress(Exception):
                await api_client.close()

    return unload_ok
