"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_TOKEN_EXPIRY = "refresh_token_expiry"

LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

DEFAULT_SCAN_INTERVAL = 60
# Kraken applique un rate-limit dynamique (KT-CT-1199) : un polling à la minute
# du portefeuille Intelligent (devices + préférences + dispatches) le déclenche.
INTELLIGENT_SCAN_INTERVAL = 5
PREVIOUS_MONTH_OVERLAP_DAYS = 7

SERVICE_FORCE_UPDATE = "force_update"

TARIFF_TYPE_TEMPO = "TEMPO"

TEMPO_STATISTICS_LABELS: frozenset[str] = frozenset(
    {
        "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
        "CONSUMPTION_OCTOFLEX_4_V4_HCE_0.0_37.0",
        "CONSUMPTION_OCTOFLEX_4_V4_HPHI_0.0_37.0",
        "CONSUMPTION_OCTOFLEX_4_V4_HCHI_0.0_37.0",
        "CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0",
        "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0",
    }
)

TEMPO_PRODUCT_CODE_KEYWORDS: tuple[str, ...] = ("TEMPO", "OCTOFLEX")

TEMPO_TEMPORAL_CLASS_CODES: frozenset[str] = frozenset(
    {"HPP", "HCP", "HPHI", "HCHI", "HPE", "HCE"}
)

TEMPO_CALENDAR_COLORS: frozenset[str] = frozenset({"ETE", "HIVER", "ROUGE"})

# Clé de sensor energy_* → label de consommation renvoyé par l'API.
ENERGY_KEY_TO_LABEL: dict[str, str] = {
    "energy_base": "BASE",
    "energy_peak_hours": "HEURES_PLEINES",
    "energy_off_peak_hours": "HEURES_CREUSES",
    "energy_tempo_ete_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
    "energy_tempo_ete_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCE_0.0_37.0",
    "energy_tempo_hiver_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPHI_0.0_37.0",
    "energy_tempo_hiver_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCHI_0.0_37.0",
    "energy_tempo_rouge_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0",
    "energy_tempo_rouge_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0",
}

# Clé de sensor cost_* → label de consommation dont dérive le coût.
COST_KEY_TO_LABEL: dict[str, str] = {
    "cost_base": "BASE",
    "cost_peak_hours": "HEURES_PLEINES",
    "cost_off_peak_hours": "HEURES_CREUSES",
    "cost_tempo_ete_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
    "cost_tempo_ete_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCE_0.0_37.0",
    "cost_tempo_hiver_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPHI_0.0_37.0",
    "cost_tempo_hiver_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCHI_0.0_37.0",
    "cost_tempo_rouge_hp": "CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0",
    "cost_tempo_rouge_hc": "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0",
}
