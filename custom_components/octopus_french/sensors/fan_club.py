"""Fan Club sensor entity for Octopus Energy France."""

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from ..const import DOMAIN
from ..coordinator_fan_club import (
    OctopusFanClubDataUpdateCoordinator,
    discount_percent,
    forecast_points,
    next_discount_change,
)


class OctopusFanClubDiscountSensor(
    CoordinatorEntity[OctopusFanClubDataUpdateCoordinator], SensorEntity
):
    """Current Fan Club discount of a wind farm, in percent."""

    def __init__(
        self,
        coordinator: OctopusFanClubDataUpdateCoordinator,
        account_number: str,
        discount_source: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the Fan Club discount sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._discount_source = discount_source
        self._attr_unique_id = (
            f"{DOMAIN}_{account_number}_fan_club_{slugify(discount_source)}"
            f"_{description.key}"
        )
        self._attr_translation_key = description.key
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, account_number)})
        self._update_attrs()

    @property
    def available(self) -> bool:
        """Return False when the discount source left the API response."""
        return (
            super().available
            and self.coordinator.get_status(self._discount_source) is not None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        status = self.coordinator.get_status(self._discount_source) or {}
        current = status.get("current") or {}
        next_change = next_discount_change(status, dt_util.now())

        self._attr_native_value = discount_percent(current.get("discount"))
        self._attr_extra_state_attributes: dict[str, Any] = {
            "discount_source": self._discount_source,
            "current_start": current.get("startAt"),
            "next_discount": next_change["discount"] if next_change else None,
            "next_discount_start": (
                next_change["valid_time"].isoformat() if next_change else None
            ),
            "forecast": [
                {
                    "valid_time": point["valid_time"].isoformat(),
                    "discount": point["discount"],
                }
                for point in forecast_points(status)
            ],
        }
