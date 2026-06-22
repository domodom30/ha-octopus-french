"""Tests pour normalize_consumption_label."""

from __future__ import annotations

import pytest

from custom_components.octopus_french.utils import normalize_consumption_label

# Mapping clé capteur → label canonique, identique à celui de electricity.py.
_CONSUMPTION_MAPPING = {
    "energy_base": "BASE",
    "energy_peak_hours": "HEURES_PLEINES",
    "energy_off_peak_hours": "HEURES_CREUSES",
}


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # Labels legacy (déjà canoniques).
        pytest.param("HEURES_PLEINES", "HEURES_PLEINES", id="legacy_hp"),
        pytest.param("HEURES_CREUSES", "HEURES_CREUSES", id="legacy_hc"),
        pytest.param("HEURES_BASE", "BASE", id="legacy_heures_base"),
        pytest.param("BASE", "BASE", id="legacy_base"),
        # Labels Effacement HPHC (format réel du compte testé) → remappés.
        pytest.param(
            "CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0",
            "HEURES_PLEINES",
            id="effacement_hp",
        ),
        pytest.param(
            "CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0",
            "HEURES_CREUSES",
            id="effacement_hc",
        ),
        # Labels Tempo OctoFlex → inchangés (ne commencent pas par EFFACEMENT).
        pytest.param(
            "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
            "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
            id="tempo_octoflex_hpe",
        ),
        pytest.param(
            "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0",
            "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0",
            id="tempo_octoflex_hcp",
        ),
        # Labels Tempo courts → inchangés (pris en charge par leur propre branche).
        pytest.param("TEMPO_ETE_HP", "TEMPO_ETE_HP", id="tempo_court_ete_hp"),
        pytest.param("TEMPO_ROUGE_HC", "TEMPO_ROUGE_HC", id="tempo_court_rouge_hc"),
        # Labels génériques HP/HC non-Effacement → inchangés (heuristique restreinte).
        pytest.param("SOME_TARIFF_HP_EXTRA", "SOME_TARIFF_HP_EXTRA", id="generic_hp"),
        pytest.param("OTHER_HC", "OTHER_HC", id="generic_hc"),
        # Labels divers / vides → inchangés.
        pytest.param("ABONNEMENT", "ABONNEMENT", id="abonnement"),
        pytest.param("", "", id="empty"),
    ],
)
def test_normalize_consumption_label(label: str, expected: str) -> None:
    """La normalisation ne remappe que les labels Effacement explicites."""
    assert normalize_consumption_label(label) == expected


def _run_label_matching(
    labels_and_values: list[tuple[str, float]], key: str
) -> float:
    """Reproduit la boucle interne qui accumule la consommation pour une clé.

    Réplique la logique de OctopusElectricitySensor._calculate_monthly_total /
    _async_import_statistics afin de valider le bout-à-bout du matching.
    """
    total = 0.0
    expected = _CONSUMPTION_MAPPING.get(key)
    for raw_label, value in labels_and_values:
        if normalize_consumption_label(raw_label) == expected:
            total += value
    return total


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        pytest.param("energy_peak_hours", 5.0, id="hp_key"),
        pytest.param("energy_off_peak_hours", 3.0, id="hc_key"),
    ],
)
def test_effacement_labels_match_energy_keys(key: str, expected: float) -> None:
    """Les labels Effacement alimentent bien les capteurs HP/HC (bug corrigé)."""
    stats = [
        ("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 5.0),
        ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 3.0),
        ("ABONNEMENT", 0.0),
    ]
    assert _run_label_matching(stats, key) == pytest.approx(expected)


def test_no_cross_contamination() -> None:
    """Un label HP ne doit pas alimenter la clé HC et inversement."""
    stats = [("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 9.9)]
    assert _run_label_matching(stats, "energy_off_peak_hours") == 0.0


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        pytest.param("energy_peak_hours", 7.5, id="legacy_hp"),
        pytest.param("energy_off_peak_hours", 2.5, id="legacy_hc"),
    ],
)
def test_legacy_labels_still_match(key: str, expected: float) -> None:
    """Non-régression : les labels legacy HP/HC continuent de matcher."""
    stats = [("HEURES_PLEINES", 7.5), ("HEURES_CREUSES", 2.5)]
    assert _run_label_matching(stats, key) == pytest.approx(expected)


def test_multi_day_accumulation() -> None:
    """Sommation sur plusieurs relevés (comme dans le total mensuel)."""
    days = [
        [
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 3.0),
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 5.0),
        ],
        [
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 2.5),
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 4.5),
        ],
    ]
    hp_total = sum(_run_label_matching(d, "energy_peak_hours") for d in days)
    hc_total = sum(_run_label_matching(d, "energy_off_peak_hours") for d in days)
    assert hp_total == pytest.approx(5.5)
    assert hc_total == pytest.approx(9.5)
