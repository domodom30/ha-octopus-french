"""Tests pour normalize_consumption_label."""

from __future__ import annotations

import logging

import pytest

from custom_components.octopus_french import utils
from custom_components.octopus_french.utils import (
    normalize_consumption_label,
    normalize_provider_calendar,
)

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
        # Le nom de l'offre est interpolé dans le label : le segment HP/HC est
        # reconnu quelle que soit l'offre, sinon le cumul mensuel reste à 0
        # sur toute offre autre qu'Effacement (issue #70).
        pytest.param(
            "CONSUMPTION_AUTRE_OFFRE_HP_0.0_37.0",
            "HEURES_PLEINES",
            id="autre_offre_hp",
        ),
        pytest.param(
            "CONSUMPTION_AUTRE_OFFRE_HC_0.0_37.0",
            "HEURES_CREUSES",
            id="autre_offre_hc",
        ),
        # Un label inconnu est renvoyé tel quel (et signalé dans les logs).
        pytest.param("CONSUMPTION_MYSTERE_XX", "CONSUMPTION_MYSTERE_XX", id="inconnu"),
        pytest.param("ABONNEMENT", "ABONNEMENT", id="abonnement"),
        # Labels Tempo OctoFlex → inchangés : leur code de classe temporelle
        # (HPE/HCP/…) est reconnu avant la recherche du segment HP/HC.
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
        # Labels Tempo courts → inchangés (TEMPO_SHORT_LABELS).
        pytest.param("TEMPO_ETE_HP", "TEMPO_ETE_HP", id="tempo_court_ete_hp"),
        pytest.param("TEMPO_ROUGE_HC", "TEMPO_ROUGE_HC", id="tempo_court_rouge_hc"),
        # Le segment HP/HC n'est cherché que dans les labels CONSUMPTION_*.
        pytest.param(
            "SOME_TARIFF_HP_EXTRA",
            "SOME_TARIFF_HP_EXTRA",
            id="no_consumption_prefix_hp",
        ),
        pytest.param("OTHER_HC", "OTHER_HC", id="no_consumption_prefix_hc"),
        # Labels divers / vides → inchangés.
        pytest.param("", "", id="empty"),
    ],
)
def test_normalize_consumption_label(label: str, expected: str) -> None:
    """Le segment HP/HC est remappé quelle que soit l'offre, sauf sur Tempo."""
    assert normalize_consumption_label(label) == expected


@pytest.fixture
def fresh_warned_labels():
    """Vide le cache d'avertissements, qui est global au module."""
    utils._UNKNOWN_LABELS_WARNED.clear()
    yield
    utils._UNKNOWN_LABELS_WARNED.clear()


@pytest.mark.usefixtures("fresh_warned_labels")
@pytest.mark.parametrize(
    "label",
    [
        pytest.param("HEURES_PLEINES", id="legacy_hp"),
        pytest.param("ABONNEMENT", id="abonnement"),
        pytest.param("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", id="effacement_hp"),
        pytest.param("CONSUMPTION_AUTRE_OFFRE_HC_0.0_37.0", id="autre_offre_hc"),
        pytest.param("CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0", id="tempo_octoflex_hpe"),
        pytest.param("TEMPO_ETE_HP", id="tempo_court_ete_hp"),
        pytest.param("TEMPO_ROUGE_HC", id="tempo_court_rouge_hc"),
    ],
)
def test_supported_labels_emit_no_warning(
    label: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Un label pris en charge ne doit pas être signalé comme non reconnu.

    Les labels Tempo courts alimentent les attributs kWh du dernier relevé
    (voir test_tempo.py) : les signaler invitait à remonter un label qui
    fonctionne.
    """
    with caplog.at_level(logging.WARNING, logger=utils.__name__):
        normalize_consumption_label(label)

    assert caplog.records == []


@pytest.mark.usefixtures("fresh_warned_labels")
def test_unknown_label_emits_warning_once(caplog: pytest.LogCaptureFixture) -> None:
    """Un label réellement inconnu est signalé, et une seule fois."""
    with caplog.at_level(logging.WARNING, logger=utils.__name__):
        normalize_consumption_label("CONSUMPTION_MYSTERE_XX")
        normalize_consumption_label("CONSUMPTION_MYSTERE_XX")

    assert len(caplog.records) == 1
    assert "CONSUMPTION_MYSTERE_XX" in caplog.records[0].getMessage()


def _run_label_matching(labels_and_values: list[tuple[str, float]], key: str) -> float:
    """
    Reproduit la boucle interne qui accumule la consommation pour une clé.

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


def _meter(*, codes: list[str] | None = None, calendar_id: str | None = None) -> dict:
    """Construit un meter minimal pour tester normalize_provider_calendar."""
    meter: dict = {}
    if codes is not None:
        meter["provider_temporal_classes"] = [{"code": c} for c in codes]
    if calendar_id is not None:
        meter["providerCalendar"] = {"id": calendar_id}
    return meter


@pytest.mark.parametrize(
    ("meter", "expected"),
    [
        # Classes temporelles : source privilégiée (cas réel EFFACEMENT_HPHC_2).
        pytest.param(_meter(codes=["HP", "HC"]), "HPHC", id="classes_hphc"),
        pytest.param(_meter(codes=["BASE"]), "BASE", id="classes_base"),
        pytest.param(_meter(codes=["HPP", "HCP", "HPE"]), "TEMPO", id="classes_tempo"),
        # Repli sur l'id brut quand aucune classe temporelle n'est exploitable.
        pytest.param(
            _meter(calendar_id="EFFACEMENT_HPHC_2"), "HPHC", id="fallback_effacement"
        ),
        pytest.param(_meter(calendar_id="BASE_1"), "BASE", id="fallback_base"),
        pytest.param(_meter(calendar_id="TEMPO_5_V4"), "TEMPO", id="fallback_tempo"),
        # Id inconnu sans classes → renvoyé inchangé (aucune perte d'info).
        pytest.param(
            _meter(calendar_id="MYSTERY_CALENDAR"),
            "MYSTERY_CALENDAR",
            id="fallback_unknown",
        ),
        # Meter vide → chaîne vide.
        pytest.param(_meter(), "", id="empty_meter"),
    ],
)
def test_normalize_provider_calendar(meter: dict, expected: str) -> None:
    """La famille de tarif est dérivée des classes temporelles, avec repli sur l'id."""
    assert normalize_provider_calendar(meter) == expected
