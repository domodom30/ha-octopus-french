"""Data update coordinator for Octopus French Energy."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
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
    from .statistics_import import OctopusStatisticsImporter

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
        self.statistics_importer: OctopusStatisticsImporter | None = None

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

        supply_points = account_data.setdefault("supply_points", {})
        supply_points["electricity"] = [
            sp
            for sp in supply_points.get("electricity", [])
            if sp.get("distributorStatus") != "RESIL"
        ]

        electricity_supply_points = supply_points["electricity"]
        electricity_meter_ids = [
            sp.get("prm") for sp in electricity_supply_points if sp.get("prm")
        ]
        # Chaque compteur peut vivre sur une property (logement) distincte : on
        # route chaque PRM vers SA property, sinon les relevés du 2e compteur
        # seraient demandés sur la property du 1er (issue #56).
        property_id_by_prm = {
            sp["prm"]: sp.get("property_id") or account_id
            for sp in electricity_supply_points
            if sp.get("prm")
        }
        gas_supply_points = supply_points.get("gas", [])
        gas_meter = gas_supply_points[0] if gas_supply_points else None
        gas_meter_id = gas_meter.get("prm") if gas_meter else None
        gas_property_id = (
            (gas_meter.get("property_id") or account_id) if gas_meter else None
        )

        now = dt_util.now()
        today_midnight = dt_util.start_of_local_day(now)
        first_of_month = today_midnight.replace(day=1)
        electricity_start = (
            first_of_month - timedelta(days=PREVIOUS_MONTH_OVERLAP_DAYS)
        ).isoformat()
        date_end = now.isoformat()
        gas_start = (today_midnight - timedelta(days=365)).isoformat()

        async def fetch_electricity_for_prm(prm_id: str) -> tuple[str, list, Any]:
            try:
                readings = await self.api_client.get_energy_readings(
                    property_id_by_prm.get(prm_id, account_id),
                    electricity_start,
                    date_end,
                    prm_id,
                    utility_type="electricity",
                    reading_frequency="DAY_INTERVAL",
                    reading_quality="ACTUAL",
                    first=100,
                )
                index = await self.api_client.get_electricity_index(
                    account_number, prm_id
                )
            except OctopusConnectionError as err:
                _LOGGER.warning(
                    "Failed to fetch electricity data for PRM %s: %s", prm_id, err
                )
                return prm_id, [], None
            else:
                return prm_id, readings, index

        async def fetch_gas() -> list:
            if not gas_meter_id:
                return []
            try:
                return await self.api_client.get_energy_readings(
                    gas_property_id or account_id,
                    gas_start,
                    date_end,
                    gas_meter_id,
                    utility_type="gas",
                    reading_frequency="MONTH_INTERVAL",
                    reading_quality="ACTUAL",
                    first=100,
                )
            except OctopusConnectionError as err:
                _LOGGER.warning("Failed to fetch gas data: %s", err)
                return []

        ledgers = account_data.get("ledgers", {})

        async def fetch_payments() -> dict:
            try:
                return await self.api_client.get_all_payment_requests(ledgers)
            except OctopusConnectionError as err:
                _LOGGER.warning("Failed to fetch payment requests: %s", err)
                return {}

        electricity_results, gas, payment_requests = await asyncio.gather(
            asyncio.gather(
                *(fetch_electricity_for_prm(prm) for prm in electricity_meter_ids)
            ),
            fetch_gas(),
            fetch_payments(),
        )

        account_data["electricity_by_prm"] = {
            prm_id: {"readings": readings, "index": index}
            for prm_id, readings, index in electricity_results
        }
        account_data["gas"] = gas
        account_data["payment_requests"] = payment_requests

        _LOGGER.debug(
            "Account data updated successfully for account %s", account_number
        )
        return account_data
