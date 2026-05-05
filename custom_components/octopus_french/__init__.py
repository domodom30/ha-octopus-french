"""The Octopus French Energy integration."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform, UnitOfApparentPower
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SERVICE_FORCE_UPDATE
from .coordinator import OctopusFrenchDataUpdateCoordinator
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator
from .octopus_french import OctopusFrenchApiClient

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class OctopusFrenchRuntimeData:
    """Runtime data stored in config entry."""

    coordinator: OctopusFrenchDataUpdateCoordinator
    account_number: str
    intelligent_coordinator: OctopusIntelligentDataUpdateCoordinator | None = field(default=None)


type OctopusFrenchConfigEntry = ConfigEntry[OctopusFrenchRuntimeData]

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Octopus French Energy integration."""

    async def handle_force_update(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        handle_force_update,
        schema=vol.Schema({}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OctopusFrenchConfigEntry) -> bool:
    """Set up Octopus French Energy from a config entry."""
    session = async_get_clientsession(hass)
    api_client = OctopusFrenchApiClient(
        email=entry.data["email"],
        password=entry.data["password"],
        session=session,
    )

    await _async_authenticate(api_client)

    account_number = await _async_get_account_number(
        api_client, entry.data.get("account_number", "")
    )

    coordinator = OctopusFrenchDataUpdateCoordinator(
        hass=hass,
        api_client=api_client,
        account_number=account_number,
        config_entry=entry,
    )

    await _async_fetch_initial_data(coordinator)

    intelligent_coordinator = await _async_setup_intelligent_coordinator(
        hass, api_client, account_number
    )

    entry.runtime_data = OctopusFrenchRuntimeData(
        coordinator=coordinator,
        account_number=account_number,
        intelligent_coordinator=intelligent_coordinator,
    )

    await _async_create_devices(hass, entry, coordinator)

    if intelligent_coordinator is not None:
        await _async_create_intelligent_devices(hass, entry, intelligent_coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_authenticate(api_client: OctopusFrenchApiClient) -> None:
    if not await api_client.authenticate():
        raise ConfigEntryAuthFailed("Authentication failed - invalid credentials")


async def _async_setup_intelligent_coordinator(
    hass: HomeAssistant,
    api_client: OctopusFrenchApiClient,
    account_number: str,
) -> OctopusIntelligentDataUpdateCoordinator | None:
    """Set up the Intelligent coordinator, returns None if not available."""
    try:
        coordinator = OctopusIntelligentDataUpdateCoordinator(
            hass=hass,
            api_client=api_client,
            account_number=account_number,
        )
        await coordinator.async_config_entry_first_refresh()
        if not coordinator.data.get("devices"):
            _LOGGER.debug("No Intelligent devices found for account %s", account_number)
            return None
        return coordinator
    except Exception as err:
        _LOGGER.debug("Octopus Intelligent not available for this account: %s", err)
        return None


async def _async_fetch_initial_data(
    coordinator: OctopusFrenchDataUpdateCoordinator,
) -> None:
    """Fetch initial data from the coordinator."""
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
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
            manufacturer="Octopus Energy France",
            model="Compte client",
        )

    for elec_meter in supply_points.get("electricity", []):
        prm_id = elec_meter.get("prm")
        if not prm_id:
            continue

        meter_kind = elec_meter.get("meterKind", "N/A")
        suscribed_max_power = elec_meter.get("subscribedMaxPower", "N/A")
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(prm_id))},
            name=f"{meter_kind} {prm_id}",
            manufacturer="Enedis",
            model=f"{elec_meter.get('meterKind', 'N/A')} - {suscribed_max_power} {UnitOfApparentPower.KILO_VOLT_AMPERE}",
        )

    for gas_meter in supply_points.get("gas", []):
        pce_ref = gas_meter.get("prm")
        if not pce_ref:
            continue

        is_smart = gas_meter.get("isSmartMeter", False)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(pce_ref))},
            name=f"Gazpar {pce_ref}",
            manufacturer="GrDF",
            model="Gazpar" if is_smart else "Compteur gaz traditionnel",
        )


async def _async_create_intelligent_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: OctopusIntelligentDataUpdateCoordinator,
) -> None:
    """Create vehicle devices for Octopus Intelligent."""
    device_registry = dr.async_get(hass)
    account_number = entry.data.get("account_number")

    for device in coordinator.data.get("devices", []):
        device_id = device.get("id")
        if not device_id:
            continue

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(device_id))},
            name=device.get("name") or device_id,
            manufacturer=device.get("chargePointMake"),
            model=device.get("chargePointModel"),
            via_device=(DOMAIN, str(account_number)) if account_number else None,
        )


async def async_unload_entry(hass: HomeAssistant, entry: OctopusFrenchConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
