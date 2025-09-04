"""Coordinator for Octopus Energy French integration."""
from __future__ import annotations

from datetime import timedelta
import json
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL
)
from .lib.octopus_french import OctopusFrenchClient
from .utils.logger import LOGGER


class OctopusDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Octopus Energy French data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OctopusFrenchClient,
        account_number: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,  # Paramètre explicite
    ) -> None:
        """Initialize."""
        self.client = client
        self.account_number = account_number

        # Utiliser l'intervalle passé en paramètre
        update_interval = timedelta(hours=scan_interval)

        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{account_number}",  # Nom unique par compte
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Octopus Energy French API."""
        try:
            ledgers = await self.client.get_data_ledgers(self.account_number)
            self.ledgers = ledgers
            return ledgers or {}
        
        
        except Exception as err:
            LOGGER.error("Error fetching Octopus Energy data for account %s: %s", 
                        self.account_number, err)
            # Retourner un dictionnaire vide au lieu de None
            return {}
