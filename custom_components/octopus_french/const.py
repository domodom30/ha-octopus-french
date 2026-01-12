"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"

# Ledger types
LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

# interval settings
UPDATE_INTERVAL = 1

# Configuration - Intervalles de mise à jour
DEFAULT_SCAN_INTERVAL = 60

# Token management
TOKEN_REFRESH_MARGIN = 300
TOKEN_AUTO_REFRESH_INTERVAL = 50 * 60

# Services
SERVICE_FORCE_UPDATE = "force_update"
