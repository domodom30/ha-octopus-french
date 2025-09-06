"""Client for Octopus Energy French API with improved token management."""
from __future__ import annotations

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
    QUERY_ELECTRICITY_READINGS
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
        self._auth_retry_count = 0
        self._max_auth_retries = 2

    async def authenticate(self) -> bool:
        """Authenticate with the API and obtain a token."""
        try:
            LOGGER.debug("Attempting authentication for email: %s", self._email)
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
                    self._auth_retry_count = 0  # Reset retry counter on success
                    LOGGER.info("Authentication successful")
                    return True
                else:
                    LOGGER.warning("Authentication failed - no token in response")
                    
        except Exception as err:
            LOGGER.error("Authentication failed: %s", err)
            
        return False

    async def _ensure_token(self) -> bool:
        """Ensure we have a valid token, re-authenticate if needed."""
        if not self._token:
            LOGGER.debug("No token found, attempting authentication...")
            return await self.authenticate()
        return True

    async def _is_token_expired_response(self, data: dict) -> bool:
        """Check if the response indicates token expiration or authentication issues."""
        if not data:
            return False
            
        # Check for explicit authentication errors
        if "errors" in data:
            for error in data["errors"]:
                error_message = error.get("message", "").lower()
                if any(keyword in error_message for keyword in [
                    "not authenticated", "token", "expired", "unauthorized", "invalid"
                ]):
                    return True
        
        # Check for empty data that might indicate auth issues
        # Si on appelle get_accounts et qu'on a aucun compte, c'est suspect
        if "data" in data:
            viewer = data["data"].get("viewer")
            if viewer is not None and not viewer.get("accounts"):
                LOGGER.debug("Empty accounts data - possible token expiration")
                return True
                
            account = data["data"].get("account")
            if account is None and "account" in str(data):
                LOGGER.debug("Null account data - possible token expiration")
                return True
                
        return False

    async def _graphql_query_with_retry(self, query: str, variables: dict = None, auth_required: bool = True) -> dict | None:
        """Execute a GraphQL query with token refresh retry logic."""
        
        for attempt in range(self._max_auth_retries + 1):
            result = await self._graphql_query_single(query, variables, auth_required)
            
            if not result:
                return None
                
            # Si on détecte une expiration de token et qu'on peut encore réessayer
            if auth_required and await self._is_token_expired_response(result) and attempt < self._max_auth_retries:
                LOGGER.warning("Token appears expired (attempt %d/%d), re-authenticating...", 
                             attempt + 1, self._max_auth_retries)
                
                # Forcer une nouvelle authentification
                self._token = None
                if await self.authenticate():
                    LOGGER.info("Re-authentication successful, retrying query")
                    continue
                else:
                    LOGGER.error("Re-authentication failed")
                    return None
            
            return result
            
        return None

    async def _graphql_query_single(self, query: str, variables: dict = None, auth_required: bool = True) -> dict | None:
        """Execute a single GraphQL query without retry logic."""
        headers = {
            "Content-Type": "application/json",
        }

        if auth_required:
            if not await self._ensure_token():
                LOGGER.error("Unable to authenticate, aborting query.")
                return None
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

    async def _graphql_query(self, query: str, variables: dict = None, auth_required: bool = True) -> dict | None:
        """Execute a GraphQL query with automatic token refresh on failure."""
        return await self._graphql_query_with_retry(query, variables, auth_required)

    async def get_accounts(self) -> list[dict] | None:
        """Get all accounts for the authenticated user."""
        LOGGER.debug("Fetching accounts...")
        response = await self._graphql_query(QUERY_GET_ACCOUNTS)
        
        if response and "data" in response and response["data"].get("viewer"):
            accounts = response["data"]["viewer"]["accounts"]
            LOGGER.debug("Found %d accounts", len(accounts) if accounts else 0)
            return accounts
        
        LOGGER.warning("No accounts found in response")
        return None

    async def get_data_ledgers(
            self, account_number: str, electricity_mode: str = "max"
        ) -> list[dict[str, Any]]:
        """Get enhanced ledgers with meter points and gas readings for gas meters."""

        LOGGER.debug("Fetching ledgers for account %s", account_number)
        response = await self._graphql_query(
            QUERY_GET_LEDGERS, {"accountNumber": account_number}
        )
        
        if not response or "data" not in response:
            LOGGER.warning("No response or data from get_data_ledgers query for account %s", account_number)
            return []

        data = response["data"]
        if not data:
            LOGGER.warning("Empty data received from get_data_ledgers query for account %s", account_number)
            return []

        # Safe extraction of ledgers and supply points with null checks
        account_data = data.get("account")
        if not account_data:
            LOGGER.warning("No account data found for account %s", account_number)
            return []

        ledgers = account_data.get("ledgers", [])
        if not ledgers:
            LOGGER.warning("No ledgers found for account %s", account_number)
            return []

        # Safe extraction of supply points
        supply_points_data = data.get("supplyPoints", {})
        supply_points_edges = supply_points_data.get("edges", []) if supply_points_data else []

        # Build meter point map with comprehensive null checks
        meter_point_map = {}
        for edge in supply_points_edges:
            if not edge:
                continue
            
            node = edge.get("node")
            if not node:
                continue
            
            meter_point = node.get("meterPoint")
            if not meter_point:
                continue
                
            meter_point_id = meter_point.get("id")
            external_id = node.get("externalIdentifier")
            
            if meter_point_id and external_id:
                meter_point_map[meter_point_id] = {
                    "external_identifier": external_id
                }

        enhanced_ledgers = []
        for ledger in ledgers:
            if not ledger or not isinstance(ledger, dict):
                LOGGER.warning("Invalid ledger data found, skipping")
                continue
                
            ledger_copy = ledger.copy()
            ledger_type = ledger.get("ledgerType")
            
            if not ledger_type:
                LOGGER.warning("Ledger without ledgerType found, skipping")
                continue

            # Associate meter points with safe pattern matching
            ledger_name = ledger.get("name", "")
            meter_point_id = None
            
            if ledger_name:
                meter_point_match = re.search(r"\((\d+)\)", ledger_name)
                if meter_point_match:
                    meter_point_id = meter_point_match.group(1)
            
            # Set meter point info (can be None if not found)
            ledger_copy["meterPoint"] = meter_point_map.get(meter_point_id)

            # Fetch additional readings with proper error handling
            try:
                if ledger_type == "FRA_GAS_LEDGER" and meter_point_id:
                    readings = await self.get_data_gas(account_number, meter_point_id, limit=100)
                    if readings:
                        ledger_copy["additional_data"] = {"readings": readings}
                    else:
                        LOGGER.debug("No gas readings found for meter point %s", meter_point_id)

                elif ledger_type == "FRA_ELECTRICITY_LEDGER" and meter_point_id:
                    readings = await self.get_data_electricity(account_number, meter_point_id, limit=100)
                    if readings:
                        ledger_copy["additional_data"] = {"readings": readings}
                    else:
                        LOGGER.debug("No electricity readings found for meter point %s", meter_point_id)
                        
            except Exception as reading_err:
                LOGGER.error("Error fetching readings for %s (meter %s): %s", 
                           ledger_type, meter_point_id, reading_err)
                # Continue processing other ledgers even if one fails

            enhanced_ledgers.append(ledger_copy)

        LOGGER.debug("Successfully processed %d ledgers for account %s", 
                    len(enhanced_ledgers), account_number)
        return enhanced_ledgers

    async def get_data_electricity(self, account_number: str, prm_id: str, limit: int = 10) -> list[dict] | None:
        """Get electricity readings for a specific PRM ID."""
        if not account_number or not prm_id:
            LOGGER.warning("Missing account_number or prm_id for electricity readings")
            return None
            
        response = await self._graphql_query(
            QUERY_ELECTRICITY_READINGS,
            {
                "accountNumber": account_number,
                "prmId": prm_id,
                "first": limit
            }
        )
    
        if not response or "data" not in response:
            LOGGER.warning("No response or data from electricity readings query")
            return None
            
        electricity_data = response["data"].get("electricityReading")
        if not electricity_data:
            LOGGER.warning("No electricityReading data found")
            return None
            
        edges = electricity_data.get("edges", [])
        if not edges:
            LOGGER.debug("No electricity reading edges found")
            return None
            
        readings = []
        for edge in edges:
            if edge and isinstance(edge, dict):
                node = edge.get("node")
                if node and isinstance(node, dict):
                    readings.append(node)
                    
        return readings if readings else None
    
    async def get_data_gas(self, account_number: str, pce_ref: str, limit: int = 10) -> list[dict] | None:
        """Get gas readings for a specific PCE reference."""
        if not account_number or not pce_ref:
            LOGGER.warning("Missing account_number or pce_ref for gas readings")
            return None
            
        response = await self._graphql_query(
            QUERY_GAS_READINGS,
            {
                "accountNumber": account_number,
                "pceRef": pce_ref,
                "first": limit
            }
        )
        
        if not response or "data" not in response:
            LOGGER.warning("No response or data from gas readings query")
            return None
            
        gas_data = response["data"].get("gasReading")
        if not gas_data:
            LOGGER.warning("No gasReading data found")
            return None
            
        edges = gas_data.get("edges", [])
        if not edges:
            LOGGER.debug("No gas reading edges found")
            return None
            
        readings = []
        for edge in edges:
            if edge and isinstance(edge, dict):
                node = edge.get("node")
                if node and isinstance(node, dict):
                    readings.append(node)
                    
        return readings if readings else None