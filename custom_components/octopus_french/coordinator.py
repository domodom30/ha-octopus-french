"""Coordinator for Octopus Energy French integration."""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .lib.octopus_french import OctopusFrenchClient
from .utils.logger import LOGGER


class OctopusDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Octopus Energy French data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OctopusFrenchClient,
        account_number: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize."""
        self.client = client
        self.account_number = account_number
        self.ledgers = []  # Initialiser avec une liste vide

        update_interval = timedelta(hours=scan_interval)

        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{account_number}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Octopus Energy French API."""
        try:
            LOGGER.debug("Fetching data for account: %s", self.account_number)

            ledgers = await self.client.get_data_ledgers(self.account_number)

            # Vérifications de sécurité
            if ledgers is None:
                LOGGER.warning(
                    "Client returned None for account %s", self.account_number
                )
                return {"ledgers": []}

            if not isinstance(ledgers, list):
                LOGGER.warning("Expected list but got %s: %s", type(ledgers), ledgers)
                return {"ledgers": []}

            LOGGER.debug("Successfully fetched %d ledgers", len(ledgers))
            self.ledgers = ledgers

            # Retourner un dictionnaire avec la clé "ledgers"
            return {"ledgers": ledgers}

        except Exception as err:
            LOGGER.error(
                "Error fetching Octopus Energy data for account %s: %s",
                self.account_number,
                err,
                exc_info=True,
            )
            # Retourner un dictionnaire avec liste vide au lieu de None
            return {"ledgers": []}
