"""API client for OctopusFrench Energy."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import logging
import re
from typing import Any

import aiohttp
import jwt

_LOGGER = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.oefr-kraken.energy/v1/graphql/"

TOKEN_EXPIRY_BUFFER = 60
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1

MUTATION_LOGIN = """
mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
    obtainKrakenToken(input: $input) {
        token
    }
}
"""

FRAGMENT_INTERVAL_MEASUREMENT = """
fragment IntervalMeasurement on IntervalMeasurementType {
  __typename
  value
  startAt
  metaData {
    statistics {
      costInclTax {
        estimatedAmount
        costCurrency
      }
      label
      value
    }
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
    ledgers {
      balance
      ledgerType
      name
      number
      id
    }
    properties {
      id
      address
      supplyPoints(first: 5) {
        edges {
          node {
            id
            externalIdentifier
            marketName
            meterPoint {
              ... on ElectricityMeterPoint {
                id
                distributorStatus
                meterKind
                subscribedMaxPower
                isTeleoperable
                offPeakLabel
                poweredStatus
                providerCalendar {
                  id
                  name
                }
              }
              ... on GasMeterPoint {
                id
                gasNature
                annualConsumption
                isSmartMeter
                poweredStatus
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
    agreements(
      activeAt: "2026-01-22T00:00:00Z"
      first: 10
    ) {
      edges {
        node {
          id
          validFrom
          validTo
          isActive
          supplyContractNumber
          supplyPoint {
            id
            externalIdentifier
          }
          product {
            code
            fullName
            displayName
          }
          energySupplyRate {
            standingRate {
              currency
              pricePerUnit
              unitType
              pricePerUnitWithTaxes
            }
            consumptionRates(first: 10) {
              edges {
                node {
                  currency
                  pricePerUnit
                  unitType
                  pricePerUnitWithTaxes
                }
              }
            }
          }
          billingFrequency
          nextPaymentForecast {
            amount
            date
          }
        }
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

QUERY_GET_INDEX_ELECTRICITY = """
query getElectricityIndex($accountNumber: String!, $prmId: String!) {
  electricityReading(
    accountNumber: $accountNumber
    prmId: $prmId
    first: 2
    calendarType: PROVIDER
  ) {
    edges {
      node {
        consumption
        periodStartAt
        periodEndAt
        indexStartValue
        indexEndValue
        statusProcessed
        calendarType
        calendarTempClass
        consumptionReliability
        indexReliability
      }
    }
  }
}
"""

QUERY_GET_METER_ELECTRICITY = """
query GetPropertyMeasurements($propertyId: ID!, $startAt: DateTime!, $endAt: DateTime!, $utilityFilters: [UtilityFiltersInput]!, $first: Int) {
  property(id: $propertyId) {
    measurements(
      startAt: $startAt
      endAt: $endAt
      first: $first
      utilityFilters: $utilityFilters
    ) {
      edges {
        node {
          ...IntervalMeasurement
        }
      }
    }
  }
}
"""

QUERY_GET_METER_GAS = """
query GetPropertyMeasurements($propertyId: ID!, $startAt: DateTime!, $endAt: DateTime!, $utilityFilters: [UtilityFiltersInput]!, $first: Int) {
  property(id: $propertyId) {
    measurements(
      startAt: $startAt
      endAt: $endAt
      first: $first
      utilityFilters: $utilityFilters
    ) {
      edges {
        node {
          ...IntervalMeasurement
        }
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

        with suppress(Exception):
            decoded = jwt.decode(token, options={"verify_signature": False})
            if exp := decoded.get("exp"):
                self._expiry = float(exp)
                return
        self._expiry = datetime.now(UTC).timestamp() + 3600

    def clear(self) -> None:
        """Clear token and expiry."""
        self._token = None
        self._expiry = None


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

        if not self._session:
            _LOGGER.error("Session not initialized")
            return None

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
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            except (aiohttp.ClientError, TimeoutError):
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
        return None

    async def authenticate(self) -> bool:
        """Authenticate with the API (thread-safe)."""
        async with self._auth_lock:
            if self.token_manager.is_valid:
                return True

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
                error_messages = (
                    [e.get("message", "Unknown") for e in result["errors"]]
                    if "errors" in result
                    else ["Invalid credentials"]
                )
                _LOGGER.error("Authentication failed: %s", ", ".join(error_messages))
                return False

            self.token_manager.set_token(token)
            return True

    async def _execute_with_auth(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """Execute GraphQL query with automatic authentication."""

        if not self.token_manager.is_valid:
            if not await self.authenticate():
                raise RuntimeError("Authentication failed")

        headers = {"Authorization": f"JWT {self.token_manager.token}"}
        result = await self._async_execute(
            query=query,
            variables=variables,
            headers=headers,
        )

        if not result:
            raise RuntimeError("API returned empty response")

        if "errors" in result and retry_count < 1:
            error_messages = [
                error.get("message", "").lower() for error in result["errors"]
            ]

            auth_keywords = {"authentication", "unauthorized", "token", "expired"}
            is_auth_error = any(
                keyword in msg for msg in error_messages for keyword in auth_keywords
            )

            if is_auth_error:
                _LOGGER.warning("Token expired during request, re-authenticating...")

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
        """Get detailed account data including ledgers and tariffs in a single query."""
        variables = {"accountNumber": account_number}
        result = await self._execute_with_auth(
            query=QUERY_GET_ACCOUNT_DATA, variables=variables
        )

        account = result.get("data", {}).get("account")
        if not account:
            return {}

        properties = account.get("properties", [])
        account_id = properties[0].get("id") if properties else None

        ledgers = self._extract_ledgers(account)

        supply_points = self._extract_supply_points(properties)

        agreements = self._extract_agreements(account)

        return {
            "account_id": account_id,
            "account_number": account.get("number", ""),
            "ledgers": ledgers,
            "supply_points": supply_points,
            "agreements": agreements,
        }

    def _extract_ledgers(self, account: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract ledgers from account data, filtering out terminated meters."""
        ledgers = {}
        active_prms = set()
        properties = account.get("properties", [])

        for prop in properties:
            if not isinstance(prop, dict):
                continue

            edges = prop.get("supplyPoints", {}).get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                meter_point = node.get("meterPoint", {})

                if (
                    meter_point.get("distributorStatus") == "RESIL"
                    and meter_point.get("poweredStatus") == "LIMI"
                ):
                    continue

                prm = node.get("externalIdentifier")
                if prm:
                    active_prms.add(prm)

        ledger_list = account.get("ledgers", [])
        if ledger_list:
            for ledger in ledger_list:
                if not ledger:
                    continue

                ledger_type = ledger.get("ledgerType")
                ledger_name = ledger.get("name", "")

                if not ledger_type:
                    continue

                if ledger_type in ["FRA_ELECTRICITY_LEDGER", "FRA_GAS_LEDGER"]:
                    match = re.search(r"\((\d+)\)", ledger_name)
                    if match:
                        ledger_prm = match.group(1)

                        if ledger_prm not in active_prms:
                            _LOGGER.debug(
                                "Skipping ledger %s for terminated meter %s",
                                ledger_type,
                                ledger_prm,
                            )
                            continue

                ledgers[ledger_type] = {
                    "balance": ledger.get("balance", 0),
                    "name": ledger.get("name", ""),
                    "number": ledger.get("number", ""),
                }

        ledger_data = account.get("creditStorage", {}).get("ledger", [])
        if not isinstance(ledger_data, list):
            ledger_data = [ledger_data]

        for ledger in ledger_data:
            if ledger and (ledger_type := ledger.get("ledgerType")):
                if ledger_type not in ledgers:
                    ledgers[ledger_type] = {
                        "balance": ledger.get("currentBalance", 0),
                        "name": ledger.get("name", ""),
                        "number": ledger.get("number", ""),
                    }

        return ledgers

    def _extract_supply_points(
        self, properties: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Extract supply points from properties."""
        supply_points = {"electricity": [], "gas": []}

        if not isinstance(properties, list):
            return supply_points

        for prop in properties:
            if not isinstance(prop, dict):
                continue

            edges = prop.get("supplyPoints", {}).get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                meter_point = node.get("meterPoint", {})

                meter_point["prm"] = node.get("externalIdentifier")
                meter_point["supply_point_id"] = node.get("id")
                meter_point["market_name"] = node.get("marketName")

                if "meterKind" in meter_point or "distributorStatus" in meter_point:
                    supply_points["electricity"].append(meter_point)

                elif "gasNature" in meter_point or "annualConsumption" in meter_point:
                    supply_points["gas"].append(meter_point)

        return supply_points

    def _extract_agreements(self, account: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract agreements with tariffs from account data."""
        agreements = []

        agreement_edges = account.get("agreements", {}).get("edges", [])

        for edge in agreement_edges:
            agreement = edge.get("node", {})

            tariffs = None
            if energy_rate := agreement.get("energySupplyRate"):
                tariffs = self._extract_tariffs(energy_rate)

            agreement_data = {
                "id": agreement.get("id"),
                "valid_from": agreement.get("validFrom"),
                "valid_to": agreement.get("validTo"),
                "is_active": agreement.get("isActive", False),
                "contract_number": agreement.get("supplyContractNumber"),
                "supply_point_id": agreement.get("supplyPoint", {}).get("id"),
                "prm": agreement.get("supplyPoint", {}).get("externalIdentifier"),
                "product": {
                    "code": agreement.get("product", {}).get("code"),
                    "name": agreement.get("product", {}).get("fullName"),
                    "display_name": agreement.get("product", {}).get("displayName"),
                },
                "tariffs": tariffs,
                "billing_frequency_months": agreement.get("billingFrequency"),
                "next_payment": None,
            }

            if next_payment := agreement.get("nextPaymentForecast"):
                agreement_data["next_payment"] = {
                    "amount": next_payment.get("amount"),
                    "date": next_payment.get("date"),
                }

            agreements.append(agreement_data)

        return agreements

    def _extract_tariffs(self, energy_rate: dict[str, Any]) -> dict[str, Any]:
        """Extract tariff information from energySupplyRate."""
        tariffs: dict[str, Any] = {
            "subscription": None,
            "consumption": {"heures_pleines": None, "heures_creuses": None},
        }

        if standing := energy_rate.get("standingRate"):
            try:
                price_ht = float(standing.get("pricePerUnit", 0)) / 100
                price_ttc = float(standing.get("pricePerUnitWithTaxes", 0)) / 100

                tariffs["subscription"] = {
                    "annual_ht_eur": round(price_ht, 2),
                    "annual_ttc_eur": round(price_ttc, 2),
                    "monthly_ttc_eur": round(price_ttc / 12, 2),
                    "currency": standing.get("currency"),
                    "unit_type": standing.get("unitType"),
                }
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Error parsing standing rate: %s", e)

        consumption_rates = []
        for rate_edge in energy_rate.get("consumptionRates", {}).get("edges", []):
            rate = rate_edge.get("node", {})
            try:
                consumption_rates.append(
                    {
                        "price_ht": round(float(rate.get("pricePerUnit", 0)) / 100, 4),
                        "price_ttc": round(
                            float(rate.get("pricePerUnitWithTaxes", 0)) / 100, 4
                        ),
                        "currency": rate.get("currency"),
                        "unit_type": rate.get("unitType"),
                    }
                )
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Error parsing consumption rate: %s", e)

        consumption_rates.sort(key=lambda x: x["price_ttc"], reverse=True)

        if len(consumption_rates) >= 2:
            tariffs["consumption"]["heures_pleines"] = consumption_rates[0]
            tariffs["consumption"]["heures_creuses"] = consumption_rates[1]
        elif len(consumption_rates) == 1:
            tariffs["consumption"]["base"] = consumption_rates[0]

        return tariffs

    async def get_energy_readings(
        self,
        property_id: str,
        start_at: str,
        end_at: str,
        market_supply_point_id: str,
        utility_type: str = "electricity",
        reading_frequency: str = "DAY_INTERVAL",
        reading_quality: str | None = None,
        first: int = 100,
    ) -> list[dict[str, Any]]:
        """Get meter readings for a property."""

        filter_key = f"{utility_type}Filters"
        filter_content = {
            "readingFrequencyType": reading_frequency,
            "marketSupplyPointId": market_supply_point_id,
        }

        if reading_quality and utility_type == "electricity":
            filter_content["readingQuality"] = reading_quality

        utility_filters = [{filter_key: filter_content}]

        variables = {
            "propertyId": property_id,
            "startAt": start_at,
            "endAt": end_at,
            "utilityFilters": utility_filters,
            "first": first,
        }

        if utility_type == "gas":
            query = FRAGMENT_INTERVAL_MEASUREMENT + "\n" + QUERY_GET_METER_GAS
        else:
            query = FRAGMENT_INTERVAL_MEASUREMENT + "\n" + QUERY_GET_METER_ELECTRICITY

        result = await self._execute_with_auth(query=query, variables=variables)

        edges = (
            result.get("data", {})
            .get("property", {})
            .get("measurements", {})
            .get("edges", [])
        )

        return [edge["node"] for edge in edges]

    async def get_payment_requests(self, ledger_number: str) -> dict[str, Any] | None:
        """Get the latest payment request for a ledger."""
        variables = {"ledgerNumber": ledger_number}
        result = await self._execute_with_auth(QUERY_GET_BILLS, variables)

        if not result:
            return None

        payment_requests = (
            result.get("data", {}).get("paymentRequests", {}).get("paymentRequest", {})
        )

        edges = payment_requests.get("edges", [])
        return edges[0].get("node") if edges else None

    async def get_all_payment_requests(
        self, account_number: str
    ) -> dict[str, dict[str, Any]]:
        """Get payment requests for all ledgers of an account."""

        account_data = await self.get_account_data(account_number)
        ledgers = account_data.get("ledgers", {})

        payment_requests = {}

        for ledger_type, ledger_info in ledgers.items():
            ledger_number = ledger_info.get("number")

            if not ledger_number:
                continue

            try:
                payment_request = await self.get_payment_requests(ledger_number)
                if payment_request:
                    payment_requests[ledger_type] = payment_request
            except (KeyError, ValueError) as err:
                _LOGGER.warning(
                    "Failed to fetch payment request for ledger %s (%s): %s",
                    ledger_type,
                    ledger_number,
                    err,
                )
                continue

        return payment_requests

    async def get_electricity_index(
        self, account_number: str, prm_id: str
    ) -> dict[str, Any] | None:
        """Get the electricity index with HP/HC breakdown or BASE rate."""
        variables = {"accountNumber": account_number, "prmId": prm_id}
        result = await self._execute_with_auth(QUERY_GET_INDEX_ELECTRICITY, variables)

        if not result:
            _LOGGER.warning("No electricity index data for PRM %s", prm_id)
            return None

        edges = result.get("data", {}).get("electricityReading", {}).get("edges", [])
        if not edges:
            _LOGGER.warning("No electricity readings in response for PRM %s", prm_id)
            return None

        index_data = {}
        period_start = None
        period_end = None
        tariff_type = None

        for edge in edges:
            node = edge.get("node", {})
            temp_class = node.get("calendarTempClass")

            if temp_class in ["HP", "HC", "BASE"]:
                key = temp_class.lower()
                index_data[key] = {
                    "consumption": node.get("consumption"),
                    "index_start": node.get("indexStartValue"),
                    "index_end": node.get("indexEndValue"),
                    "status": node.get("statusProcessed"),
                    "consumption_reliability": node.get("consumptionReliability"),
                    "index_reliability": node.get("indexReliability"),
                }

                if temp_class == "BASE":
                    tariff_type = "BASE"
                elif temp_class in ["HP", "HC"] and tariff_type != "BASE":
                    tariff_type = "HPHC"

                if not period_start:
                    period_start = node.get("periodStartAt")
                    period_end = node.get("periodEndAt")

        if not index_data:
            _LOGGER.warning("No index data found for PRM %s", prm_id)
            return None

        result_data = {
            "tariff_type": tariff_type,
            "period_start": period_start,
            "period_end": period_end,
        }

        result_data.update(index_data)

        return result_data
