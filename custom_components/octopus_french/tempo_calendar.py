"""Fetch dated Tempo announcements from the public Calendrier Tempo API."""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.util import dt as dt_util

from .const import TEMPO_TIME_ZONE

_LOGGER = logging.getLogger(__name__)
_API_URL = "https://www.calendrier-tempo.fr/api"
_TIMEOUT = ClientTimeout(total=5)
_REFRESH_SECONDS = 3600


class TempoCalendar:
    """Share a bounded, date-keyed announcement cache across Octopus entries."""

    def __init__(self, session: ClientSession) -> None:
        """Initialize the client without making a network request."""
        self._session = session
        self._lock = asyncio.Lock()
        self._next_refresh = 0.0
        self._codes: dict[str, int] = {}

    async def async_day_codes(self) -> dict[str, int]:
        """Return known codes for today and tomorrow in Paris."""
        async with self._lock:
            today = dt_util.now(TEMPO_TIME_ZONE).date()
            tomorrow = today + timedelta(days=1)
            now = asyncio.get_running_loop().time()
            if now >= self._next_refresh:
                self._next_refresh = now + _REFRESH_SECONDS
                codes = await asyncio.gather(
                    self._async_fetch_code("today", today),
                    self._async_fetch_code("tomorrow", tomorrow),
                )
                for day, code in zip((today, tomorrow), codes, strict=True):
                    if code is not None:
                        self._codes[day.isoformat()] = code

            # Recheck the date in case the requests crossed midnight.
            today = dt_util.now(TEMPO_TIME_ZONE).date()
            valid_days = {today.isoformat(), (today + timedelta(days=1)).isoformat()}
            self._codes = {
                day: code for day, code in self._codes.items() if day in valid_days
            }
            return self._codes.copy()

    async def _async_fetch_code(self, route: str, expected_date: date) -> int | None:
        """Read one announcement; failures never become non-red confirmations."""
        try:
            async with self._session.get(
                f"{_API_URL}/{route}", timeout=_TIMEOUT, allow_redirects=False
            ) as response:
                if response.status != 200:
                    _LOGGER.debug(
                        "Tempo calendar %s returned HTTP %s", route, response.status
                    )
                    return None
                payload: Any = await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Tempo calendar %s unavailable: %s", route, err)
            return None

        if (
            not isinstance(payload, dict)
            or payload.get("status") != "ok"
            or payload.get("date") != expected_date.isoformat()
        ):
            return None
        code = payload.get("code")
        return code if type(code) is int and code in (1, 2, 3) else None
