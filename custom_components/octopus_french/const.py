"""Constants for the OEFR Energy integration."""

DOMAIN = "octopus_french"

CONF_ACCOUNT_NUMBER = "account_number"

LEDGER_TYPE_ELECTRICITY = "FRA_ELECTRICITY_LEDGER"
LEDGER_TYPE_GAS = "FRA_GAS_LEDGER"
LEDGER_TYPE_POT = "POT_LEDGER"

DEFAULT_SCAN_INTERVAL = 60
PREVIOUS_MONTH_OVERLAP_DAYS = 7  # Jours de chevauchement sur le mois précédent pour capter les relevés Linky tardifs

SERVICE_FORCE_UPDATE = "force_update"

# ── OctoTempo ─────────────────────────────────────────────────────────────────
# Type de tarif Tempo (3 couleurs × HP/HC)
TARIFF_TYPE_TEMPO = "TEMPO"

# Labels potentiels dans metaData.statistics pour les relevés OctoTempo.
# L'API Octopus calcule la répartition colorielle côté serveur en croisant
# les données Linky avec le calendrier Tempo RTE.
# Ces noms sont à valider dès qu'un compte OctoTempo réel sera disponible.
TEMPO_STATISTICS_LABELS: frozenset[str] = frozenset({
    "TEMPO_BLEU_HP",
    "TEMPO_BLEU_HC",
    "TEMPO_BLANC_HP",
    "TEMPO_BLANC_HC",
    "TEMPO_ROUGE_HP",
    "TEMPO_ROUGE_HC",
})

# Mots-clés recherchés dans product.code pour identifier un contrat OctoTempo.
# "OCTOFLEX" couvre le produit OctoTempo réel (ex: OCTOFLEX_4).
TEMPO_PRODUCT_CODE_KEYWORDS: tuple[str, ...] = ("TEMPO", "OCTOFLEX")

# Valeurs de calendarTempClass retournées par l'API pour les jours Tempo.
# Actuellement hypothétiques — à valider avec un compte Tempo réel.
TEMPO_CALENDAR_COLORS: frozenset[str] = frozenset({"BLEU", "BLANC", "ROUGE"})
