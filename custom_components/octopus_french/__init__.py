"""The Octopus Energy French integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_ACCOUNT_NUMBER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .lib.octopus_french import OctopusFrenchClient
from .coordinator import OctopusDataUpdateCoordinator
from .utils.logger import LOGGER

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus Energy French from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    if entry.entry_id in hass.data[DOMAIN]:
        LOGGER.warning(f"Entry {entry.entry_id} already exists, skipping setup")
        return False

    session = aiohttp_client.async_get_clientsession(hass)
    client = OctopusFrenchClient(
        entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], session
    )

    # Authenticate
    if not await client.authenticate():
        LOGGER.error("Authentication failed for Octopus Energy French")
        return False

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = OctopusDataUpdateCoordinator(
        hass, client, entry.data[CONF_ACCOUNT_NUMBER], scan_interval
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        CONF_ACCOUNT_NUMBER: entry.data[CONF_ACCOUNT_NUMBER],
        CONF_SCAN_INTERVAL: scan_interval,  # Stocker dans l'entrée spécifique
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
