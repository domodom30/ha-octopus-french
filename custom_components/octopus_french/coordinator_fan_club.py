"""Data update coordinator for the Octopus Fan Club offer."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.fan_club import OctopusFanClubApiClient
from .const import FAN_CLUB_SCAN_INTERVAL
from .octopus_french import OctopusAuthError, OctopusConnectionError

if TYPE_CHECKING:
    from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)


def discount_percent(value: Any) -> float | None:
    """Convert an API discount ratio ("0.200") to a percentage (20.0)."""
    try:
        return round(float(value) * 100, 1)
    except (TypeError, ValueError):
        return None


def forecast_points(status: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the projected discounts of a status, sorted by time."""
    points = []
    for point in (status.get("forecast") or {}).get("data") or []:
        valid_time = dt_util.parse_datetime(point.get("validTime") or "")
        percent = discount_percent(point.get("projectedDiscount"))
        if valid_time is not None and percent is not None:
            points.append({"valid_time": valid_time, "discount": percent})
    return sorted(points, key=lambda point: point["valid_time"])


def next_discount_change(
    status: dict[str, Any], now: datetime
) -> dict[str, Any] | None:
    """Return the first forecast point after now with a different discount."""
    current = discount_percent((status.get("current") or {}).get("discount"))
    for point in forecast_points(status):
        if point["valid_time"] > now and point["discount"] != current:
            return point
    return None


class OctopusFanClubDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Fan Club discounts from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: OctopusFrenchApiClient,
        account_number: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Octopus Fan Club",
            update_interval=timedelta(minutes=FAN_CLUB_SCAN_INTERVAL),
            config_entry=config_entry,
        )
        self.fan_club_client = OctopusFanClubApiClient(api_client)
        self.account_number = account_number

    def get_status(self, discount_source: str) -> dict[str, Any] | None:
        """Return the status of a discount source."""
        return ((self.data or {}).get("statuses") or {}).get(discount_source)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the Fan Club statuses from API."""
        try:
            statuses = await self.fan_club_client.get_fan_club_status(
                self.account_number
            )
        except OctopusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (OctopusConnectionError, RuntimeError) as err:
            raise UpdateFailed(f"Error communicating with Fan Club API: {err}") from err

        return {"statuses": {status["discountSource"]: status for status in statuses}}
