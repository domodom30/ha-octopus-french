"""Tests pour le capteur binaire HC — sources timeSlots vs offPeakLabel."""

from __future__ import annotations

from custom_components.octopus_french.utils import (
    find_calendar_hc_ranges,
    find_contract_hc_slots,
    parse_time_slots,
    resolve_hc_schedule,
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


def _make_calendar_data(
    prm: str,
    temporal_classes: list[dict],
    off_peak_label: str | None = None,
    product_code: str = "OCTOFLEX_4_V4",
) -> dict:
    """coordinator.data avec un calendrier fournisseur, sans timeSlots contrat."""
    return {
        "supply_points": {
            "electricity": [
                {
                    "prm": prm,
                    "offPeakLabel": off_peak_label,
                    "provider_temporal_classes": temporal_classes,
                }
            ]
        },
        "agreements": [
            {
                "prm": prm,
                "is_active": True,
                "product": {"code": product_code},
                "tariffs": {"consumption": {}},
            }
        ],
    }


# Classes temporelles d'un contrat OctoTempo : une description par couleur.
_OCTOTEMPO_CLASSES = [
    {"code": "HPE", "label": "HP Été", "description": ""},
    {"code": "HCE", "label": "HC Été", "description": "21H00-7H00;11H00-17H00"},
    {"code": "HPHI", "label": "HP Hiver", "description": ""},
    {"code": "HCHI", "label": "HC Hiver", "description": "21H00-7H00"},
    {"code": "HPP", "label": "HP Rouge", "description": ""},
    {"code": "HCP", "label": "HC Rouge", "description": "2H00-6H00"},
]


class TestFindCalendarHcRanges:
    """Les plages HC dérivées de providerCalendar.temporalClasses[].description."""

    def test_hphc_classic(self):
        """Format réel d'un compteur HP/HC : deux plages séparées par ';'."""
        data = _make_calendar_data(
            "PRM1",
            [
                {"code": "HC", "label": "Heures creuses", "description": "0H50-6H50"},
                {"code": "HP", "label": "Heures Pleines", "description": ""},
            ],
            product_code="ECO_CONSO_FIXE_3",
        )
        schedule = find_calendar_hc_ranges(data, "PRM1")

        assert schedule is not None
        assert schedule["source"] == "calendar"
        assert schedule["type"] == "HC"
        assert schedule["ranges"][0]["start"] == "00:50"
        assert schedule["ranges"][0]["end"] == "06:50"
        assert schedule["total_hours"] == 6.0

    def test_tempo_color_selects_matching_class(self):
        """Chaque couleur lit la description de SA classe HC (HCE/HCHI/HCP)."""
        data = _make_calendar_data("PRM1", _OCTOTEMPO_CLASSES)

        ete = find_calendar_hc_ranges(data, "PRM1", tempo_color="ETE")
        assert ete is not None
        assert [(r["start"], r["end"]) for r in ete["ranges"]] == [
            ("21:00", "07:00"),
            ("11:00", "17:00"),
        ]
        assert ete["total_hours"] == 16.0

        hiver = find_calendar_hc_ranges(data, "PRM1", tempo_color="HIVER")
        assert hiver is not None
        assert [(r["start"], r["end"]) for r in hiver["ranges"]] == [("21:00", "07:00")]

        rouge = find_calendar_hc_ranges(data, "PRM1", tempo_color="ROUGE")
        assert rouge is not None
        assert [(r["start"], r["end"]) for r in rouge["ranges"]] == [("02:00", "06:00")]

    def test_empty_description_returns_none(self):
        """Une description vide ne produit aucune plage inventée."""
        data = _make_calendar_data(
            "PRM1", [{"code": "HCE", "label": "HC Été", "description": ""}]
        )
        assert find_calendar_hc_ranges(data, "PRM1", tempo_color="ETE") is None

    def test_unknown_prm_returns_none(self):
        """Un PRM absent des supply points renvoie None."""
        data = _make_calendar_data("PRM1", _OCTOTEMPO_CLASSES)
        assert find_calendar_hc_ranges(data, "PRM_AUTRE", tempo_color="ETE") is None


class TestResolveHcSchedule:
    """Ordre de priorité contrat → calendrier → linky → none."""

    def test_contract_wins(self):
        """Les créneaux du contrat priment sur le calendrier et sur Linky."""
        data = _make_calendar_data(
            "PRM1", _OCTOTEMPO_CLASSES, off_peak_label="HC (22H00-6H00)"
        )
        data["agreements"][0]["tariffs"]["consumption"]["tempo_ete_hc"] = {
            "time_slots": [{"start": "01:00:00", "end": "05:00:00"}]
        }

        schedule = resolve_hc_schedule(data, "PRM1", tempo_color="ETE")
        assert schedule["source"] == "contract"
        assert [(r["start"], r["end"]) for r in schedule["ranges"]] == [
            ("01:00", "05:00")
        ]

    def test_calendar_used_when_contract_has_no_slots(self):
        """Sans timeSlots contrat, on lit le calendrier — pas offPeakLabel."""
        data = _make_calendar_data(
            "PRM1", _OCTOTEMPO_CLASSES, off_peak_label="HC (22H00-6H00)"
        )

        schedule = resolve_hc_schedule(data, "PRM1", tempo_color="ETE")
        assert schedule["source"] == "calendar"
        assert schedule["total_hours"] == 16.0

    def test_linky_last_resort(self):
        """Sans contrat ni calendrier exploitable, on retombe sur offPeakLabel."""
        data = _make_calendar_data("PRM1", [], off_peak_label="HC (22H00-6H00)")

        schedule = resolve_hc_schedule(data, "PRM1", tempo_color="ETE")
        assert schedule["source"] == "linky"
        assert [(r["start"], r["end"]) for r in schedule["ranges"]] == [
            ("22:00", "06:00")
        ]

    def test_none_when_no_source(self):
        """Aucune source exploitable : plage vide, l'entité devient indisponible."""
        data = _make_calendar_data("PRM1", [], off_peak_label=None)

        schedule = resolve_hc_schedule(data, "PRM1", tempo_color="ETE")
        assert schedule["source"] == "none"
        assert schedule["range_count"] == 0
