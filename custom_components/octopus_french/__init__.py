"""The Octopus French Energy integration."""

from __future__ import annotations

from contextlib import suppress
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, UnitOfApparentPower
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, SERVICE_FORCE_UPDATE
from .coordinator import OctopusFrenchDataUpdateCoordinator
from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus French Energy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api_client = OctopusFrenchApiClient(
        email=entry.data["email"],
        password=entry.data["password"],
    )

    await _async_authenticate(api_client)

    account_number = await _async_get_account_number(
        api_client, entry.data.get("account_number", "")
    )

    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    coordinator = OctopusFrenchDataUpdateCoordinator(
        hass=hass,
        api_client=api_client,
        account_number=account_number,
        scan_interval=scan_interval,
    )

    await _async_fetch_initial_data(coordinator, api_client)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api_client,
        "account_number": account_number,
    }

    await _async_create_devices(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Octopus Energy France."""

    async def handle_force_update(call: ServiceCall):
        for data in hass.data.get(DOMAIN, {}).values():
            coordinator = data.get("coordinator")
            if coordinator:
                await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        handle_force_update,
        schema=vol.Schema({}),
    )

    _LOGGER.debug("Services registered successfully")


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_authenticate(api_client: OctopusFrenchApiClient) -> None:
    if not await api_client.authenticate():
        raise ConfigEntryAuthFailed("Authentication failed - invalid credentials")


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

        if configured_account and configured_account in account_numbers:
            return configured_account

        if account_numbers:
            return account_numbers[0]

    return configured_account or ""


async def _async_create_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: OctopusFrenchDataUpdateCoordinator,
) -> None:
    """Create devices for all meters."""
    device_registry = dr.async_get(hass)
    account_number = entry.data.get("account_number")
    supply_points = coordinator.data.get("supply_points", {})

    if account_number:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(account_number))},
            name="Compte Octopus Energy",
            model="Compte client",
        )

    for elec_meter in supply_points.get("electricity", []):
        prm_id = elec_meter.get("id")
        if not prm_id:
            continue

        meter_kind = elec_meter.get("meterKind", "N/A")
        suscribed_max_power = elec_meter.get("subscribedMaxPower", "N/A")
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(prm_id))},
            name=f"{meter_kind} {prm_id}",
            model=f"{elec_meter.get('meterKind', 'N/A')} - {suscribed_max_power} {UnitOfApparentPower.KILO_VOLT_AMPERE}",
        )

    for gas_meter in supply_points.get("gas", []):
        pce_ref = gas_meter.get("id")
        if not pce_ref:
            continue

        is_smart = gas_meter.get("isSmartMeter", False)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(pce_ref))},
            name=f"Gazpar {pce_ref}",
            model="Gazpar" if is_smart else "Compteur gaz traditionnel",
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)

        if api_client := data.get("api"):
            with suppress(Exception):
                await api_client.close()
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
        _LOGGER.debug("Services unregistered")
    return unload_ok
