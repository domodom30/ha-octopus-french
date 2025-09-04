"""Client for Octopus Energy French API."""
from __future__ import annotations

import json
import re
from typing import Any
import aiohttp
from async_timeout import timeout

from ..const import (
    GRAPH_QL_ENDPOINT,
    QUERY_GET_ACCOUNTS,
    QUERY_GET_LEDGERS,
    MUTATION_LOGIN,
    QUERY_GAS_READINGS,
    QUERY_ELECTRICITY_READINGS,
    SUPPORTED_LEDGER_TYPES
)

from ..utils.logger import LOGGER

class OctopusFrenchClient:
    """Client for Octopus Energy French API."""

    def __init__(self, email: str, password: str, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._email = email
        self._password = password
        self._session = session
        self._token = None

    async def authenticate(self) -> bool:
        """Authenticate with the API and obtain a token."""
        try:
            async with timeout(30):
                response = await self._graphql_query(
                    MUTATION_LOGIN,
                    {
                        "input": {
                            "email": self._email,
                            "password": self._password
                        }
                    },
                    auth_required=False
                )
                
                if response and "data" in response and response["data"].get("obtainKrakenToken"):
                    self._token = response["data"]["obtainKrakenToken"]["token"]
                    return True
                    
        except Exception as err:
            LOGGER.error("Authentication failed: %s", err)
            
        return False

    async def _graphql_query(self, query: str, variables: dict = None, auth_required: bool = True) -> dict | None:
        """Execute a GraphQL query."""
        headers = {
            "Content-Type": "application/json",
        }
        
        if auth_required and self._token:
            headers["Authorization"] = f"JWT {self._token}"
        
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        try:
            async with timeout(30):
                async with self._session.post(
                    GRAPH_QL_ENDPOINT,
                    json=payload,
                    headers=headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
                    
        except aiohttp.ClientError as err:
            LOGGER.error("GraphQL query failed: %s", err)
            return None
        except Exception as err:
            LOGGER.error("Unexpected error: %s", err)
            return None

    async def get_accounts(self) -> list[dict] | None:
        """Get all accounts for the authenticated user."""
        response = await self._graphql_query(QUERY_GET_ACCOUNTS)
        
        if response and "data" in response and response["data"].get("viewer"):
            return response["data"]["viewer"]["accounts"]
        return None


    async def get_data_ledgers(
            self, account_number: str, electricity_mode: str = "max"
        ) -> list[dict[str, Any]]:
        """Get enhanced ledgers with meter points and gas readings for gas meters."""

        response = await self._graphql_query(
            QUERY_GET_LEDGERS, {"accountNumber": account_number}
        )
        if not response or "data" not in response:
            return []

        data = response["data"]
        ledgers = data.get("account", {}).get("ledgers", [])
        supply_points = data.get("supplyPoints", {}).get("edges", [])

        meter_point_map = {
            node.get("meterPoint", {}).get("id"): {"external_identifier": node.get("externalIdentifier")}
            for edge in supply_points
            if (node := edge.get("node"))
            if node.get("meterPoint", {}).get("id")
        }

        enhanced_ledgers = []
        for ledger in ledgers:
            if not ledger:
                continue
                
            ledger_copy = ledger.copy()
            ledger_type = ledger.get("ledgerType")

            # Associer les meter points
            ledger_name = ledger.get("name", "")
            meter_point_match = re.search(r"\((\d+)\)", ledger_name)
            meter_point_id = meter_point_match.group(1) if meter_point_match else None
            ledger_copy["meterPoint"] = meter_point_map.get(meter_point_id)

            # Récupérer et ajouter les lectures de gaz si c'est un compteur gaz
            if ledger_type == "FRA_GAS_LEDGER" and meter_point_id:
                readings = await self.get_data_gas(account_number, meter_point_id, limit=100)
                # Ajouter les lectures au ledger
                ledger_copy["additional_data"] = { "readings": readings }

            # Récupérer et ajouter les lectures de gaz si c'est un compteur gaz
            if ledger_type == "FRA_ELECTRICITY_LEDGER" and meter_point_id:
                readings = await self.get_data_electricity(account_number, meter_point_id, limit=100)
                # Ajouter les lectures au ledger
                ledger_copy["additional_data"] = { "readings": readings }

            enhanced_ledgers.append(ledger_copy)
            # LOGGER.debug(json.dumps(enhanced_ledgers, indent=2, ensure_ascii=False))
        return enhanced_ledgers

    async def get_data_electricity(self, account_number: str, prm_id: str, limit: int = 10) -> list[dict] | None:
        """Get electricity readings for a specific PRM ID."""
        response = await self._graphql_query(
            QUERY_ELECTRICITY_READINGS,
            {
                "accountNumber": account_number,
                "prmId": prm_id,
                "first": limit
            }
        )
    
        if response and "data" in response and response["data"].get("electricityReading"):
            readings = []
            for edge in response["data"]["electricityReading"]["edges"]:
                if edge.get("node"):
                    readings.append(edge["node"])
            return readings
        return None
    
    async def get_data_gas(self, account_number: str, pce_ref: str, limit: int = 10) -> list[dict] | None:
        """Get gas readings for a specific PCE reference."""
        response = await self._graphql_query(
            QUERY_GAS_READINGS,
            {
                "accountNumber": account_number,
                "pceRef": pce_ref,
                "first": limit
            }
        )
        
        if response and "data" in response and response["data"].get("gasReading"):
            readings = []
            for edge in response["data"]["gasReading"]["edges"]:
                if edge.get("node"):
                    readings.append(edge["node"])
            return readings
        return None