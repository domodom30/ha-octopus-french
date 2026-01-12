"""Data update coordinator for Octopus French Energy."""

from __future__ import annotations

from contextlib import suppress
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL

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
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Octopus French Energy",
            update_interval=timedelta(minutes=scan_interval),
        )
        self.api_client = api_client
        self.account_number = account_number

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self._fetch_all_data()
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_all_data(self) -> dict[str, Any]:
        """Fetch all data from API."""
        account_data = await self.api_client.get_account_data(self.account_number)

        # Validation des données essentielles
        account_id = account_data.get("account_id")
        account_number = account_data.get("account_number")

        if not account_id:
            raise UpdateFailed("Missing account_id in API response")
        if not account_number:
            raise UpdateFailed("Missing account_number in API response")

        # Filtrer les compteurs résiliés
        account_data["supply_points"]["electricity"] = [
            sp
            for sp in account_data["supply_points"]["electricity"]
            if not (
                sp.get("distributorStatus") == "RESIL"
                and sp.get("poweredStatus") == "LIMI"
            )
        ]

        # Récupérer les IDs des compteurs
        electricity_supply_points = account_data.get("supply_points", {}).get(
            "electricity", []
        )
        electricity_meter_id = (
            electricity_supply_points[0]["id"] if electricity_supply_points else None
        )
        gas_supply_points = account_data.get("supply_points", {}).get("gas", [])
        gas_meter_id = gas_supply_points[0]["id"] if gas_supply_points else None

        # Calculer les dates avec le timezone de Home Assistant
        now = dt_util.now()
        today_midnight = dt_util.start_of_local_day(now)
        first_of_month = today_midnight.replace(day=1)
        electricity_start = first_of_month.isoformat()
        date_end = (today_midnight + timedelta(days=1)).isoformat()
        gas_start = (today_midnight - timedelta(days=365)).isoformat()

        # Récupération des données électricité (journalières agrégées)
        electricity_readings = []
        elec_index = None

        if electricity_meter_id:
            electricity_readings = await self.api_client.get_energy_readings(
                account_id,
                electricity_start,
                date_end,
                electricity_meter_id,
                utility_type="electricity",
                reading_frequency="DAY_INTERVAL",
                reading_quality="ACTUAL",
                first=100,
            )

            elec_index = await self.api_client.get_electricity_index(
                account_number, electricity_meter_id
            )

        # Stocker les données électricité
        account_data["electricity"] = {
            "readings": electricity_readings,
            "index": elec_index,
        }

        # Récupération des données gaz (mensuelles)
        gas = []
        if gas_meter_id:
            gas = await self.api_client.get_energy_readings(
                account_id,
                gas_start,
                date_end,
                gas_meter_id,
                utility_type="gas",
                reading_frequency="MONTH_INTERVAL",
                first=100,
            )

        account_data["gas"] = gas

        # Récupérer les demandes de paiement
        await self._fetch_payment_requests(account_data)

        _LOGGER.debug("Account data updated successfully: %s", account_data)
        return account_data

    async def _fetch_payment_requests(self, account_data: dict[str, Any]) -> None:
        """Fetch payment requests for all ledgers."""
        ledgers = account_data.get("ledgers", {})
        payment_requests = {}

        for ledger_type, ledger_info in ledgers.items():
            ledger_number = ledger_info.get("number")
            if ledger_number:
                with suppress(Exception):
                    payment_request = await self.api_client.get_payment_requests(
                        ledger_number
                    )
                    if payment_request:
                        payment_requests[ledger_type] = payment_request

        account_data["payment_requests"] = payment_requests
