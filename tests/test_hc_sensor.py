"""Tests pour le capteur binaire HC — sources timeSlots vs offPeakLabel."""

from __future__ import annotations

from custom_components.octopus_french.utils import (
    find_contract_hc_slots,
    parse_time_slots,
)


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
        "supply_points": {"electricity": [{"id": prm, "offPeakLabel": off_peak_label}]},
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


class TestParseTimeSlots:
    """Tests for parse_time_slots."""

    def test_single_slot(self):
        """A single overnight slot yields one range of 8 hours."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        result = parse_time_slots(slots)
        assert result["range_count"] == 1
        assert result["ranges"][0]["start"] == "22:00"
        assert result["ranges"][0]["end"] == "06:00"
        assert result["source"] == "contract"
        assert result["ranges"][0]["duration_hours"] == 8.0
        assert result["total_hours"] == 8.0

    def test_two_slots(self):
        """Cas réel : 00:50-06:50 et 14:50-16:50 (7h total)."""
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
        """No slots yields zero ranges and zero total hours."""
        result = parse_time_slots([])
        assert result["range_count"] == 0
        assert result["total_hours"] == 0.0
        assert result["source"] == "contract"

    def test_malformed_slot_skipped(self):
        """A malformed slot is skipped, keeping only the valid one."""
        slots = [
            {"start": "bad", "end": "06:00:00"},
            {"start": "22:00:00", "end": "06:00:00"},
        ]
        result = parse_time_slots(slots)
        assert result["range_count"] == 1

    def test_missing_keys_skipped(self):
        """A slot missing the `end` key is skipped."""
        slots = [{"start": "22:00:00"}]
        result = parse_time_slots(slots)
        assert result["range_count"] == 0

    def test_daytime_slot(self):
        """Créneau ne chevauchant pas minuit."""
        slots = [{"start": "14:00:00", "end": "17:00:00"}]
        result = parse_time_slots(slots)
        assert result["ranges"][0]["duration_hours"] == 3.0


class TestFindContractHcSlots:
    """Tests for find_contract_hc_slots."""

    def test_hphc_contract(self):
        """An active HPHC contract returns its configured slots."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data("PRM1", time_slots=slots)
        result = find_contract_hc_slots(data, "PRM1")
        assert result == slots

    def test_no_active_agreement(self):
        """No active agreement returns None."""
        data = {
            "supply_points": {"electricity": [{"id": "PRM1"}]},
            "agreements": [
                {
                    "prm": "PRM1",
                    "is_active": False,
                    "tariffs": {
                        "consumption": {
                            "heures_creuses": {
                                "time_slots": [{"start": "22:00:00", "end": "06:00:00"}]
                            }
                        }
                    },
                }
            ],
        }
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_wrong_prm(self):
        """An unknown PRM returns None."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data("PRM1", time_slots=slots)
        assert find_contract_hc_slots(data, "PRM_AUTRE") is None

    def test_no_time_slots(self):
        """An agreement without time slots returns None."""
        data = _make_coordinator_data("PRM1", time_slots=[])
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_no_agreements(self):
        """Empty agreements return None."""
        data = {"supply_points": {"electricity": []}, "agreements": []}
        assert find_contract_hc_slots(data, "PRM1") is None

    def test_tempo_hc_key(self):
        """Pour OctoTempo : cherche la première clé se terminant par '_hc'."""
        slots = [{"start": "22:00:00", "end": "06:00:00"}]
        data = _make_coordinator_data(
            "PRM1", time_slots=slots, tariff_key="tempo_ete_hc"
        )
        result = find_contract_hc_slots(data, "PRM1")
        assert result == slots

    def test_octoflex_fallback_uses_tempo_color_schedule(self):
        """OctoTempo ne doit pas retomber sur offPeakLabel si le contrat n'a pas de timeSlots."""
        data = {
            "agreements": [
                {
                    "prm": "PRM1",
                    "is_active": True,
                    "product": {"code": "OCTOFLEX_4"},
                    "tariffs": {
                        "consumption": {
                            "tempo_ete_hp": {"price_ttc": 0.1575},
                            "tempo_ete_hc": {"price_ttc": 0.1325},
                        }
                    },
                }
            ],
            "supply_points": {
                "electricity": [{"id": "PRM1", "offPeakLabel": "HC (22H00-6H00)"}]
            },
        }

        slots = find_contract_hc_slots(data, "PRM1", tempo_color="ETE")
        schedule = parse_time_slots(slots or [])

        assert schedule["ranges"] == [
            {
                "start": "00:00",
                "end": "07:00",
                "start_minutes": 0,
                "end_minutes": 420,
                "duration_minutes": 420,
                "duration_hours": 7.0,
            },
            {
                "start": "11:00",
                "end": "20:00",
                "start_minutes": 660,
                "end_minutes": 1200,
                "duration_minutes": 540,
                "duration_hours": 9.0,
            },
        ]
        assert schedule["total_hours"] == 16.0

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
