"""Data update coordinator for Octopus French Energy."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, PREVIOUS_MONTH_OVERLAP_DAYS

from .octopus_french import OctopusAuthError, OctopusConnectionError

if TYPE_CHECKING:
    from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)


class OctopusFrenchDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

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
            name="Octopus French Energy",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
            config_entry=config_entry,
        )
        self.api_client = api_client
        self.account_number = account_number

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self._fetch_all_data()
        except OctopusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OctopusConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_all_data(self) -> dict[str, Any]:
        """Fetch all data from API."""
        account_data = await self.api_client.get_account_data(self.account_number)
        account_id = account_data.get("account_id")
        account_number = account_data.get("account_number")

        if not account_id:
            raise UpdateFailed("Missing account_id in API response")
        if not account_number:
            raise UpdateFailed("Missing account_number in API response")

        account_data["supply_points"]["electricity"] = [
            sp
            for sp in account_data["supply_points"]["electricity"]
            if sp.get("distributorStatus") != "RESIL"
        ]

        electricity_supply_points = account_data.get("supply_points", {}).get(
            "electricity", []
        )
        electricity_meter_id = (
            electricity_supply_points[0].get("prm") if electricity_supply_points else None
        )
        gas_supply_points = account_data.get("supply_points", {}).get("gas", [])
        gas_meter_id = gas_supply_points[0].get("prm") if gas_supply_points else None

        now = dt_util.now()
        today_midnight = dt_util.start_of_local_day(now)
        first_of_month = today_midnight.replace(day=1)
        electricity_start = (first_of_month - timedelta(days=PREVIOUS_MONTH_OVERLAP_DAYS)).isoformat()
        date_end = now.isoformat()
        gas_start = (today_midnight - timedelta(days=365)).isoformat()

        async def fetch_electricity() -> tuple[list, Any]:
            if not electricity_meter_id:
                return [], None

            try:
                readings = await self.api_client.get_energy_readings(
                    account_id,
                    electricity_start,
                    date_end,
                    electricity_meter_id,
                    utility_type="electricity",
                    reading_frequency="DAY_INTERVAL",
                    reading_quality="ACTUAL",
                    first=100,
                )
                index = await self.api_client.get_electricity_index(
                    account_number, electricity_meter_id
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Failed to fetch electricity data: %s", err)
                return [], None
            else:
                return readings, index

        async def fetch_gas() -> list:
            if not gas_meter_id:
                return []
            try:
                return await self.api_client.get_energy_readings(
                    account_id,
                    gas_start,
                    date_end,
                    gas_meter_id,
                    utility_type="gas",
                    reading_frequency="MONTH_INTERVAL",
                    reading_quality="ACTUAL",
                    first=100,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Failed to fetch gas data: %s", err)
                return []

        ledgers = account_data.get("ledgers", {})

        async def fetch_payments() -> dict:
            try:
                return await self.api_client.get_all_payment_requests(ledgers)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Failed to fetch payment requests: %s", err)
                return {}

        (
            (electricity_readings, elec_index),
            gas,
            payment_requests,
        ) = await asyncio.gather(fetch_electricity(), fetch_gas(), fetch_payments())

        # Expose active tariffs for the electricity supply point
        tariffs = None
        agreements = account_data.get("agreements", [])
        for agreement in agreements:
            if agreement.get("prm") == electricity_meter_id and agreement.get("is_active"):
                tariffs = agreement.get("tariffs")
                break
        if tariffs is None:
            for agreement in agreements:
                if agreement.get("is_active"):
                    tariffs = agreement.get("tariffs")
                    break

        account_data["electricity"] = {
            "readings": electricity_readings,
            "index": elec_index,
            "tariffs": tariffs,
        }
        account_data["gas"] = gas
        account_data["payment_requests"] = payment_requests

        _LOGGER.debug(
            "Account data updated successfully for account %s", account_number
        )
        return account_data
