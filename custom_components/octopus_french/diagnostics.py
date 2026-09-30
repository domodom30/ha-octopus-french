"""Diagnostics support for Octopus French Energy."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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


_ENTITY_ATTRIBUTES_TO_SKIP = frozenset(
    {
        "attribution",
        "device_class",
        "friendly_name",
        "icon",
        "state_class",
        "unit_of_measurement",
    }
)


def _redact_meter_keys(
    coordinator_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Redact meter IDs used as dict keys and return the token mapping."""
    redacted = dict(coordinator_data or {})
    mapping: dict[str, str] = {}
    for key in ("electricity_by_prm", "gas_by_pce"):
        if by_meter := redacted.get(key):
            renamed = {}
            for meter_id, value in by_meter.items():
                token = mapping.setdefault(
                    str(meter_id), f"**REDACTED_{len(mapping)}**"
                )
                renamed[token] = value
            redacted[key] = renamed
    return redacted, mapping


def _redact_identifiers(text: str, mapping: dict[str, str]) -> str:
    """Replace each known meter ID with its token."""
    for meter_id, token in mapping.items():
        text = text.replace(meter_id, token)
    return text


def _entity_states(
    hass: HomeAssistant, entry: OctopusFrenchConfigEntry, mapping: dict[str, str]
) -> dict[str, Any]:
    """Return the redacted state and attributes of each entry entity."""
    registry = er.async_get(hass)
    states: dict[str, Any] = {}

    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(entity.entity_id)
        key = _redact_identifiers(entity.unique_id, mapping)
        states[key] = {
            "entity_id": _redact_identifiers(entity.entity_id, mapping),
            "disabled": entity.disabled_by is not None,
            "state": state.state if state else None,
            "attributes": (
                {
                    name: value
                    for name, value in state.attributes.items()
                    if name not in _ENTITY_ATTRIBUTES_TO_SKIP
                }
                if state
                else None
            ),
            "last_changed": state.last_changed if state else None,
        }

    return states


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OctopusFrenchConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    intelligent = runtime.intelligent_coordinator
    coordinator_data, meter_mapping = _redact_meter_keys(runtime.coordinator.data)

    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator_data": async_redact_data(coordinator_data, TO_REDACT),
        "intelligent_data": (
            async_redact_data(intelligent.data, TO_REDACT) if intelligent else None
        ),
        "entities": async_redact_data(
            _entity_states(hass, entry, meter_mapping), TO_REDACT
        ),
    }
