"""Data update coordinator for Octopus French Energy."""

from __future__ import annotations

from contextlib import suppress
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
        scan_interval: int = DEFAULT_SCAN_INTERVAL,  # ✅ Ajout du paramètre
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Octopus French Energy",
            update_interval=timedelta(
                minutes=scan_interval
            ),  # ✅ Utilisation du paramètre
        )
        self.api_client = api_client
        self.account_number = account_number

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            account_data = await self.api_client.get_account_data(self.account_number)

            if not account_data:
                raise UpdateFailed("No account data received")

            supply_points = account_data.get("supply_points", {})

            await self._fetch_gas_readings(account_data, supply_points)
            await self._fetch_electricity_readings(account_data, supply_points)

            tarifs = await self.api_client.get_tarifs(self.account_number)
            account_data["tarifs"] = tarifs

            await self._fetch_payment_requests(account_data)

            return account_data

        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_gas_readings(
        self, account_data: dict[str, Any], supply_points: dict[str, Any]
    ) -> None:
        """Fetch gas readings and add to account data."""
        account_data["gas_readings"] = []

        gas_points = supply_points.get("gas", [])
        if not gas_points:
            return

        pce_ref = gas_points[0].get("id")
        if not pce_ref:
            return

        with suppress(Exception):
            gas_readings = await self.api_client.get_gas_readings(
                self.account_number, pce_ref
            )
            account_data["gas_readings"] = gas_readings
            account_data["pce_ref"] = pce_ref

    async def _fetch_electricity_readings(
        self, account_data: dict[str, Any], supply_points: dict[str, Any]
    ) -> None:
        """Fetch electricity readings and add to account data."""
        account_data["electricity_readings"] = []

        electricity_points = supply_points.get("electricity", [])
        if not electricity_points:
            return

        prm_id = electricity_points[0].get("id")
        if not prm_id:
            return

        with suppress(Exception):
            electricity_readings = await self.api_client.get_electricity_readings(
                self.account_number, prm_id
            )
            account_data["electricity_readings"] = electricity_readings
            account_data["prm_id"] = prm_id

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
