"""API client for OctopusFrench Energy."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import logging
from typing import Any

import aiohttp
import jwt

from .const import LEDGER_TYPE_ELECTRICITY, LEDGER_TYPE_GAS

_LOGGER = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.oefr-kraken.energy/v1/graphql/"

# Token constants
TOKEN_EXPIRY_BUFFER = 60  # Consider token expired 60s before actual expiry
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # seconds

MUTATION_LOGIN = """
mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
    obtainKrakenToken(input: $input) {
        token
    }
}
"""

QUERY_GET_ACCOUNTS = """
{
  viewer {
    accounts {
      number
      ledgers {
        balance
        ledgerType
        name
        number
        id
      }
    }
  }
}
"""

QUERY_GET_ACCOUNT_DATA = """
query getAccountData($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    properties {
      address
      supplyPoints(first: 10) {
        edges {
          node {
            meterPoint {
              ... on ElectricityMeterPoint {
                id
                distributorStatus
                meterKind
                subscribedMaxPower
                isTeleoperable
                offPeakLabel
                poweredStatus
                providerCalendarId
                providerCalendarName
                address {
                  fullAddress
                }
              }
              ... on GasMeterPoint {
                id
                gasNature
                annualConsumption
                isSmartMeter
                poweredStatus
                priceLevel
                tariffOption
                address {
                  fullAddress
                }
              }
            }
          }
        }
      }
    }
    creditStorage {
      ledger {
        currentBalance
        ledgerType
        name
        number
      }
    }
  }
}
"""

QUERY_GET_BILLS = """
    query paiement($ledgerNumber: String!) {
      paymentRequests(ledgerNumber: $ledgerNumber) {
        paymentRequest(first: 1) {
          edges {
            node {
              paymentStatus
              totalAmount
              customerAmount
              expectedPaymentDate
            }
          }
        }
      }
    }
"""

QUERY_GET_TARIFS = """
query GetTarifs($accountNumber: String!) {
  agreements(accountNumber: $accountNumber, first: 10) {
    edges {
      node {
        id
        isActive
        chargingLedger {
          ledgerType
        }
        ... on ElectricitySpecificAgreementType {
          product {
            consumptionRates(first: 3) {
              edges {
                node {
                  ... on ElectricityConsumptionRateType {
                    pricePerUnit
                    pricePerUnitWithTaxes
                    providerCalendar
                    currency
                  }
                }
              }
            }
          }
        }
        ... on GasSpecificAgreementType {
          product {
            consumptionRates(first: 1) {
              edges {
                node {
                  ... on GasConsumptionRateType {
                    priceLevel
                    pricePerUnit
                    currency
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

QUERY_GET_METER_ELECTRICITY = """
query ElectricityMeterReadings($accountNumber: String!, $prmId: String!) {
  electricityReading(
    accountNumber: $accountNumber
    prmId: $prmId
    first: 10
    calendarType: PROVIDER
    statusProcessed: OK
  ) {
    edges {
      node {
        indexStartValue
        indexEndValue
        calendarType
        calendarTempClass
        consumption
        consumptionReliability
        statusProcessed
        periodEndAt
        periodStartAt
      }
    }
  }
}
"""

QUERY_GET_METER_GAS = """
query GasMeterReadings($accountNumber: String!, $pceRef: String!) {
  gasReading(accountNumber: $accountNumber, first: 10, pceRef: $pceRef) {
    edges {
      node {
        consumption
        indexEndValue
        indexStartValue
        periodEndAt
        periodStartAt
        readingDate
        readingType
        statusProcessed
      }
    }
  }
}
"""


class TokenManager:
    """Robust token management with automatic refresh."""

    def __init__(self) -> None:
        """Initialize the token manager."""
        self._token: str | None = None
        self._expiry: float | None = None
        self._refresh_lock = asyncio.Lock()

    @property
    def token(self) -> str | None:
        """Get the current token."""
        return self._token

    @property
    def is_valid(self) -> bool:
        """Check if token is valid with buffer."""
        if not self._token or not self._expiry:
            return False

        now = datetime.now(UTC).timestamp()
        # Token is valid if it has at least TOKEN_EXPIRY_BUFFER seconds left
        return now < (self._expiry - TOKEN_EXPIRY_BUFFER)

    @property
    def expires_in(self) -> float:
        """Get seconds until token expiry."""
        if not self._expiry:
            return 0
        return max(0, self._expiry - datetime.now(UTC).timestamp())

    def set_token(self, token: str) -> None:
        """Set a new token and decode its expiry."""
        self._token = token

        # Try to decode expiry from JWT
        with suppress(Exception):
            decoded = jwt.decode(token, options={"verify_signature": False})
            if exp := decoded.get("exp"):
                self._expiry = float(exp)
                expires_in = int(self.expires_in)
                _LOGGER.info("Token set, valid for %d seconds", expires_in)
                return

        # Fallback: assume 1 hour validity
        self._expiry = datetime.now(UTC).timestamp() + 3600
        _LOGGER.warning("Could not decode token expiry, assuming 1 hour validity")

    def clear(self) -> None:
        """Clear token and expiry."""
        self._token = None
        self._expiry = None
        _LOGGER.debug("Token cleared")


class OctopusFrenchApiClient:
    """OctopusFrench API Client with robust authentication."""

    def __init__(self, email: str, password: str) -> None:
        """Initialize the API client."""
        self.email = email
        self.password = password
        self.token_manager = TokenManager()
        self._auth_lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _async_execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Execute GraphQL query with retry logic."""
        await self._ensure_session()

        payload = {"query": query, "variables": variables or {}}
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                async with self._session.post(
                    GRAPHQL_ENDPOINT,
                    json=payload,
                    headers=request_headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()

                    _LOGGER.warning(
                        "API returned status %d (attempt %d/%d)",
                        response.status,
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                    )

                    # On non-200, retry after delay
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.warning(
                    "Network error: %s (attempt %d/%d)",
                    err,
                    attempt + 1,
                    MAX_RETRY_ATTEMPTS,
                )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
        _LOGGER.error("All retry attempts failed")
        return None

    async def authenticate(self) -> bool:
        """Authenticate with the API (thread-safe)."""
        async with self._auth_lock:
            # Check if another task already refreshed the token
            if self.token_manager.is_valid:
                return True
            _LOGGER.info("Authenticating with Octopus Energy API...")
            variables = {
                "input": {
                    "email": self.email,
                    "password": self.password,
                }
            }

            result = await self._async_execute(
                query=MUTATION_LOGIN,
                variables=variables,
            )

            if not result:
                return False

            token = result.get("data", {}).get("obtainKrakenToken", {}).get("token")

            if not token:
                if "errors" in result:
                    errors = [e.get("message", "Unknown") for e in result["errors"]]
                    _LOGGER.error(
                        "Authentication failed: %s",
                        ", ".join(errors),
                    )
                else:
                    _LOGGER.error("Authentication failed: Invalid credentials")
                return False

            self.token_manager.set_token(token)
            _LOGGER.info("Authentication successful")
            return True

    async def _execute_with_auth(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Execute GraphQL query with automatic authentication."""
        # Ensure we have a valid token
        if not self.token_manager.is_valid:
            if not await self.authenticate():
                raise RuntimeError("Authentication failed")

        # Execute with current token
        headers = {"Authorization": f"JWT {self.token_manager.token}"}
        result = await self._async_execute(
            query=query,
            variables=variables,
            headers=headers,
        )

        if not result:
            raise RuntimeError("API returned empty response")

        # Check for auth errors in response
        if "errors" in result and retry_count < 1:
            error_messages = [
                error.get("message", "").lower() for error in result["errors"]
            ]

            # Check if it's an auth error
            auth_keywords = {"authentication", "unauthorized", "token", "expired"}
            is_auth_error = any(
                keyword in msg for msg in error_messages for keyword in auth_keywords
            )

            if is_auth_error:
                _LOGGER.warning("Token expired during request, re-authenticating...")
                # Token expired mid-request, clear and retry once
                self.token_manager.clear()
                return await self._execute_with_auth(
                    query=query,
                    variables=variables,
                    retry_count=retry_count + 1,
                )

        return result

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            _LOGGER.debug("API client session closed")

    async def get_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts."""
        result = await self._execute_with_auth(query=QUERY_GET_ACCOUNTS)
        return result.get("data", {}).get("viewer", {}).get("accounts", [])

    async def get_account_data(self, account_number: str) -> dict[str, Any]:
        """Get detailed account data including ledgers."""
        variables = {"accountNumber": account_number}
        result = await self._execute_with_auth(
            query=QUERY_GET_ACCOUNT_DATA, variables=variables
        )

        account = result.get("data", {}).get("account")
        if not account:
            return {}

        # Parse ledgers
        ledgers = await self._parse_ledgers(account, account_number)

        # Parse address
        address = self._parse_address(account.get("properties"))

        # Parse supply points
        supply_points = self._parse_supply_points(account.get("properties"))

        return {
            "account_id": account.get("id", ""),
            "account_number": account.get("number", ""),
            "address": address,
            "ledgers": ledgers,
            "supply_points": supply_points,
        }

    async def _parse_ledgers(
        self, account: dict[str, Any], account_number: str
    ) -> dict[str, dict[str, Any]]:
        """Parse ledgers from account data."""
        ledgers = {}

        # Parse credit storage ledgers
        ledger_data = account.get("creditStorage", {}).get("ledger", [])
        if not isinstance(ledger_data, list):
            ledger_data = [ledger_data]

        for ledger in ledger_data:
            if ledger and (ledger_type := ledger.get("ledgerType")):
                ledgers[ledger_type] = {
                    "balance": ledger.get("currentBalance", 0),
                    "name": ledger.get("name", ""),
                    "number": ledger.get("number", ""),
                }

        # Get additional ledgers from accounts query
        with suppress(Exception):
            all_accounts = await self.get_accounts()
            for acc in all_accounts:
                if acc["number"] == account_number:
                    for ledger in acc.get("ledgers", []):
                        if (
                            ledger_type := ledger.get("ledgerType")
                        ) and ledger_type not in ledgers:
                            ledgers[ledger_type] = {
                                "balance": ledger.get("balance", 0),
                                "name": ledger_type.lower(),
                                "number": ledger.get("number", ""),
                            }

        return ledgers

    def _parse_address(self, properties: Any) -> str:
        """Parse address from properties."""
        if not properties:
            return ""

        if isinstance(properties, str):
            return properties

        if isinstance(properties, dict):
            return properties.get("address", "")

        if isinstance(properties, list) and properties:
            first_prop = properties[0]
            if isinstance(first_prop, dict):
                return first_prop.get("address", "")

        return ""

    def _parse_supply_points(self, properties: Any) -> dict[str, list[dict[str, Any]]]:
        """Parse supply points from properties."""
        supply_points = {"electricity": [], "gas": []}

        if not isinstance(properties, list):
            return supply_points

        for prop in properties:
            if not isinstance(prop, dict):
                continue

            edges = prop.get("supplyPoints", {}).get("edges", [])
            for edge in edges:
                meter_point = edge.get("node", {}).get("meterPoint", {})

                # Check if electricity meter
                if "meterKind" in meter_point or "distributorStatus" in meter_point:
                    supply_points["electricity"].append(meter_point)
                # Check if gas meter
                elif "gasNature" in meter_point or "annualConsumption" in meter_point:
                    supply_points["gas"].append(meter_point)

        return supply_points

    async def get_gas_readings(
        self, account_number: str, pce_ref: str
    ) -> list[dict[str, Any]]:
        """Get gas meter readings."""
        variables = {"accountNumber": account_number, "pceRef": pce_ref}
        result = await self._execute_with_auth(
            query=QUERY_GET_METER_GAS, variables=variables
        )

        edges = result.get("data", {}).get("gasReading", {}).get("edges", [])
        return [edge["node"] for edge in edges]

    async def get_electricity_readings(
        self, account_number: str, prm_id: str
    ) -> list[dict[str, Any]]:
        """Get electricity meter readings."""
        variables = {"accountNumber": account_number, "prmId": prm_id}
        result = await self._execute_with_auth(
            query=QUERY_GET_METER_ELECTRICITY, variables=variables
        )

        edges = result.get("data", {}).get("electricityReading", {}).get("edges", [])
        return [edge["node"] for edge in edges]

    async def get_tarifs(self, account_number: str) -> dict[str, Any]:
        """Get tarifs for account."""
        variables = {"accountNumber": account_number}
        result = await self._execute_with_auth(
            query=QUERY_GET_TARIFS, variables=variables
        )

        agreements = result.get("data", {}).get("agreements", {}).get("edges", [])
        tarifs = {"electricity": {}, "gas": {}}

        for edge in agreements:
            agreement = edge.get("node", {})

            if not agreement.get("isActive"):
                continue

            ledger_type = agreement.get("chargingLedger", {}).get("ledgerType")

            # Parse electricity tarifs
            if ledger_type == LEDGER_TYPE_ELECTRICITY:
                rates = (
                    agreement.get("product", {})
                    .get("consumptionRates", {})
                    .get("edges", [])
                )

                for rate_edge in rates:
                    rate = rate_edge.get("node", {})
                    calendar = rate.get("providerCalendar")

                    if calendar == "PEAK_OFF_PEAK":
                        # HC = prix le plus bas, HP = prix le plus haut
                        price_ttc = float(rate.get("pricePerUnitWithTaxes", 0))

                        if not tarifs["electricity"].get("hc") or price_ttc < tarifs[
                            "electricity"
                        ].get("hc", 999):
                            tarifs["electricity"]["hc"] = price_ttc
                        if not tarifs["electricity"].get("hp") or price_ttc > tarifs[
                            "electricity"
                        ].get("hp", 0):
                            tarifs["electricity"]["hp"] = price_ttc

            # Parse gas tarifs (on prend le niveau 1 par défaut)
            elif ledger_type == LEDGER_TYPE_GAS:
                rates = (
                    agreement.get("product", {})
                    .get("consumptionRates", {})
                    .get("edges", [])
                )

                for rate_edge in rates:
                    rate = rate_edge.get("node", {})
                    if rate.get("priceLevel") == 1:
                        tarifs["gas"]["price"] = float(rate.get("pricePerUnit", 0))
                        break

        return tarifs

    async def get_payment_requests(self, ledger_number: str) -> dict | None:
        """Get the latest payment request for a ledger."""

        variables = {"ledgerNumber": ledger_number}
        result = await self._execute_with_auth(QUERY_GET_BILLS, variables)

        if result and "data" in result and "paymentRequests" in result["data"]:
            payment_requests = result["data"]["paymentRequests"].get(
                "paymentRequest", {}
            )
            edges = payment_requests.get("edges", [])
            if edges:
                return edges[0].get("node")

        return None
