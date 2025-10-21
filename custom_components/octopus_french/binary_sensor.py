"""Binary sensors for OctopusFrench Energy integration."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Final

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

from .const import DOMAIN
from .utils import parse_off_peak_hours

# Constants
ATTR_HC_SCHEDULE_AVAILABLE: Final = "hc_schedule_available"
ATTR_TOTAL_HC_HOURS: Final = "total_hc_hours"
ATTR_HC_TYPE: Final = "hc_type"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OctopusFrench binary sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    # Validate coordinator data
    if not (data := coordinator.data):
        return

    if not isinstance(data, dict):
        return

    sensors = []

    # Find electricity meters with off-peak hours
    supply_points = data.get("supply_points", {})
    electricity_points = supply_points.get("electricity", [])

    for meter in electricity_points:
        prm_id = meter.get("id")
        status = meter.get("distributorStatus")
        powered = meter.get("poweredStatus")

        # Ignorer les compteurs résiliés
        if status == "RESIL" and powered == "LIMI":
            continue

        off_peak_label = meter.get("offPeakLabel")

        if off_peak_label:
            off_peak_data = parse_off_peak_hours(off_peak_label)

            if off_peak_data["ranges"]:
                # Create attributes from off-peak data
                electricity_attributes = {
                    "off_peak_type": off_peak_data["type"],
                    "off_peak_total_hours": off_peak_data["total_hours"],
                    "off_peak_range_count": off_peak_data["range_count"],
                }

                # Add each range
                for i, time_range in enumerate(off_peak_data["ranges"], 1):
                    electricity_attributes[f"off_peak_range_{i}_start"] = time_range[
                        "start"
                    ]
                    electricity_attributes[f"off_peak_range_{i}_end"] = time_range[
                        "end"
                    ]
                    electricity_attributes[f"off_peak_range_{i}_duration"] = time_range[
                        "duration_hours"
                    ]

                # Create HC binary sensor for this meter
                hc_sensor = OctopusFrenchHcBinarySensor(
                    coordinator=coordinator,
                    prm_id=prm_id,  # ✅ Passer le PRM ID au lieu de account_number
                    electricity_sensor_attributes=electricity_attributes,
                )
                sensors.append(hc_sensor)

    if sensors:
        async_add_entities(sensors)


class OctopusFrenchHcBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if current time is in HC (Heures Creuses) period."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator,
        prm_id: str,
        electricity_sensor_attributes: dict[str, Any],
    ) -> None:
        """Initialize the HC binary sensor."""
        super().__init__(coordinator)
        self._prm_id = prm_id
        self._attributes = electricity_sensor_attributes
        self._attr_unique_id = f"{DOMAIN}_{prm_id}_hc_active"
        self._attr_translation_key = "hc_active"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prm_id)},
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_time_change(self.hass, self._async_update_state, second=0)
        )

    async def _async_update_state(self, now=None) -> None:
        """Update state based on current time."""
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Heures creuses actives"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._attributes.get("off_peak_range_count", 0) > 0
        )

    @property
    def is_on(self) -> bool:
        """Return True if current time is within HC periods."""
        return self._is_current_time_in_hc()

    def _is_current_time_in_hc(self) -> bool:
        """Check if current time falls within any HC time range."""
        try:
            now = datetime.now().time()
            range_count = self._attributes.get("off_peak_range_count", 0)

        except (AttributeError, KeyError, ValueError):
            return False

        else:
            for i in range(1, range_count + 1):
                start_attr = f"off_peak_range_{i}_start"
                end_attr = f"off_peak_range_{i}_end"

                if start_attr in self._attributes and end_attr in self._attributes:
                    start_time_str = self._attributes[start_attr]
                    end_time_str = self._attributes[end_attr]

                    if self._is_time_in_range(now, start_time_str, end_time_str):
                        return True
            return False

    def _is_time_in_range(
        self, current_time: time, start_str: str, end_str: str
    ) -> bool:
        """Check if current time is within a time range (handles overnight ranges)."""
        try:
            start_parts = start_str.split(":")
            end_parts = end_str.split(":")

            start_time = time(int(start_parts[0]), int(start_parts[1]))
            end_time = time(int(end_parts[0]), int(end_parts[1]))

            current_minutes = current_time.hour * 60 + current_time.minute
            start_minutes = start_time.hour * 60 + start_time.minute
            end_minutes = end_time.hour * 60 + end_time.minute

        except (ValueError, IndexError):
            return False

        else:
            if end_minutes <= start_minutes:
                return (current_minutes >= start_minutes) or (
                    current_minutes <= end_minutes
                )

            return start_minutes <= current_minutes <= end_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return HC schedule information."""
        range_count = self._attributes.get("off_peak_range_count", 0)

        attributes = {
            ATTR_HC_SCHEDULE_AVAILABLE: range_count > 0,
            ATTR_TOTAL_HC_HOURS: self._attributes.get("off_peak_total_hours", 0),
            ATTR_HC_TYPE: self._attributes.get("off_peak_type", "Unknown"),
        }

        # Add individual HC ranges in a readable format
        for i in range(1, range_count + 1):
            start_attr = f"off_peak_range_{i}_start"
            end_attr = f"off_peak_range_{i}_end"
            duration_attr = f"off_peak_range_{i}_duration"

            if all(
                attr in self._attributes
                for attr in [start_attr, end_attr, duration_attr]
            ):
                attributes[f"hc_range_{i}"] = (
                    f"{self._attributes[start_attr]} - {self._attributes[end_attr]}"
                )

        return attributes

    @property
    def icon(self) -> str:
        """Return dynamic icon based on state."""
        return "mdi:clock-check" if self.is_on else "mdi:clock-outline"
