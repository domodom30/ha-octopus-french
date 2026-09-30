"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_TOKEN_EXPIRY = "refresh_token_expiry"

LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

DEFAULT_SCAN_INTERVAL = 60

INTELLIGENT_SCAN_INTERVAL = 5
PREVIOUS_MONTH_OVERLAP_DAYS = 7

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_RECOMPUTE_STATISTICS = "recompute_statistics"
SERVICE_PURGE_ORPHAN_STATISTICS = "purge_orphan_statistics"

ISSUE_HC_FALLBACK_LINKY = "hc_fallback_linky_{}"
ISSUE_UNKNOWN_CONSUMPTION_LABEL = "unknown_consumption_label_{}"

TARIFF_TYPE_TEMPO = "TEMPO"
TARIFF_TYPE_HPHC_TWO_SEASON = "HPHC_2_SAISONS"

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

TEMPO_SHORT_LABELS: frozenset[str] = frozenset(
    {
        "TEMPO_ETE_HP",
        "TEMPO_ETE_HC",
        "TEMPO_HIVER_HP",
        "TEMPO_HIVER_HC",
        "TEMPO_ROUGE_HP",
        "TEMPO_ROUGE_HC",
    }
)

TEMPO_PRODUCT_CODE_KEYWORDS: tuple[str, ...] = ("TEMPO", "OCTOFLEX")

TEMPO_TEMPORAL_CLASS_CODES: frozenset[str] = frozenset(
    {"HPP", "HCP", "HPHI", "HCHI", "HPE", "HCE"}
)

TWO_SEASON_TEMPORAL_CLASS_TO_SEASON: dict[str, str] = {
    "HPB": "ETE",
    "HCB": "ETE",
    "HPH": "HIVER",
    "HCH": "HIVER",
}

TWO_SEASON_TEMPORAL_CLASS_CODES: frozenset[str] = frozenset(
    TWO_SEASON_TEMPORAL_CLASS_TO_SEASON
)

TWO_SEASON_CANONICAL_LABELS: frozenset[str] = frozenset(
    {
        "HEURES_PLEINES_ETE",
        "HEURES_CREUSES_ETE",
        "HEURES_PLEINES_HIVER",
        "HEURES_CREUSES_HIVER",
    }
)

TEMPO_CALENDAR_COLORS: frozenset[str] = frozenset({"ETE", "HIVER", "ROUGE"})

TEMPO_TEMPORAL_CLASS_TO_COLOR: dict[str, str] = {
    "HPP": "ROUGE",
    "HCP": "ROUGE",
    "HPHI": "HIVER",
    "HCHI": "HIVER",
    "HPE": "ETE",
    "HCE": "ETE",
}

FRENCH_MONTH_NUMBERS: dict[str, int] = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}

TEMPO_DEFAULT_SEASON_MONTHS: dict[str, tuple[int, int]] = {
    "ETE": (4, 10),
    "HIVER": (11, 3),
}

TWO_SEASON_DEFAULT_SEASON_MONTHS: dict[str, tuple[int, int]] = {
    "ETE": (4, 10),
    "HIVER": (11, 3),
}

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
    "energy_summer_peak_hours": "HEURES_PLEINES_ETE",
    "energy_summer_off_peak_hours": "HEURES_CREUSES_ETE",
    "energy_winter_peak_hours": "HEURES_PLEINES_HIVER",
    "energy_winter_off_peak_hours": "HEURES_CREUSES_HIVER",
}

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
    "cost_summer_peak_hours": "HEURES_PLEINES_ETE",
    "cost_summer_off_peak_hours": "HEURES_CREUSES_ETE",
    "cost_winter_peak_hours": "HEURES_PLEINES_HIVER",
    "cost_winter_off_peak_hours": "HEURES_CREUSES_HIVER",
}
