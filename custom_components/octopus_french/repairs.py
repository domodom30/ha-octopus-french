"""Repair issues for Octopus French data anomalies."""

import hashlib
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    COST_KEY_TO_LABEL,
    DOMAIN,
    ENERGY_KEY_TO_LABEL,
    ISSUE_HC_FALLBACK_LINKY,
    ISSUE_UNKNOWN_CONSUMPTION_LABEL,
    TEMPO_TEMPORAL_CLASS_CODES,
)
from .utils import (
    get_tempo_color_for_prm,
    normalize_consumption_label,
    resolve_hc_schedule,
)

_LOGGER = logging.getLogger(__name__)

_LABELS_WITHOUT_STATISTIC = frozenset({"ABONNEMENT"})

_KNOWN_LABELS = frozenset(ENERGY_KEY_TO_LABEL.values()) | frozenset(
    COST_KEY_TO_LABEL.values()
)


def _safe_key(template: str, identifier: str) -> str:
    """Return an issue key with a hashed meter ID."""
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
    return template.format(digest)


def _meters_on_linky_fallback(data: dict[str, Any]) -> list[str]:
    """Return Tempo PRMs whose off-peak ranges fall back to the meter label."""
    fallbacks = []
    for meter in data.get("supply_points", {}).get("electricity", []):
        prm_id = meter.get("prm")
        if not prm_id:
            continue
        color = get_tempo_color_for_prm(data, prm_id)
        if resolve_hc_schedule(data, prm_id, color).get("source") == "linky":
            classes = {
                (c.get("code") or "").upper()
                for c in meter.get("provider_temporal_classes") or []
            }
            if classes & TEMPO_TEMPORAL_CLASS_CODES:
                fallbacks.append(prm_id)
    return fallbacks


def _unknown_consumption_labels(data: dict[str, Any]) -> set[str]:
    """Return consumption labels that feed no statistic."""
    unknown = set()
    for prm_data in (data.get("electricity_by_prm") or {}).values():
        for reading in prm_data.get("readings") or []:
            for stat in (reading.get("metaData") or {}).get("statistics", []):
                label = normalize_consumption_label(stat.get("label", ""))
                if (
                    label
                    and label not in _KNOWN_LABELS
                    and label not in _LABELS_WITHOUT_STATISTIC
                ):
                    unknown.add(label)
    return unknown


def async_update_issues(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Create or delete repair issues from the current data."""
    active: set[str] = set()

    for prm_id in _meters_on_linky_fallback(data):
        issue_id = _safe_key(ISSUE_HC_FALLBACK_LINKY, prm_id)
        active.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="hc_fallback_linky",
        )

    for label in _unknown_consumption_labels(data):
        issue_id = _safe_key(ISSUE_UNKNOWN_CONSUMPTION_LABEL, label)
        active.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="unknown_consumption_label",
            translation_placeholders={"label": label},
        )

    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id not in active:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
