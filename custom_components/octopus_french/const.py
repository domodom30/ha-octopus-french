"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"

LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

CONF_SCAN_INTERVAL = "scan_interval"
UPDATE_INTERVAL = 1
DEFAULT_SCAN_INTERVAL = 60

TOKEN_REFRESH_MARGIN = 300
TOKEN_AUTO_REFRESH_INTERVAL = 50 * 60

SERVICE_FORCE_UPDATE = "force_update"

from typing import TypedDict, Any

class TariffData(TypedDict):
    price_ht: float
    price_ttc: float
    unit: str

class ElectricityData(TypedDict):
    readings: list[dict[str, Any]]
    index: dict[str, Any] | None
    tariffs: dict[str, Any] | None
