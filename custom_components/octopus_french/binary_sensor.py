"""Binary sensors for OctopusFrench Energy integration."""

from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .utils import find_contract_hc_slots, parse_off_peak_hours, parse_time_slots

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OctopusFrench binary sensors."""
    coordinator = config_entry.runtime_data.coordinator

    if not (data := coordinator.data):
        return

    if not isinstance(data, dict):
        return

    sensors = []

    supply_points = data.get("supply_points", {})
    electricity_points = supply_points.get("electricity", [])

    for meter in electricity_points:
        prm_id = meter.get("id")
        if not prm_id:
            continue

        # Le capteur HC est créé dès qu'une source d'horaires existe.
        # La logique de sélection de source est déléguée au capteur lui-même
        # (relecture dynamique à chaque mise à jour du coordinateur).
        off_peak_label = meter.get("offPeakLabel")
        contract_slots = find_contract_hc_slots(data, prm_id)

        if contract_slots or off_peak_label:
            sensors.append(
                OctopusFrenchHcBinarySensor(
                    coordinator=coordinator,
                    prm_id=prm_id,
                )
            )

    if sensors:
        async_add_entities(sensors)


class OctopusFrenchHcBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if current time is in HC (Heures Creuses) period.

    Priorité des sources d'horaires (ordre décroissant de fiabilité) :
      1. timeSlots du contrat actif (données structurées, API)
      2. offPeakLabel du compteur Linky (parsing regex, moins fiable)
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, prm_id: str) -> None:
        """Initialize the HC binary sensor."""
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_hc_active"
        self._attr_translation_key = "hc_active"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prm_id)},
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Mise à jour chaque minute (le tick second=0 suffit)
        self.async_on_remove(
            async_track_time_change(self.hass, self._async_update_state, second=0)
        )

    async def _async_update_state(self, now=None) -> None:
        """Update state based on current time."""
        self.async_write_ha_state()

    # ── Résolution de la source d'horaires ────────────────────────────────────

    def _resolve_hc_schedule(self) -> dict[str, Any]:
        """Return the best available HC schedule from coordinator data.

        Returns a dict with keys: ranges, total_hours, range_count, source, type.
        'source' is 'contract' or 'linky'.
        """
        data = self.coordinator.data or {}

        # Source 1 : timeSlots du contrat (plus fiable)
        if contract_slots := find_contract_hc_slots(data, self._prm_id):
            schedule = parse_time_slots(contract_slots)
            if schedule["range_count"] > 0:
                return schedule

        # Source 2 : offPeakLabel Linky (fallback regex)
        supply_points = data.get("supply_points", {})
        for meter in supply_points.get("electricity", []):
            if meter.get("id") == self._prm_id:
                off_peak_label = meter.get("offPeakLabel")
                if off_peak_label:
                    schedule = parse_off_peak_hours(off_peak_label)
                    schedule["source"] = "linky"
                    return schedule
                break

        return {"ranges": [], "total_hours": 0.0, "range_count": 0,
                "source": "none", "type": None}

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._resolve_hc_schedule()["range_count"] > 0
        )

    @property
    def is_on(self) -> bool:
        """Return True if current time is within HC periods."""
        schedule = self._resolve_hc_schedule()
        if not schedule["ranges"]:
            return False
        try:
            now = dt_util.now().time()
        except (AttributeError, ValueError):
            return False
        return any(
            self._is_time_in_range(now, r["start"], r["end"])
            for r in schedule["ranges"]
        )

    @staticmethod
    def _is_time_in_range(current_time: time, start_str: str, end_str: str) -> bool:
        """Check if current_time is within [start_str, end_str] (handles overnight)."""
        try:
            sh, sm = start_str.split(":")[:2]
            eh, em = end_str.split(":")[:2]
            start_min = int(sh) * 60 + int(sm)
            end_min = int(eh) * 60 + int(em)
            cur_min = current_time.hour * 60 + current_time.minute
        except (ValueError, IndexError):
            return False

        if end_min <= start_min:  # plage chevauchant minuit
            return cur_min >= start_min or cur_min <= end_min
        return start_min <= cur_min <= end_min

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return HC schedule information."""
        schedule = self._resolve_hc_schedule()
        ranges = schedule["ranges"]

        attributes: dict[str, Any] = {
            "hc_schedule_available": len(ranges) > 0,
            "total_hc_hours": schedule["total_hours"],
            "hc_type": schedule.get("type") or "Unknown",
            "hc_source": schedule["source"],
        }

        for i, r in enumerate(ranges, 1):
            attributes[f"hc_range_{i}"] = f"{r['start']} - {r['end']}"
            attributes[f"hc_range_{i}_duration_h"] = r["duration_hours"]

        return attributes

    @property
    def icon(self) -> str:
        """Return dynamic icon based on state."""
        return "mdi:clock-check" if self.is_on else "mdi:clock-outline"
