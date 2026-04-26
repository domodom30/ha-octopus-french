"""Data update coordinator for Octopus French Energy."""

from __future__ import annotations

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
        # Récupération des données de base du compte
        account_data = await self.api_client.get_account_data(self.account_number)
        
        # Vérification de sécurité contre le crash NoneType
        if not account_data:
            _LOGGER.error("L'API Octopus n'a renvoyé aucune donnée pour le compte %s", self.account_number)
            raise UpdateFailed("La réponse de l'API est vide ou invalide (NoneType)")

        account_id = account_data.get("account_id")
        account_number_val = account_data.get("account_number")

        if not account_id or not account_number_val:
            raise UpdateFailed("Identifiant de compte ou numéro de compte manquant")

        # Accès sécurisé aux points de livraison
        supply_points = account_data.get("supply_points", {})
        electricity_supply_points = supply_points.get("electricity", [])
        gas_supply_points = supply_points.get("gas", [])

        # Filtrage des points d'électricité actifs
        filtered_electricity = [
            sp for sp in electricity_supply_points
            if not (sp.get("distributorStatus") == "RESIL" and sp.get("poweredStatus") == "LIMI")
        ]

        if "supply_points" not in account_data:
            account_data["supply_points"] = {}
        account_data["supply_points"]["electricity"] = filtered_electricity

        electricity_meter_id = filtered_electricity[0].get("id") if filtered_electricity else None
        gas_meter_id = gas_supply_points[0].get("id") if gas_supply_points else None

        # Périodes de relevés
        now = dt_util.now()
        today_midnight = dt_util.start_of_local_day(now)
        electricity_start = (today_midnight.replace(day=1)).isoformat()
        date_end = (today_midnight + timedelta(days=1)).isoformat()
        gas_start = (today_midnight - timedelta(days=365)).isoformat()

        # Électricité : Relevés et Index
        electricity_readings = []
        elec_index = None
        if electricity_meter_id:
            try:
                electricity_readings = await self.api_client.get_energy_readings(
                    account_id, electricity_start, date_end, electricity_meter_id,
                    utility_type="electricity", reading_frequency="DAY_INTERVAL",
                    reading_quality="ACTUAL", first=100
                )
                elec_index = await self.api_client.get_electricity_index(self.account_number, electricity_meter_id)
            except Exception as err:
                _LOGGER.warning("Erreur relevés électriques : %s", err)

        # Extraction dynamique du tarif depuis les agreements
        tariffs = None
        current_agreements = account_data.get("agreements", [])
        if current_agreements:
            for agreement in current_agreements:
                if agreement.get("supply_point_id") == electricity_meter_id or agreement.get("is_active"):
                    tariffs = agreement.get("tariffs")
                    break

        account_data["electricity"] = {
            "readings": electricity_readings or [],
            "index": elec_index,
            "tariffs": tariffs, # Exposé pour les sensors de prix
        }

        # Gaz : Relevés
        gas_readings = []
        if gas_meter_id:
            try:
                gas_readings = await self.api_client.get_energy_readings(
                    account_id, gas_start, date_end, gas_meter_id,
                    utility_type="gas", reading_frequency="MONTH_INTERVAL", first=100
                )
            except Exception as err:
                _LOGGER.warning("Erreur relevés gaz : %s", err)
        account_data["gas"] = gas_readings or []

        # Facturation
        try:
            account_data["payment_requests"] = await self.api_client.get_all_payment_requests(self.account_number)
        except Exception as err:
            _LOGGER.warning("Erreur factures : %s", err)
            account_data["payment_requests"] = []

        return account_data
