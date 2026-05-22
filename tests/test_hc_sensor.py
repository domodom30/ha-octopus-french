"""Tests pour le capteur binaire HC — sources timeSlots vs offPeakLabel."""

from __future__ import annotations

import pytest

from custom_components.octopus_french.utils import (
    find_contract_hc_slots,
    parse_time_slots,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_coordinator_data(
    prm: str,
    time_slots: list[dict] | None = None,
    off_peak_label: str | None = None,
    tariff_key: str = "heures_creuses",
) -> dict:
    """Construire un coordinator.data minimal pour les tests."""
    hc_rate: dict = {}
    if time_slots is not None:
        hc_rate["time_slots"] = time_slots

    return {
        "supply_points": {
            "electricity": [
                {"id": prm, "offPeakLabel": off_peak_label}
            ]
        },
        "agreements": [
            {
                "prm": prm,
                "is_active": True,
                "tariffs": {
                    "subscription": None,
                    "consumption": {tariff_key: hc_rate},
                },
            }
        ],
    }


# ── parse_time_slots ──────────────────────────────────────────────────────────

class TestParseTimeSlots:
    def test_single_slot(self):
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        result = parse_time_slots(slots)
        assert result["range_count"] == 1
        assert result["ranges"][0]["start"] == "22:00"
        assert result["ranges"][0]["end"] == "06:00"
        assert result["source"] == "contract"
        # durée chevauchant minuit : 8h
        assert result["ranges"][0]["duration_hours"] == 8.0
        assert result["total_hours"] == 8.0

    def test_two_slots(self):
        """Cas réel : 00:50–06:50 et 14:50–16:50 (7h total)."""
        slots = [
            {"start": "00:50:00", "end": "06:50:00"},
            {"start": "14:50:00", "end": "16:50:00"},
        ]
        result = parse_time_slots(slots)
        assert result["range_count"] == 2
        assert result["ranges"][0]["start"] == "00:50"
        assert result["ranges"][0]["end"] == "06:50"
        assert result["ranges"][0]["duration_hours"] == 6.0
        assert result["ranges"][1]["duration_hours"] == 2.0
        assert result["total_hours"] == 8.0

    def test_empty_slots(self):
        result = parse_time_slots([])
        assert result["range_count"] == 0
        assert result["total_hours"] == 0.0
        assert result["source"] == "contract"

    def test_malformed_slot_skipped(self):
        slots = [
            {"start": "bad", "end": "06:00:00"},
            {"start": "22:00:00", "end": "06:00:00"},
        ]
        result = parse_time_slots(slots)
        assert result["range_count"] == 1  # seul le bon est gardé

    def test_missing_keys_skipped(self):
        slots = [{"start": "22:00:00"}]  # pas de 'end'
        result = parse_time_slots(slots)
        assert result["range_count"] == 0

    def test_daytime_slot(self):
        """Créneau ne chevauchant pas minuit."""
        slots = [{"start": "14:00:00", "end": "17:00:00"}]
        result = parse_time_slots(slots)
        assert result["ranges"][0]["duration_hours"] == 3.0


# ── find_contract_hc_slots ────────────────────────────────────────────────────

class TestFindContractHcSlots:
    def test_hphc_contract(self):
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data("PRM1", time_slots=slots)
        result = find_contract_hc_slots(data, "PRM1")
        assert result == slots

    def test_no_active_agreement(self):
        data = {
            "supply_points": {"electricity": [{"id": "PRM1"}]},
            "agreements": [
                {"prm": "PRM1", "is_active": False,
                 "tariffs": {"consumption": {"heures_creuses": {"time_slots": [{"start": "22:00:00", "end": "06:00:00"}]}}}}
            ],
        }
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_wrong_prm(self):
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data("PRM1", time_slots=slots)
        assert find_contract_hc_slots(data, "PRM_AUTRE") is None

    def test_no_time_slots(self):
        data = _make_coordinator_data("PRM1", time_slots=[])
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_no_agreements(self):
        data = {"supply_points": {"electricity": []}, "agreements": []}
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_tempo_hc_key(self):
        """Pour OctoTempo : cherche la première clé se terminant par '_hc'."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data("PRM1", time_slots=slots, tariff_key="tempo_bleu_hc")
        result = find_contract_hc_slots(data, "PRM1")
        assert result == slots

    def test_contract_preferred_over_linky(self):
        """find_contract_hc_slots retourne les slots contrat même si offPeakLabel existe."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data(
            "PRM1",
            time_slots=slots,
            off_peak_label="HC (23H30-7H30)",
        )
        result = find_contract_hc_slots(data, "PRM1")
        assert result == slots
