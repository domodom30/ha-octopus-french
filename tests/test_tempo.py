"""Tests pour l'intégration de l'offre OctoTempo."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.octopus_french.const import (
    TARIFF_TYPE_TEMPO,
    TEMPO_PRODUCT_CODE_KEYWORDS,
    TEMPO_STATISTICS_LABELS,
)
from custom_components.octopus_french.octopus_french import OctopusFrenchApiClient
from custom_components.octopus_french.sensor import _detect_tariff_type_for_meter
from custom_components.octopus_french.sensors.descriptions import TEMPO_SENSORS


# ── Constantes ──────────────────────────────────────────────────────────────

_TEMPO_ENERGY_KEYS = {
    "energy_tempo_bleu_hp",
    "energy_tempo_bleu_hc",
    "energy_tempo_blanc_hp",
    "energy_tempo_blanc_hc",
    "energy_tempo_rouge_hp",
    "energy_tempo_rouge_hc",
}

_TEMPO_COST_KEYS = {
    "cost_tempo_bleu_hp",
    "cost_tempo_bleu_hc",
    "cost_tempo_blanc_hp",
    "cost_tempo_blanc_hc",
    "cost_tempo_rouge_hp",
    "cost_tempo_rouge_hc",
}

_TEMPO_RATE_KEYS = {
    "rate_tempo_bleu_hp",
    "rate_tempo_bleu_hc",
    "rate_tempo_blanc_hp",
    "rate_tempo_blanc_hc",
    "rate_tempo_rouge_hp",
    "rate_tempo_rouge_hc",
}


# ── Tests de détection du tarif ──────────────────────────────────────────────

class TestDetectTariffTypeTempo:
    """Tests pour la détection du type de tarif OctoTempo."""

    def _make_data(
        self,
        stat_labels: list[str],
        prm_id: str = "TEST_PRM",
        product_code: str = "",
    ) -> dict:
        """Construit un faux objet coordinator.data."""
        stats = [{"label": lbl, "value": "1.0"} for lbl in stat_labels]
        return {
            "electricity": {
                "readings": [
                    {"startAt": "2026-05-01T00:00:00", "metaData": {"statistics": stats}}
                ],
                "index": None,
            },
            "agreements": [
                {
                    "prm": prm_id,
                    "is_active": True,
                    "product": {"code": product_code, "display_name": "Test"},
                    "tariffs": {},
                }
            ],
        }

    def test_detection_via_tempo_label(self) -> None:
        """Un label TEMPO_BLEU_HP dans les statistics doit retourner TEMPO."""
        data = self._make_data(["TEMPO_BLEU_HP", "TEMPO_BLEU_HC"])
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_detection_via_product_code(self) -> None:
        """Un product.code contenant TEMPO doit retourner TEMPO."""
        data = self._make_data(stat_labels=[], product_code="FR_TEMPO_2024")
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_product_code_case_insensitive(self) -> None:
        """La détection du code produit est insensible à la casse."""
        data = self._make_data(stat_labels=[], product_code="fr_tempo_standard")
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_detection_base_not_affected(self) -> None:
        """Un label BASE ne doit pas être confondu avec TEMPO."""
        data = self._make_data(["BASE"])
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == "BASE"

    def test_detection_hphc_not_affected(self) -> None:
        """Les labels HP/HC standards ne doivent pas être détectés comme TEMPO."""
        data = self._make_data(["HEURES_PLEINES", "HEURES_CREUSES"])
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == "HPHC"

    def test_tempo_label_takes_priority_over_hphc(self) -> None:
        """TEMPO_BLEU_HP dans les labels a la priorité sur HEURES_PLEINES."""
        data = self._make_data(["HEURES_PLEINES", "HEURES_CREUSES", "TEMPO_BLEU_HP"])
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_other_prm_not_detected_as_tempo(self) -> None:
        """Le produit TEMPO d'un autre PRM ne doit pas affecter le PRM cible."""
        data = self._make_data(
            stat_labels=["BASE"],
            prm_id="OTHER_PRM",
            product_code="FR_TEMPO",
        )
        # On cherche TEST_PRM qui n'a qu'un reading BASE et pas d'accord Tempo
        data["electricity"]["readings"][0]["metaData"]["statistics"] = [
            {"label": "BASE", "value": "1.0"}
        ]
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == "BASE"

    def test_no_readings_fallback_to_index(self) -> None:
        """Sans readings, on utilise l'index électrique."""
        data = {
            "electricity": {
                "readings": [],
                "index": {"tariff_type": TARIFF_TYPE_TEMPO, "tempo_color": "BLEU"},
            },
            "agreements": [],
        }
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO


# ── Tests d'extraction des tarifs ────────────────────────────────────────────

class TestExtractTariffsTempo:
    """Tests pour l'extraction des 6 taux OctoTempo depuis l'API."""

    def _make_api_client(self) -> OctopusFrenchApiClient:
        """Créer un client API factice."""
        return OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

    def _make_consumption_rates(self, prices: list[float]) -> dict:
        """Construit une réponse consumptionRates avec les prix indiqués."""
        edges = [
            {
                "node": {
                    "pricePerUnit": str(int(p * 100)),
                    "pricePerUnitWithTaxes": str(int(p * 100)),
                    "currency": "EUR",
                    "unitType": "kWh",
                }
            }
            for p in prices
        ]
        return {"standingRate": None, "consumptionRates": {"edges": edges}}

    def test_six_rates_assigns_tempo_keys(self) -> None:
        """Avec 6 taux, les clés Tempo doivent être présentes dans consumption."""
        client = self._make_api_client()
        # 6 prix dans l'ordre croissant
        energy_rate = self._make_consumption_rates([0.10, 0.12, 0.14, 0.16, 0.40, 0.60])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "tempo_bleu_hc" in consumption
        assert "tempo_bleu_hp" in consumption
        assert "tempo_blanc_hc" in consumption
        assert "tempo_blanc_hp" in consumption
        assert "tempo_rouge_hc" in consumption
        assert "tempo_rouge_hp" in consumption

    def test_six_rates_ordered_by_price_ascending(self) -> None:
        """Les taux Tempo doivent être ordonnés du moins cher au plus cher."""
        client = self._make_api_client()
        # Prix dans le désordre — on s'attend à ce qu'ils soient triés
        prices = [0.40, 0.12, 0.60, 0.10, 0.16, 0.14]
        energy_rate = self._make_consumption_rates(prices)
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        bleu_hc = consumption["tempo_bleu_hc"]["price_ttc"]
        bleu_hp = consumption["tempo_bleu_hp"]["price_ttc"]
        blanc_hc = consumption["tempo_blanc_hc"]["price_ttc"]
        blanc_hp = consumption["tempo_blanc_hp"]["price_ttc"]
        rouge_hc = consumption["tempo_rouge_hc"]["price_ttc"]
        rouge_hp = consumption["tempo_rouge_hp"]["price_ttc"]

        assert bleu_hc <= bleu_hp
        assert bleu_hp <= blanc_hc
        assert blanc_hc <= blanc_hp
        assert blanc_hp <= rouge_hc
        assert rouge_hc <= rouge_hp

    def test_two_rates_does_not_create_tempo_keys(self) -> None:
        """Avec 2 taux, aucune clé Tempo ne doit être créée (offre HP/HC classique)."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.12, 0.18])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "tempo_bleu_hc" not in consumption
        assert "heures_pleines" in consumption
        assert "heures_creuses" in consumption

    def test_one_rate_creates_base_key(self) -> None:
        """Avec 1 seul taux, la clé 'base' doit être créée."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.15])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "base" in consumption
        assert "tempo_bleu_hc" not in consumption


# ── Tests des descriptions de capteurs ───────────────────────────────────────

class TestTempoSensorDescriptions:
    """Tests pour vérifier que les 19 descriptions Tempo sont définies."""

    def test_tempo_sensors_count(self) -> None:
        """Il doit y avoir exactement 19 descriptions de capteurs Tempo."""
        assert len(TEMPO_SENSORS) == 19

    def test_energy_sensor_keys(self) -> None:
        """Les 6 clés de capteurs d'énergie doivent être présentes."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert _TEMPO_ENERGY_KEYS.issubset(keys)

    def test_cost_sensor_keys(self) -> None:
        """Les 6 clés de capteurs de coût doivent être présentes."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert _TEMPO_COST_KEYS.issubset(keys)

    def test_rate_sensor_keys(self) -> None:
        """Les 6 clés de capteurs de tarif doivent être présentes."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert _TEMPO_RATE_KEYS.issubset(keys)

    def test_color_sensor_key(self) -> None:
        """Le capteur couleur du jour doit être présent."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert "tempo_color_today" in keys

    def test_no_index_sensors(self) -> None:
        """Aucun capteur d'index Linky ne doit être dans TEMPO_SENSORS."""
        keys = {s.key for s in TEMPO_SENSORS}
        index_keys = {"meter_index_base", "meter_index_peak_hours", "meter_index_off_peak_hours"}
        assert keys.isdisjoint(index_keys), (
            f"Des capteurs d'index ont été trouvés dans TEMPO_SENSORS : {keys & index_keys}"
        )


# ── Tests de la détection de couleur via l'index électrique ──────────────────

class TestElectricityIndexTempo:
    """Tests pour la détection de la couleur Tempo via get_electricity_index."""

    def _make_index_response(self, temp_class: str) -> dict:
        """Construit une fausse réponse API electricityReading."""
        return {
            "data": {
                "electricityReading": {
                    "edges": [
                        {
                            "node": {
                                "calendarTempClass": temp_class,
                                "consumption": "10.5",
                                "indexStartValue": "1000",
                                "indexEndValue": "1010",
                                "statusProcessed": "REAL",
                                "consumptionReliability": "REAL",
                                "indexReliability": "REAL",
                                "periodStartAt": "2026-05-22T00:00:00",
                                "periodEndAt": "2026-05-22T23:59:59",
                            }
                        }
                    ]
                }
            }
        }

    @pytest.mark.asyncio
    async def test_blue_day_detected(self) -> None:
        """Une classe BLEU doit être détectée comme TEMPO avec couleur BLEU."""
        from custom_components.octopus_french.octopus_french import OctopusFrenchApiClient

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "_execute_with_auth", return_value=self._make_index_response("BLEU")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_TEMPO
        assert result["tempo_color"] == "BLEU"

    @pytest.mark.asyncio
    async def test_rouge_day_detected(self) -> None:
        """Une classe ROUGE doit être détectée comme TEMPO avec couleur ROUGE."""
        from custom_components.octopus_french.octopus_french import OctopusFrenchApiClient

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "_execute_with_auth", return_value=self._make_index_response("ROUGE")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_TEMPO
        assert result["tempo_color"] == "ROUGE"

    @pytest.mark.asyncio
    async def test_hp_class_still_detected_as_hphc(self) -> None:
        """Une classe HP classique doit toujours être détectée comme HPHC."""
        from custom_components.octopus_french.octopus_french import OctopusFrenchApiClient

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "_execute_with_auth", return_value=self._make_index_response("HP")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == "HPHC"
        assert "tempo_color" not in result
