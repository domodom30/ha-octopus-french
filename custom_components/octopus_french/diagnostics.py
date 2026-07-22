"""Diagnostics support for Octopus French Energy."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OctopusFrenchConfigEntry
from .const import CONF_ACCOUNT_NUMBER

TO_REDACT = {
    "email",
    "password",
    "refresh_token",
    "account_id",
    "account_number",
    "number",
    CONF_ACCOUNT_NUMBER,
    "prm",
    "supply_point_id",
    "externalIdentifier",
    "ledger_id",
    "ledger_number",
    "address",
    "offPeakLabel",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OctopusFrenchConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    intelligent = runtime.intelligent_coordinator

    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator_data": async_redact_data(runtime.coordinator.data, TO_REDACT),
        "intelligent_data": (
            async_redact_data(intelligent.data, TO_REDACT) if intelligent else None
        ),
    }
