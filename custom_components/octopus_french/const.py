"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"

LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

DEFAULT_SCAN_INTERVAL = 60
PREVIOUS_MONTH_OVERLAP_DAYS = 7  # Jours de chevauchement sur le mois précédent pour capter les relevés Linky tardifs

SERVICE_FORCE_UPDATE = "force_update"
