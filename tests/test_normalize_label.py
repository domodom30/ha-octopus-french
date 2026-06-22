"""Tests for normalize_consumption_label and its effect on statistics/monthly calculations."""

from __future__ import annotations

import importlib.util
import pathlib
import pytest

_UTILS_PATH = pathlib.Path(__file__).parent.parent / "custom_components" / "octopus_french" / "utils.py"
_spec = importlib.util.spec_from_file_location("octopus_utils", _UTILS_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_normalize_label = _mod.normalize_consumption_label


# ── _normalize_label ──────────────────────────────────────────────────────────

class TestNormalizeLabel:
    """Unit tests for the label normalizer."""

    # Legacy labels pass through unchanged (canonical form)
    def test_legacy_heures_pleines(self):
        assert _normalize_label("HEURES_PLEINES") == "HEURES_PLEINES"

    def test_legacy_heures_creuses(self):
        assert _normalize_label("HEURES_CREUSES") == "HEURES_CREUSES"

    def test_legacy_heures_base(self):
        assert _normalize_label("HEURES_BASE") == "BASE"

    def test_legacy_base(self):
        assert _normalize_label("BASE") == "BASE"

    # CONSUMPTION_EFFACEMENT_HPHC_2 variants (real account labels)
    def test_effacement_hp(self):
        assert _normalize_label("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0") == "HEURES_PLEINES"

    def test_effacement_hc(self):
        assert _normalize_label("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0") == "HEURES_CREUSES"

    # Generic _HP_ / _HC_ anywhere in the label
    def test_generic_hp_infix(self):
        assert _normalize_label("SOME_TARIFF_HP_EXTRA") == "HEURES_PLEINES"

    def test_generic_hc_infix(self):
        assert _normalize_label("SOME_TARIFF_HC_EXTRA") == "HEURES_CREUSES"

    def test_label_ending_hp(self):
        assert _normalize_label("TARIFF_HP") == "HEURES_PLEINES"

    def test_label_ending_hc(self):
        assert _normalize_label("TARIFF_HC") == "HEURES_CREUSES"

    # Tempo labels are unchanged
    def test_tempo_bleu_hp(self):
        assert _normalize_label("TEMPO_BLEU_HP") == "HEURES_PLEINES"

    def test_tempo_bleu_hc(self):
        assert _normalize_label("TEMPO_BLEU_HC") == "HEURES_CREUSES"

    def test_tempo_blanc_hp(self):
        assert _normalize_label("TEMPO_BLANC_HP") == "HEURES_PLEINES"

    def test_tempo_rouge_hc(self):
        assert _normalize_label("TEMPO_ROUGE_HC") == "HEURES_CREUSES"

    # Unknown labels are passed through
    def test_unknown_label(self):
        assert _normalize_label("ABONNEMENT") == "ABONNEMENT"

    def test_empty_string(self):
        assert _normalize_label("") == ""


# ── Label matching in statistics / monthly totals ─────────────────────────────

def _run_label_matching(labels_and_values: list[tuple[str, float]], key: str) -> float:
    """Simulate the inner loop that accumulates consumption for a given sensor key."""
    consumption_mapping = {
        "energy_base": "BASE",
        "energy_peak_hours": "HEURES_PLEINES",
        "energy_off_peak_hours": "HEURES_CREUSES",
    }
    total = 0.0
    for raw_label, value in labels_and_values:
        label = _normalize_label(raw_label)
        if key.startswith("energy_"):
            expected = consumption_mapping.get(key)
            if label == expected:
                total += value
    return total


class TestLabelMatchingWithEffacementLabels:
    """Verify that CONSUMPTION_EFFACEMENT_* labels are matched correctly."""

    def test_hp_effacement_matches_energy_peak_hours(self):
        stats = [
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 5.0),
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 3.0),
            ("ABONNEMENT", 0.0),
        ]
        assert _run_label_matching(stats, "energy_peak_hours") == pytest.approx(5.0)

    def test_hc_effacement_matches_energy_off_peak_hours(self):
        stats = [
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 5.0),
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 3.0),
            ("ABONNEMENT", 0.0),
        ]
        assert _run_label_matching(stats, "energy_off_peak_hours") == pytest.approx(3.0)

    def test_no_cross_contamination(self):
        """HP label must not match HC key and vice versa."""
        stats = [("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 9.9)]
        assert _run_label_matching(stats, "energy_off_peak_hours") == 0.0

    def test_legacy_heures_pleines_still_works(self):
        stats = [("HEURES_PLEINES", 7.5), ("HEURES_CREUSES", 2.5)]
        assert _run_label_matching(stats, "energy_peak_hours") == pytest.approx(7.5)

    def test_legacy_heures_creuses_still_works(self):
        stats = [("HEURES_PLEINES", 7.5), ("HEURES_CREUSES", 2.5)]
        assert _run_label_matching(stats, "energy_off_peak_hours") == pytest.approx(2.5)

    def test_abonnement_ignored_for_energy_key(self):
        stats = [
            ("ABONNEMENT", 100.0),
            ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 4.0),
        ]
        assert _run_label_matching(stats, "energy_off_peak_hours") == pytest.approx(4.0)

    def test_multi_day_accumulation(self):
        """Summing over multiple readings (as in monthly total loop)."""
        days = [
            [("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 3.0),
             ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 5.0)],
            [("CONSUMPTION_EFFACEMENT_HPHC_2_HP_0.0_37.0", 2.5),
             ("CONSUMPTION_EFFACEMENT_HPHC_2_HC_0.0_37.0", 4.5)],
        ]
        hp_total = sum(_run_label_matching(d, "energy_peak_hours") for d in days)
        hc_total = sum(_run_label_matching(d, "energy_off_peak_hours") for d in days)
        assert hp_total == pytest.approx(5.5)
        assert hc_total == pytest.approx(9.5)
