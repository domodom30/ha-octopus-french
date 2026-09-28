"""
Tests des tickets de réparation et du masquage dans le diagnostic.

Les anomalies qui remontent en issue GitHub — plages HC retombées sur l'étiquette
Linky, label de consommation non reconnu — n'étaient signalées qu'au journal, que
personne ne lit. Elles deviennent des tickets de réparation, dont la clé ne doit
jamais contenir d'identifiant de compteur : le registre est persisté sur disque et
affiché dans l'interface.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from custom_components.octopus_french.diagnostics import (
    _redact_identifiers,
    _redact_meter_keys,
)
from custom_components.octopus_french.repairs import (
    _meters_on_linky_fallback,
    _safe_key,
    _unknown_consumption_labels,
)

PRM = "12345678901234"

_OCTOTEMPO_CLASSES = [
    {"code": "HPE", "description": "Avril à octobre, de 7h à 11h et de 17h à 21h"},
    {"code": "HCE", "description": "Avril à octobre, 21h à 7h et de 11h à 17h"},
    {"code": "HPP", "description": "Heures pleines en jour rouge, de 7h à 21h"},
    {"code": "HCP", "description": "Heures creuses en jour rouge, de 21h à 7h"},
]


def _data(
    temporal_classes: list[dict] | None = None,
    off_peak_label: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Données de coordinateur minimales pour un compteur électrique."""
    return {
        "supply_points": {
            "electricity": [
                {
                    "prm": PRM,
                    "provider_temporal_classes": temporal_classes or [],
                    "offPeakLabel": off_peak_label,
                }
            ]
        },
        "agreements": [
            {
                "prm": PRM,
                "is_active": True,
                "product": {"code": "OCTOFLEX_4"},
                "tariffs": {"consumption": {}},
            }
        ],
        "electricity_by_prm": {
            PRM: {
                "readings": [
                    {
                        "startAt": "2026-06-01T00:00:00+02:00",
                        "metaData": {
                            "statistics": [
                                {"label": label, "value": "1.0"}
                                for label in (labels or [])
                            ]
                        },
                    }
                ],
                "index": {},
            }
        },
    }


class TestLinkyFallbackDetection:
    """Repli des plages HC sur l'étiquette du compteur, sur un contrat Tempo."""

    def test_tempo_without_usable_calendar_is_flagged(self) -> None:
        """Sans description exploitable, le repli Linky ampute la plage d'été."""
        classes = [{"code": code, "description": ""} for code in ("HCE", "HPE")]
        data = _data(classes, off_peak_label="HC (22H00-6H00)")

        assert _meters_on_linky_fallback(data) == [PRM]

    def test_usable_calendar_raises_nothing(self) -> None:
        """Un calendrier lisible donne les bonnes plages : aucun ticket."""
        data = _data(_OCTOTEMPO_CLASSES, off_peak_label="HC (22H00-6H00)")

        assert _meters_on_linky_fallback(data) == []

    def test_non_tempo_contract_is_ignored(self) -> None:
        """Le repli Linky est légitime sur un contrat HP/HC : rien à signaler."""
        classes = [{"code": "HP", "description": ""}, {"code": "HC", "description": ""}]
        data = _data(classes, off_peak_label="HC (22H00-6H00)")

        assert _meters_on_linky_fallback(data) == []


class TestUnknownConsumptionLabels:
    """Labels de consommation qui n'alimentent aucune statistique."""

    @pytest.mark.parametrize(
        "label",
        [
            pytest.param("HEURES_PLEINES", id="canonique"),
            pytest.param("ABONNEMENT", id="sans-statistique-attendue"),
            pytest.param("CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0", id="tempo-connu"),
        ],
    )
    def test_known_labels_raise_nothing(self, label: str) -> None:
        """Un label pris en charge ne doit produire aucun ticket."""
        assert _unknown_consumption_labels(_data(labels=[label])) == set()

    def test_unknown_label_is_reported(self) -> None:
        """Un label inédit signifie des kWh absents du tableau de bord Énergie."""
        data = _data(labels=["CONSUMPTION_OFFRE_INEDITE_XYZ_0.0_37.0"])

        assert _unknown_consumption_labels(data) == {
            "CONSUMPTION_OFFRE_INEDITE_XYZ_0.0_37.0"
        }


class TestIssueKeys:
    """La clé d'un ticket est persistée : elle ne doit rien exposer."""

    def test_meter_id_is_hashed_out_of_the_key(self) -> None:
        """Le PRM ne doit apparaître ni en clair ni en fragment dans la clé."""
        key = _safe_key("hc_fallback_linky_{}", PRM)

        assert PRM not in key
        assert re.search(r"\d{14}", key) is None
        assert key.startswith("hc_fallback_linky_")

    def test_key_is_stable_and_distinct_per_meter(self) -> None:
        """Même compteur, même clé — sinon les tickets s'empileraient."""
        assert _safe_key("k_{}", PRM) == _safe_key("k_{}", PRM)
        assert _safe_key("k_{}", PRM) != _safe_key("k_{}", "98765432109876")


class TestDiagnosticsRedaction:
    """Le diagnostic est destiné à être joint à une issue publique."""

    def test_meter_keys_are_replaced_and_mapped(self) -> None:
        """La table de correspondance sert aussi aux identifiants interpolés."""
        redacted, mapping = _redact_meter_keys(
            {
                "electricity_by_prm": {PRM: {"index": {}}},
                "gas_by_pce": {"GI123456789012": {}},
            }
        )

        assert PRM not in str(redacted)
        assert mapping[PRM].startswith("**REDACTED_")
        assert mapping["GI123456789012"] != mapping[PRM]

    def test_identifiers_are_masked_inside_unique_ids(self) -> None:
        """Un PRM interpolé dans un unique_id doit disparaître lui aussi."""
        _, mapping = _redact_meter_keys({"electricity_by_prm": {PRM: {}}})

        masked = _redact_identifiers(f"octopus_french_{PRM}_tempo_color_today", mapping)

        assert PRM not in masked
        assert masked.endswith("_tempo_color_today")
