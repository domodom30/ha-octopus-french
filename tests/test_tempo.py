"""Tests pour l'intégration de l'offre OctoTempo."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.octopus_french.const import (
    COST_KEY_TO_LABEL,
    TARIFF_TYPE_HPHC_TWO_SEASON,
    TARIFF_TYPE_TEMPO,
    TEMPO_STATISTICS_LABELS,
)
from custom_components.octopus_french.octopus_french import (
    QUERY_GET_ACCOUNT_DATA,
    OctopusFrenchApiClient,
)
from custom_components.octopus_french.sensor import _detect_tariff_type_for_meter
from custom_components.octopus_french.sensors.descriptions import TEMPO_SENSORS
from custom_components.octopus_french.sensors.electricity import (
    OctopusTempoColorSensor,
    OctopusTempoCurrentRateSensor,
)
from custom_components.octopus_french.utils import (
    resolve_tempo_season,
    tempo_color_from_measurements,
)

_TEMPO_ENERGY_KEYS = {
    "energy_tempo_ete_hp",
    "energy_tempo_ete_hc",
    "energy_tempo_hiver_hp",
    "energy_tempo_hiver_hc",
    "energy_tempo_rouge_hp",
    "energy_tempo_rouge_hc",
}

_TEMPO_COST_KEYS = {
    "cost_tempo_ete_hp",
    "cost_tempo_ete_hc",
    "cost_tempo_hiver_hp",
    "cost_tempo_hiver_hc",
    "cost_tempo_rouge_hp",
    "cost_tempo_rouge_hc",
}

_TEMPO_RATE_KEYS = {
    "rate_tempo_ete_hp",
    "rate_tempo_ete_hc",
    "rate_tempo_hiver_hp",
    "rate_tempo_hiver_hc",
    "rate_tempo_rouge_hp",
    "rate_tempo_rouge_hc",
}


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
            "electricity_by_prm": {
                prm_id: {
                    "readings": [
                        {
                            "startAt": "2026-05-01T00:00:00",
                            "metaData": {"statistics": stats},
                        }
                    ],
                    "index": None,
                }
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
        """Un label CONSUMPTION_OCTOFLEX_4_V4_HPE dans les statistics doit retourner TEMPO."""
        data = self._make_data(
            [
                "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
                "CONSUMPTION_OCTOFLEX_4_V4_HCE_0.0_37.0",
            ]
        )
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
        """Le label OctoTempo a la priorité sur HEURES_PLEINES."""
        data = self._make_data(
            [
                "HEURES_PLEINES",
                "HEURES_CREUSES",
                "CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0",
            ]
        )
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_other_prm_not_detected_as_tempo(self) -> None:
        """Le produit TEMPO d'un autre PRM ne doit pas affecter le PRM cible."""
        # TEST_PRM a des relevés BASE ; un AUTRE PRM est en TEMPO.
        # La détection de TEST_PRM ne doit pas être polluée par l'autre PRM.
        data = self._make_data(stat_labels=["BASE"], prm_id="TEST_PRM")
        data["agreements"].append(
            {
                "prm": "OTHER_PRM",
                "is_active": True,
                "product": {"code": "FR_TEMPO", "display_name": "Tempo"},
                "tariffs": {},
            }
        )
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == "BASE"

    def test_no_readings_fallback_to_index(self) -> None:
        """Sans readings, on utilise l'index électrique."""
        data = {
            "electricity_by_prm": {
                "TEST_PRM": {
                    "readings": [],
                    "index": {"tariff_type": TARIFF_TYPE_TEMPO, "tempo_color": "ETE"},
                }
            },
            "agreements": [],
        }
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_TEMPO

    def test_detection_via_two_season_labels(self) -> None:
        """Des labels HPB/HCB/HPH/HCH désignent un contrat HP/HC deux saisons."""
        data = self._make_data(
            [
                "CONSUMPTION_HPHC_2_SAISONS_HPB_6.0_7.0",
                "CONSUMPTION_HPHC_2_SAISONS_HCB_6.0_7.0",
            ]
        )
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_HPHC_TWO_SEASON

    def test_no_readings_fallback_to_index_two_season(self) -> None:
        """Sans readings, l'index électrique distingue aussi le deux-saisons."""
        data = {
            "electricity_by_prm": {
                "TEST_PRM": {
                    "readings": [],
                    "index": {"tariff_type": TARIFF_TYPE_HPHC_TWO_SEASON},
                }
            },
            "agreements": [],
        }
        result = _detect_tariff_type_for_meter(data, "TEST_PRM")
        assert result == TARIFF_TYPE_HPHC_TWO_SEASON


class TestExtractTariffsTempo:
    """Tests pour l'extraction des 6 taux OctoTempo depuis l'API."""

    def test_account_query_does_not_request_consumption_rate_temporal_class(
        self,
    ) -> None:
        """temporalClass n'existe pas sur SupplyConsumptionRateType → HTTP 400.

        Régression déjà survenue en 3.3.0 puis en 4.1.3 : le champ y avait été
        ajouté, ce qui faisait rejeter toute la requête getAccountData.
        """
        # temporalClass est légitime dans le bloc `rates` qui suit : on borne le
        # découpage à consumptionRates seul.
        consumption_rates_block = QUERY_GET_ACCOUNT_DATA.split(
            "consumptionRates(first: 10)"
        )[1].split("rates(first: 20)", 1)[0]
        # Le garde-fou en commentaire dans la requête mentionne le champ : on ne
        # regarde que les lignes réellement envoyées à l'API.
        queried_fields = "\n".join(
            line
            for line in consumption_rates_block.splitlines()
            if not line.lstrip().startswith("#")
        )

        assert "temporalClass" not in queried_fields

    def _make_api_client(self) -> OctopusFrenchApiClient:
        """Créer un client API factice."""
        return OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

    def _make_consumption_rates(self, prices: list[float]) -> dict:
        """
        Construit une réponse `consumptionRates` avec les prix indiqués.

        Ce champ n'expose jamais temporalClass (le demander déclenche un
        HTTP 400) : ces taux empruntent donc le fallback par ordre de prix.
        Pour le mapping par code, voir `_make_rates`.
        """
        edges = [
            {
                "node": {
                    "pricePerUnit": str(p * 100),
                    "pricePerUnitWithTaxes": str(p * 100),
                    "currency": "EUR",
                    "unitType": "kWh",
                }
            }
            for p in prices
        ]
        return {"standingRate": None, "consumptionRates": {"edges": edges}}

    def _make_rates(self, rates: list[tuple[float, str, str]]) -> dict:
        """
        Construit une réponse `rates` telle que renvoyée par l'API.

        Chaque entrée est (prix, code de classe temporelle, description horaire),
        au format réel d'`ElectricitySupplyConsumptionRateType`.
        """
        edges = [
            {
                "node": {
                    "__typename": "ElectricitySupplyConsumptionRateType",
                    "pricePerUnit": str(price * 100),
                    "pricePerUnitWithTaxes": str(price * 100),
                    "currency": "EURO_CENTS",
                    "unitType": "KWH_CONSUMPION",
                    "timeSlots": [],
                    "temporalClass": {
                        "code": code,
                        "label": code,
                        "description": description,
                        "registerId": 1,
                    },
                }
            }
            for price, code, description in rates
        ]
        return {"standingRate": None, "rates": {"edges": edges}}

    def test_rates_map_tempo_keys_by_code(self) -> None:
        """Les 6 taux OctoTempo sont mappés par temporalClass.code, pas par prix."""
        client = self._make_api_client()
        # Prix volontairement désordonnés : un mapping par prix se tromperait.
        energy_rate = self._make_rates(
            [
                (0.60, "HPP", ""),
                (0.10, "HCE", "21H00-7H00;11H00-17H00"),
                (0.16, "HPE", ""),
                (0.40, "HCP", "2H00-6H00"),
                (0.20, "HPHI", ""),
                (0.12, "HCHI", "21H00-7H00"),
            ]
        )
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["tempo_rouge_hp"]["price_ttc"] == pytest.approx(0.60)
        assert consumption["tempo_ete_hc"]["price_ttc"] == pytest.approx(0.10)
        assert consumption["tempo_rouge_hc"]["price_ttc"] == pytest.approx(0.40)
        assert consumption["tempo_hiver_hc"]["price_ttc"] == pytest.approx(0.12)

    def test_rates_map_two_season_keys_by_code(self) -> None:
        """Les 4 taux HP/HC deux-saisons sont mappés par temporalClass.code."""
        client = self._make_api_client()
        energy_rate = self._make_rates(
            [
                (0.20, "HPB", ""),
                (0.10, "HCB", ""),
                (0.30, "HPH", ""),
                (0.15, "HCH", ""),
            ]
        )
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["heures_pleines_ete"]["price_ttc"] == pytest.approx(0.20)
        assert consumption["heures_creuses_ete"]["price_ttc"] == pytest.approx(0.10)
        assert consumption["heures_pleines_hiver"]["price_ttc"] == pytest.approx(0.30)
        assert consumption["heures_creuses_hiver"]["price_ttc"] == pytest.approx(0.15)

    def test_rates_carry_temporal_class_description(self) -> None:
        """La description horaire de la classe est conservée sur le taux."""
        client = self._make_api_client()
        energy_rate = self._make_rates([(0.10, "HCE", "21H00-7H00;11H00-17H00")])
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert (
            consumption["tempo_ete_hc"]["temporal_class_description"]
            == "21H00-7H00;11H00-17H00"
        )

    def test_rates_ignore_standing_rate_nodes(self) -> None:
        """Un éventuel nœud d'abonnement dans `rates` n'est pas pris pour un taux kWh."""
        client = self._make_api_client()
        energy_rate = self._make_rates([(0.10, "HC", "0H50-6H50")])
        energy_rate["rates"]["edges"].insert(
            0,
            {
                "node": {
                    "__typename": "ElectricityStandingRateType",
                    "pricePerUnit": "5000",
                    "pricePerUnitWithTaxes": "6000",
                    "currency": "EURO_CENTS",
                    "unitType": "DAY",
                }
            },
        )
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["heures_creuses"]["price_ttc"] == pytest.approx(0.10)
        assert "base" not in consumption

    def test_consumption_rates_used_when_rates_absent(self) -> None:
        """Sans `rates`, l'extraction retombe sur `consumptionRates`."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.20, 0.10])
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["heures_pleines"]["price_ttc"] == pytest.approx(0.20)
        assert consumption["heures_creuses"]["price_ttc"] == pytest.approx(0.10)

    def test_six_rates_assigns_tempo_keys(self) -> None:
        """Avec 6 taux, les clés Tempo doivent être présentes dans consumption."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.10, 0.12, 0.14, 0.16, 0.40, 0.60])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "tempo_ete_hc" in consumption
        assert "tempo_ete_hp" in consumption
        assert "tempo_hiver_hc" in consumption
        assert "tempo_hiver_hp" in consumption
        assert "tempo_rouge_hc" in consumption
        assert "tempo_rouge_hp" in consumption

    def test_six_rates_fallback_groups_hc_before_hp(self) -> None:
        """
        Fallback par prix : tous les HC (moins chers) avant tous les HP.

        La grille Tempo entrelace HC et HP — l'ordre croissant réel est
        ete_hc < hiver_hc < rouge_hc < ete_hp < hiver_hp < rouge_hp.
        """
        client = self._make_api_client()
        prices = [0.40, 0.12, 0.60, 0.10, 0.16, 0.14]
        energy_rate = self._make_consumption_rates(prices)
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        ete_hc = consumption["tempo_ete_hc"]["price_ttc"]
        hiver_hc = consumption["tempo_hiver_hc"]["price_ttc"]
        rouge_hc = consumption["tempo_rouge_hc"]["price_ttc"]
        ete_hp = consumption["tempo_ete_hp"]["price_ttc"]
        hiver_hp = consumption["tempo_hiver_hp"]["price_ttc"]
        rouge_hp = consumption["tempo_rouge_hp"]["price_ttc"]

        assert ete_hc <= hiver_hc <= rouge_hc <= ete_hp <= hiver_hp <= rouge_hp

    def test_fallback_does_not_swap_hiver_hp_and_rouge_hc(self) -> None:
        """
        Non-régression issue #37 : Rouge HC moins cher que Hiver HP.

        Le fallback ne doit pas permuter ces deux taux quand rouge_hc < hiver_hp.
        Grille réaliste (€/kWh TTC) : ete_hc < hiver_hc < rouge_hc < ete_hp <
        hiver_hp < rouge_hp.
        """
        client = self._make_api_client()
        prices = [0.1296, 0.1486, 0.1575, 0.1609, 0.1871, 0.7562]
        energy_rate = self._make_consumption_rates(prices)
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["tempo_hiver_hp"]["price_ttc"] == pytest.approx(0.1871)
        assert consumption["tempo_rouge_hc"]["price_ttc"] == pytest.approx(0.1575)

    def test_mapping_by_temporal_class_code_ignores_price_order(self) -> None:
        """
        Non-régression issue #37 : l'affectation suit temporalClass.code, pas le prix.

        Grille réelle de l'issue, dans le désordre. Le mapping par code n'est
        atteignable que via `rates` : `consumptionRates` n'expose pas
        temporalClass, et le demander à cet endroit casse toute la requête.
        """
        client = self._make_api_client()
        energy_rate = self._make_rates(
            [
                (0.1871, "HPHI", ""),
                (0.1575, "HCP", "2H00-6H00"),
                (0.1296, "HCE", "21H00-7H00;11H00-17H00"),
                (0.7562, "HPP", ""),
                (0.1486, "HCHI", "21H00-7H00"),
                (0.1609, "HPE", ""),
            ]
        )
        consumption = client._extract_tariffs(energy_rate)["consumption"]

        assert consumption["tempo_hiver_hp"]["price_ttc"] == pytest.approx(0.1871)
        assert consumption["tempo_rouge_hc"]["price_ttc"] == pytest.approx(0.1575)
        assert consumption["tempo_ete_hc"]["price_ttc"] == pytest.approx(0.1296)
        assert consumption["tempo_rouge_hp"]["price_ttc"] == pytest.approx(0.7562)

    def test_two_rates_does_not_create_tempo_keys(self) -> None:
        """Avec 2 taux, aucune clé Tempo ne doit être créée (offre HP/HC classique)."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.12, 0.18])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "tempo_ete_hc" not in consumption
        assert "heures_pleines" in consumption
        assert "heures_creuses" in consumption

    def test_one_rate_creates_base_key(self) -> None:
        """Avec 1 seul taux, la clé 'base' doit être créée."""
        client = self._make_api_client()
        energy_rate = self._make_consumption_rates([0.15])
        result = client._extract_tariffs(energy_rate)
        consumption = result["consumption"]

        assert "base" in consumption
        assert "tempo_ete_hc" not in consumption


class TestTempoSensorDescriptions:
    """Tests pour vérifier les 21 descriptions Tempo définies."""

    def test_tempo_sensors_count(self) -> None:
        """Il doit y avoir exactement 21 descriptions de capteurs Tempo."""
        assert len(TEMPO_SENSORS) == 21

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

    def test_tomorrow_color_key(self) -> None:
        """Le capteur couleur de demain doit être présent."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert "tempo_color_tomorrow" in keys

    def test_current_rate_key(self) -> None:
        """Le capteur tarif en cours doit être présent."""
        keys = {s.key for s in TEMPO_SENSORS}
        assert "tempo_current_rate" in keys

    def test_no_index_sensors(self) -> None:
        """Aucun capteur d'index Linky ne doit être dans TEMPO_SENSORS."""
        keys = {s.key for s in TEMPO_SENSORS}
        index_keys = {
            "meter_index_base",
            "meter_index_peak_hours",
            "meter_index_off_peak_hours",
        }
        assert keys.isdisjoint(index_keys), (
            f"Des capteurs d'index ont été trouvés dans TEMPO_SENSORS : {keys & index_keys}"
        )


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
        """Une classe BLEU (legacy) doit être détectée comme TEMPO avec couleur ETE."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "execute_with_auth", return_value=self._make_index_response("BLEU")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_TEMPO
        assert result["tempo_color"] == "ETE"

    @pytest.mark.asyncio
    async def test_rouge_day_detected(self) -> None:
        """Une classe ROUGE doit être détectée comme TEMPO avec couleur ROUGE."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "execute_with_auth", return_value=self._make_index_response("ROUGE")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_TEMPO
        assert result["tempo_color"] == "ROUGE"

    @pytest.mark.asyncio
    async def test_hp_class_still_detected_as_hphc(self) -> None:
        """Une classe HP classique doit toujours être détectée comme HPHC."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "execute_with_auth", return_value=self._make_index_response("HP")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == "HPHC"
        assert "tempo_color" not in result

    @pytest.mark.asyncio
    async def test_two_season_class_detected_as_hphc_two_season(self) -> None:
        """Une classe deux saisons a son propre tariff_type (issue #85).

        Confondue avec HPHC, elle ferait créer les capteurs des deux sous-types.
        """
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)

        with patch.object(
            client, "execute_with_auth", return_value=self._make_index_response("HPB")
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_HPHC_TWO_SEASON

    @pytest.mark.asyncio
    async def test_two_season_indexes_are_kept_separately(self) -> None:
        """Les quatre index deux-saisons ne s'écrasent pas entre eux."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)
        codes = {
            "HPB": (1000, 1010),
            "HCB": (2000, 2020),
            "HPH": (3000, 3030),
            "HCH": (4000, 4040),
        }
        response = {
            "data": {
                "electricityReading": {
                    "edges": [
                        {
                            "node": {
                                "temporalClass": {"code": code},
                                "consumption": str(end - start),
                                "indexStartValue": str(start),
                                "indexEndValue": str(end),
                                "periodStartAt": "2026-05-22T00:00:00+00:00",
                                "periodEndAt": "2026-05-22T23:59:59+00:00",
                            }
                        }
                        for code, (start, end) in codes.items()
                    ]
                }
            }
        }

        with patch.object(client, "execute_with_auth", return_value=response):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == TARIFF_TYPE_HPHC_TWO_SEASON
        assert result["hp_ete"]["index_end"] == "1010"
        assert result["hc_ete"]["index_end"] == "2020"
        assert result["hp_hiver"]["index_end"] == "3030"
        assert result["hc_hiver"]["index_end"] == "4040"

    @pytest.mark.asyncio
    async def test_two_season_node_does_not_overwrite_resolved_tariff_type(
        self,
    ) -> None:
        """Un nœud deux saisons n'écrase pas un tariff_type déjà résolu en BASE."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)
        response = {
            "data": {
                "electricityReading": {
                    "edges": [
                        {
                            "node": {
                                "temporalClass": {"code": "BASE"},
                                "consumption": "5",
                                "indexStartValue": "100",
                                "indexEndValue": "105",
                                "periodStartAt": "2026-05-22T00:00:00+00:00",
                                "periodEndAt": "2026-05-22T23:59:59+00:00",
                            }
                        },
                        {
                            "node": {
                                "temporalClass": {"code": "HPB"},
                                "consumption": "3",
                                "indexStartValue": "200",
                                "indexEndValue": "203",
                                "periodStartAt": "2026-05-22T00:00:00+00:00",
                                "periodEndAt": "2026-05-22T23:59:59+00:00",
                            }
                        },
                    ]
                }
            }
        }

        with patch.object(client, "execute_with_auth", return_value=response):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result["tariff_type"] == "BASE"

    def _make_index_response_with_date(self, temp_class: str, period_date: str) -> dict:
        """Construit une fausse réponse API avec une date de période explicite."""
        return {
            "data": {
                "electricityReading": {
                    "edges": [
                        {
                            "node": {
                                "calendarTempClass": temp_class,
                                "consumption": "8.0",
                                "indexStartValue": "2000",
                                "indexEndValue": "2008",
                                "statusProcessed": "REAL",
                                "consumptionReliability": "REAL",
                                "indexReliability": "REAL",
                                "periodStartAt": f"{period_date}T00:00:00+00:00",
                                "periodEndAt": f"{period_date}T23:59:59+00:00",
                            }
                        }
                    ]
                }
            }
        }

    @pytest.mark.asyncio
    async def test_today_color_not_tomorrow(self) -> None:
        """Une edge datée d'aujourd'hui → tempo_color, pas tempo_color_tomorrow."""
        from custom_components.octopus_french.octopus_french import (
            OctopusFrenchApiClient,
        )

        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)
        # Date locale HA, pas date.today() : sous pytest-homeassistant-custom-component
        # le fuseau HA est US/Pacific, donc les deux diffèrent entre 00h et 07h UTC.
        today_str = dt_util.now().date().isoformat()

        with patch.object(
            client,
            "execute_with_auth",
            return_value=self._make_index_response_with_date("BLEU", today_str),
        ):
            result = await client.get_electricity_index("ACC123", "PRM456")

        assert result is not None
        assert result.get("tempo_color") == "ETE"
        assert "tempo_color_tomorrow" not in result


# Ordre dans lequel l'API renvoie les six registres OctoTempo pour une même
# journée, relevé dans les logs de l'issue #84 : `HCP` arrive en tête alors que
# la journée était en fait ÉTÉ.
_ISSUE_84_REGISTER_ORDER = ("HCP", "HPE", "HPHI", "HPP", "HCE", "HCHI")


def _octotempo_edges(day: str, consumption: dict[str, float]) -> list[dict]:
    """Construit les six edges d'une journée OctoTempo, dans l'ordre de l'API."""
    return [
        {
            "node": {
                "temporalClass": {
                    "code": code,
                    "label": code,
                    "registerId": register_id,
                },
                "calendarTempClass": None,
                "consumption": consumption.get(code, 0),
                "indexStartValue": 1000,
                "indexEndValue": 1000 + int(consumption.get(code, 0)),
                "statusProcessed": "REAL",
                "consumptionReliability": "REAL",
                "indexReliability": "REAL",
                "periodStartAt": f"{day}T00:00:00+02:00",
                "periodEndAt": f"{day}T23:59:59+02:00",
            }
        }
        for register_id, code in enumerate(_ISSUE_84_REGISTER_ORDER)
    ]


def _octotempo_response(days: dict[str, dict[str, float]]) -> dict:
    """Réponse `electricityReading` couvrant plusieurs journées OctoTempo."""
    edges: list[dict] = []
    for day, consumption in sorted(days.items(), reverse=True):
        edges.extend(_octotempo_edges(day, consumption))
    return {"data": {"electricityReading": {"edges": edges}}}


class TestOctoTempoColorFromRegisters:
    """Couleur OctoTempo dérivée des registres consommés (issue #84)."""

    async def _color(self, response: dict) -> dict:
        client = OctopusFrenchApiClient.__new__(OctopusFrenchApiClient)
        with patch.object(client, "execute_with_auth", return_value=response):
            result = await client.get_electricity_index("ACC123", "PRM456")
        assert result is not None
        return result

    @pytest.mark.parametrize(
        ("consumption", "expected_color"),
        [
            pytest.param({"HPE": 3.8, "HCE": 10.7}, "ETE", id="ete"),
            pytest.param({"HPHI": 5.1, "HCHI": 12.4}, "HIVER", id="hiver"),
            pytest.param({"HPP": 4.2, "HCP": 9.9}, "ROUGE", id="rouge"),
        ],
    )
    @pytest.mark.asyncio
    async def test_color_follows_consumed_registers(
        self, consumption: dict[str, float], expected_color: str
    ) -> None:
        """La couleur est celle des registres consommés, pas de la première edge.

        Régression de l'issue #84 : `HCP` ouvre la liste dans les trois cas, donc
        l'ancienne implémentation renvoyait `ROUGE` quelle que soit la journée.
        """
        result = await self._color(_octotempo_response({"2026-08-31": consumption}))

        assert result["tariff_type"] == TARIFF_TYPE_TEMPO
        assert result["tempo_color"] == expected_color
        assert result["tempo_color_date"] == "2026-08-31"

    @pytest.mark.asyncio
    async def test_latest_consumed_day_wins(self) -> None:
        """Entre deux journées relevées, la plus récente donne la couleur."""
        result = await self._color(
            _octotempo_response(
                {
                    "2026-08-30": {"HPP": 4.2, "HCP": 9.9},
                    "2026-08-31": {"HPE": 3.8, "HCE": 10.7},
                }
            )
        )

        assert result["tempo_color"] == "ETE"
        assert result["tempo_color_date"] == "2026-08-31"

    @pytest.mark.asyncio
    async def test_day_without_consumption_falls_back(self) -> None:
        """Une journée à 0 kWh partout ne fige pas la couleur : on remonte d'un jour."""
        result = await self._color(
            _octotempo_response(
                {
                    "2026-08-30": {"HPP": 4.2, "HCP": 9.9},
                    "2026-08-31": {},
                }
            )
        )

        assert result["tempo_color"] == "ROUGE"
        assert result["tempo_color_date"] == "2026-08-30"

    @pytest.mark.asyncio
    async def test_index_values_come_from_latest_day(self) -> None:
        """Les valeurs d'index exposées sont celles du jour le plus récent."""
        result = await self._color(
            _octotempo_response(
                {
                    "2026-08-30": {"HPE": 1.0, "HCE": 2.0},
                    "2026-08-31": {"HPE": 3.0, "HCE": 4.0},
                }
            )
        )

        assert result["period_start"].startswith("2026-08-31")
        assert result["tempo_ete_hp"]["consumption"] == 3.0
        assert result["tempo_ete_hc"]["consumption"] == 4.0


class TestTempoCurrentRateSensor:
    """Tests pour OctopusTempoCurrentRateSensor."""

    def _make_coordinator(
        self,
        tempo_color: str | None,
        rate_key: str,
        rate_value: float,
        prm_id: str = "TEST_PRM",
        hc_slots: list[dict] | None = None,
    ) -> MagicMock:
        """Construit un coordinateur factice avec couleur Tempo et tarifs."""
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {
            "electricity_by_prm": {
                prm_id: {
                    "index": {"tempo_color": tempo_color} if tempo_color else {},
                }
            },
            "agreements": [
                {
                    "prm": prm_id,
                    "is_active": True,
                    "tariffs": {
                        "consumption": {
                            rate_key: {
                                "price_ttc": rate_value,
                                "price_ht": rate_value * 0.8,
                            },
                        }
                    },
                    "time_slots": hc_slots or [],
                }
            ],
            "supply_points": {"electricity": []},
        }
        return coordinator

    def _make_sensor(
        self,
        coordinator: MagicMock,
        prm_id: str = "TEST_PRM",
    ) -> OctopusTempoCurrentRateSensor:
        """Instancie le capteur sans passer par HA."""
        from homeassistant.components.sensor import (
            SensorDeviceClass,
            SensorEntityDescription,
        )
        from homeassistant.const import CURRENCY_EURO

        config = SensorEntityDescription(
            key="tempo_current_rate",
            device_class=SensorDeviceClass.MONETARY,
            native_unit_of_measurement=f"{CURRENCY_EURO}/kWh",
            suggested_display_precision=4,
        )
        sensor = OctopusTempoCurrentRateSensor.__new__(OctopusTempoCurrentRateSensor)
        sensor.coordinator = coordinator
        sensor._prm_id = prm_id
        sensor._sensor_config = config
        return sensor

    def test_returns_rate_ete_hp(self) -> None:
        """Couleur ETE + période HP → tarif tempo_ete_hp."""
        coordinator = self._make_coordinator("ETE", "tempo_ete_hp", 0.1234)
        sensor = self._make_sensor(coordinator)

        with patch.object(sensor, "_is_currently_hc", return_value=False):
            assert sensor._compute_native_value() == pytest.approx(0.1234)

    def test_returns_rate_rouge_hc(self) -> None:
        """Couleur ROUGE + période HC → tarif tempo_rouge_hc."""
        coordinator = self._make_coordinator("ROUGE", "tempo_rouge_hc", 0.1568)
        sensor = self._make_sensor(coordinator)

        with patch.object(sensor, "_is_currently_hc", return_value=True):
            assert sensor._compute_native_value() == pytest.approx(0.1568)

    def test_returns_none_when_no_color(self) -> None:
        """Sans couleur Tempo dans l'index → None."""
        coordinator = self._make_coordinator(None, "tempo_ete_hp", 0.1234)
        sensor = self._make_sensor(coordinator)

        assert sensor._compute_native_value() is None

    def test_extra_attributes_contain_color_and_period(self) -> None:
        """Les attributs doivent exposer la couleur et la période."""
        coordinator = self._make_coordinator("HIVER", "tempo_hiver_hp", 0.18)
        sensor = self._make_sensor(coordinator)

        with patch.object(sensor, "_is_currently_hc", return_value=False):
            attrs = sensor._compute_attributes()

        assert attrs["tempo_color"] == "HIVER"
        assert attrs["period_type"] == "HP"
        assert attrs["prm_id"] == "TEST_PRM"

    def test_octoflex_summer_daytime_uses_calendar_hc_range(self) -> None:
        """OctoTempo été : la plage HC de journée vient du calendrier fournisseur.

        offPeakLabel n'expose qu'une seule plage nocturne et donnerait HP à 13h ;
        la description de la classe HCE porte la vraie plage 11H-17H.
        """
        coordinator = self._make_coordinator("ETE", "tempo_ete_hc", 0.1325)
        coordinator.data["agreements"][0]["product"] = {"code": "OCTOFLEX_4_V4"}
        coordinator.data["supply_points"] = {
            "electricity": [
                {
                    "prm": "TEST_PRM",
                    "offPeakLabel": "HC (22H00-6H00)",
                    "provider_temporal_classes": [
                        {"code": "HCE", "description": "21H00-7H00;11H00-17H00"},
                        {"code": "HPE", "description": ""},
                    ],
                }
            ]
        }
        sensor = self._make_sensor(coordinator)

        with patch(
            "custom_components.octopus_french.sensors.electricity.dt_util.now",
            return_value=datetime(2026, 7, 28, 13, 0, tzinfo=ZoneInfo("Europe/Paris")),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.1325)
            attrs = sensor._compute_attributes()

        assert attrs["period_type"] == "HC"
        assert attrs["hc_source"] == "calendar"


class TestCostToConsumptionLabel:
    """Vérifie que la constante partagée couvre tous les capteurs de coût."""

    def test_all_cost_tempo_keys_present(self) -> None:
        """Les 6 clés cost_tempo_* doivent être dans la constante."""
        tempo_cost_keys = {
            "cost_tempo_ete_hp",
            "cost_tempo_ete_hc",
            "cost_tempo_hiver_hp",
            "cost_tempo_hiver_hc",
            "cost_tempo_rouge_hp",
            "cost_tempo_rouge_hc",
        }
        assert tempo_cost_keys.issubset(COST_KEY_TO_LABEL.keys())

    def test_labels_match_tempo_statistics_labels(self) -> None:
        """Les labels de consommation Tempo doivent correspondre à TEMPO_STATISTICS_LABELS."""
        tempo_labels_in_map = {
            v for k, v in COST_KEY_TO_LABEL.items() if k.startswith("cost_tempo_")
        }
        assert tempo_labels_in_map == TEMPO_STATISTICS_LABELS


class TestLatestReadingTempoAttributes:
    """Tests pour les attributs Tempo dans OctopusLatestReadingSensor."""

    def _make_coordinator(
        self,
        stats: list[dict],
        prm_id: str = "TEST_PRM",
        rate_key: str | None = None,
        rate_value: float = 0.0,
    ) -> MagicMock:
        """Construit un coordinateur factice pour latest_reading."""
        coordinator = MagicMock()
        coordinator.last_update_success = True
        agreements = []
        if rate_key:
            agreements = [
                {
                    "prm": prm_id,
                    "is_active": True,
                    "tariffs": {
                        "consumption": {
                            rate_key: {
                                "price_ttc": rate_value,
                                "price_ht": rate_value * 0.8,
                            },
                        }
                    },
                }
            ]
        coordinator.data = {
            "electricity_by_prm": {
                prm_id: {
                    "readings": [
                        {
                            "startAt": "2026-06-13T00:00:00",
                            "value": "15.0",
                            "metaData": {"statistics": stats},
                        }
                    ],
                }
            },
            "agreements": agreements,
        }
        return coordinator

    def _make_sensor(self, coordinator: MagicMock, prm_id: str = "TEST_PRM"):
        """Instancie OctopusLatestReadingSensor sans passer par HA."""
        from homeassistant.components.sensor import SensorEntityDescription

        from custom_components.octopus_french.sensors.electricity import (
            OctopusLatestReadingSensor,
        )

        config = SensorEntityDescription(key="latest_reading")
        sensor = OctopusLatestReadingSensor.__new__(OctopusLatestReadingSensor)
        sensor.coordinator = coordinator
        sensor._prm_id = prm_id
        sensor._sensor_config = config
        return sensor

    def test_tempo_kwh_attributes_populated(self) -> None:
        """Les labels TEMPO_ETE_HP/ROUGE_HC doivent peupler les attributs kWh."""
        stats = [
            {"label": "TEMPO_ETE_HP", "value": "5.0", "costInclTax": None},
            {"label": "TEMPO_ROUGE_HC", "value": "2.3", "costInclTax": None},
        ]
        coordinator = self._make_coordinator(stats)
        sensor = self._make_sensor(coordinator)

        attrs = sensor._compute_attributes()
        assert attrs.get("tempo_ete_hp") == pytest.approx(5.0)
        assert attrs.get("tempo_rouge_hc") == pytest.approx(2.3)

    @pytest.mark.parametrize(
        "codes",
        [
            pytest.param(("HCB", "HCH", "HPB", "HPH"), id="ordre_issue_85"),
            pytest.param(("HCH", "HCB", "HPH", "HPB"), id="saison_inactive_d_abord"),
        ],
    )
    @pytest.mark.parametrize(
        "inactive_value",
        [pytest.param("0.0", id="zero_texte"), pytest.param(0, id="zero_numerique")],
    )
    def test_two_season_kwh_attributes_keep_active_season(
        self, codes: tuple[str, ...], inactive_value: str | int
    ) -> None:
        """Le registre de la saison inactive, publié à zéro, n'efface pas l'autre.

        Chaque relevé d'un contrat deux saisons porte les quatre registres.
        """
        values = {
            "HCB": "4.0",
            "HPB": "9.0",
            "HCH": inactive_value,
            "HPH": inactive_value,
        }
        stats = [
            {
                "label": f"CONSUMPTION_HPHC_2_SAISONS_{code}_6.0_7.0",
                "value": values[code],
            }
            for code in codes
        ]
        coordinator = self._make_coordinator(stats)
        sensor = self._make_sensor(coordinator)

        attrs = sensor._compute_attributes()
        assert attrs["heures_pleines_kwh"] == pytest.approx(9.0)
        assert attrs["heures_creuses_kwh"] == pytest.approx(4.0)

    def test_tempo_cost_computed(self) -> None:
        """Avec un tarif disponible, le coût €/kWh doit être calculé."""
        stats = [{"label": "TEMPO_ETE_HP", "value": "10.0", "costInclTax": None}]
        coordinator = self._make_coordinator(
            stats, rate_key="tempo_ete_hp", rate_value=0.12
        )
        sensor = self._make_sensor(coordinator)

        attrs = sensor._compute_attributes()
        assert attrs.get("cout_tempo_ete_hp_euro") == pytest.approx(
            10.0 * 0.12, rel=1e-4
        )

    def test_non_tempo_attributes_unchanged(self) -> None:
        """Un relevé BASE ne doit pas produire d'attributs Tempo."""
        stats = [{"label": "HEURES_BASE", "value": "8.0", "costInclTax": None}]
        coordinator = self._make_coordinator(stats)
        sensor = self._make_sensor(coordinator)

        attrs = sensor._compute_attributes()
        assert attrs.get("heures_base") == pytest.approx(8.0)
        assert "tempo_ete_hp" not in attrs


# Descriptions relevées telles quelles sur un contrat OctoFlex réel
# (providerCalendar OCTOFLEX_4_V4) : elles portent les bornes de saison.
_OCTOFLEX_TEMPORAL_CLASSES = [
    {"code": "HPP", "description": "Heures pleines en jour rouge, de 7h à 21h"},
    {"code": "HPHI", "description": "Novembre à mars, de 7h à 21h"},
    {"code": "HCHI", "description": "Novembre à mars, de 21h à 7h"},
    {"code": "HCP", "description": "Heures creuses en jour rouge, de 21h à 7h"},
    {"code": "HPE", "description": "Avril à octobre, de 7h à 11h et de 17h à 21h"},
    {"code": "HCE", "description": "Avril à octobre, 21h à 7h et de 11h à 17h"},
]

_OCTOFLEX_PRM = "PRM_OCTOFLEX"


def _octoflex_data(
    readings: list[dict] | None = None,
    index: dict | None = None,
    temporal_classes: list[dict] | None = None,
) -> dict:
    """Données de coordinateur pour un contrat OctoFlex."""
    return {
        "supply_points": {
            "electricity": [
                {
                    "prm": _OCTOFLEX_PRM,
                    "provider_temporal_classes": (
                        _OCTOFLEX_TEMPORAL_CLASSES
                        if temporal_classes is None
                        else temporal_classes
                    ),
                }
            ]
        },
        "agreements": [
            {
                "prm": _OCTOFLEX_PRM,
                "is_active": True,
                "product": {"code": "OCTOFLEX_4"},
                "tariffs": {"consumption": {}},
            }
        ],
        "electricity_by_prm": {
            _OCTOFLEX_PRM: {"readings": readings or [], "index": index or {}}
        },
    }


def _measurement(day: str, labels: dict[str, str | None]) -> dict:
    """Un relevé journalier avec ses statistiques par classe temporelle."""
    return {
        "startAt": f"{day}T00:00:00+01:00",
        "metaData": {
            "statistics": [
                {"label": label, "value": value} for label, value in labels.items()
            ]
        },
    }


class TestTempoSeason:
    """Saison OctoTempo déduite du calendrier fournisseur."""

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            pytest.param(date(2026, 1, 15), "HIVER", id="janvier"),
            pytest.param(date(2026, 3, 31), "HIVER", id="fin-mars"),
            pytest.param(date(2026, 4, 1), "ETE", id="debut-avril"),
            pytest.param(date(2026, 6, 15), "ETE", id="juin"),
            pytest.param(date(2026, 10, 31), "ETE", id="fin-octobre"),
            pytest.param(date(2026, 11, 1), "HIVER", id="debut-novembre"),
            pytest.param(date(2026, 12, 25), "HIVER", id="decembre"),
        ],
    )
    def test_season_from_calendar_description(self, day: date, expected: str) -> None:
        """Les bornes viennent des descriptions « Avril à octobre » / « Novembre à mars »."""
        assert resolve_tempo_season(_octoflex_data(), _OCTOFLEX_PRM, day) == expected

    def test_falls_back_when_descriptions_name_no_month(self) -> None:
        """Sans mois exploitable, les bornes par défaut prennent le relais."""
        classes = [
            {"code": code, "description": "de 7h à 21h"}
            for code in ("HPE", "HCE", "HPHI", "HCHI", "HPP", "HCP")
        ]
        data = _octoflex_data(temporal_classes=classes)

        assert resolve_tempo_season(data, _OCTOFLEX_PRM, date(2026, 6, 15)) == "ETE"
        assert resolve_tempo_season(data, _OCTOFLEX_PRM, date(2026, 1, 15)) == "HIVER"

    def test_non_tempo_contract_has_no_season(self) -> None:
        """Un contrat HP/HC ne doit pas se voir attribuer de saison Tempo."""
        data = {
            "supply_points": {
                "electricity": [
                    {
                        "prm": "PRM_HPHC",
                        "provider_temporal_classes": [
                            {"code": "HP", "description": "de 7h à 21h"},
                            {"code": "HC", "description": "de 21h à 7h"},
                        ],
                    }
                ]
            },
            "agreements": [],
            "electricity_by_prm": {},
        }

        assert resolve_tempo_season(data, "PRM_HPHC", date(2026, 6, 15)) is None


class TestTempoColorFromMeasurements:
    """Couleur journalière tirée de metaData.statistics[].label."""

    @pytest.fixture(autouse=True)
    def _paris_timezone(self) -> Generator[None]:
        """Les relevés portent minuit local : la journée dépend du fuseau de HA."""
        with patch.object(dt_util, "DEFAULT_TIME_ZONE", ZoneInfo("Europe/Paris")):
            yield

    def test_red_day_detected(self) -> None:
        """Une journée dont seuls HPP/HCP consomment est un jour rouge."""
        readings = [
            _measurement(
                "2026-01-14",
                {
                    "CONSUMPTION_OCTOFLEX_4_V4_HPHI_0.0_37.0": "12.0",
                    "CONSUMPTION_OCTOFLEX_4_V4_HCHI_0.0_37.0": "8.0",
                    "ABONNEMENT": None,
                },
            ),
            _measurement(
                "2026-01-15",
                {
                    "CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0": "9.0",
                    "CONSUMPTION_OCTOFLEX_4_V4_HCP_0.0_37.0": "4.0",
                },
            ),
        ]

        assert tempo_color_from_measurements(readings) == ("ROUGE", "2026-01-15")
        assert tempo_color_from_measurements(readings, date(2026, 1, 14)) == (
            "HIVER",
            "2026-01-14",
        )

    @pytest.mark.parametrize(
        "label",
        [
            pytest.param("CONSUMPTION_OCTOFLEX_5_V1_HPP_0.0_36.0", id="autre-version"),
            pytest.param("TEMPO_ROUGE_HP", id="label-court"),
        ],
    )
    def test_label_variants_are_recognised(self, label: str) -> None:
        """Le code temporel est reconnu sans dépendre des chaînes figées de const.py."""
        readings = [_measurement("2026-01-15", {label: "9.0"})]

        assert tempo_color_from_measurements(readings) == ("ROUGE", "2026-01-15")

    @pytest.mark.parametrize(
        "labels",
        [
            pytest.param({"ABONNEMENT": None, "BASE": "16.2"}, id="aucun-label-tempo"),
            pytest.param(
                {"CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0": None}, id="valeur-absente"
            ),
            pytest.param(
                {"CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0": "n/a"}, id="valeur-illisible"
            ),
        ],
    )
    def test_unusable_statistics_yield_no_color(
        self, labels: dict[str, str | None]
    ) -> None:
        """Un compte récent n'a que des labels ABONNEMENT : aucune couleur exploitable."""
        assert tempo_color_from_measurements([_measurement("2026-01-15", labels)]) == (
            None,
            None,
        )


class TestTempoColorSensor:
    """Couleur du jour et du lendemain exposées par OctopusTempoColorSensor."""

    @pytest.fixture(autouse=True)
    def _paris_timezone(self) -> Generator[None]:
        """Les relevés portent minuit local : la journée dépend du fuseau de HA."""
        with patch.object(dt_util, "DEFAULT_TIME_ZONE", ZoneInfo("Europe/Paris")):
            yield

    def _make_sensor(self, data: dict, is_tomorrow: bool) -> OctopusTempoColorSensor:
        """Instancie le capteur sans passer par HA."""
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = data

        sensor = OctopusTempoColorSensor.__new__(OctopusTempoColorSensor)
        sensor.coordinator = coordinator
        sensor._prm_id = _OCTOFLEX_PRM
        sensor._is_tomorrow = is_tomorrow
        return sensor

    def test_tomorrow_is_available_and_follows_the_season(self) -> None:
        """La couleur du lendemain vient de la saison, plus d'un relevé daté du futur."""
        sensor = self._make_sensor(_octoflex_data(), is_tomorrow=True)

        with patch(
            "custom_components.octopus_french.utils.dt_util.now",
            return_value=datetime(2026, 6, 15, 12, 0, tzinfo=ZoneInfo("Europe/Paris")),
        ):
            assert sensor.available is True
            assert sensor._compute_native_value() == "ETE"
            attrs = sensor._compute_attributes()

        assert attrs["date"] == "2026-06-16"
        assert attrs["source"] == "season"
        assert attrs["red_day_detectable"] is False

    def test_today_is_requalified_red_by_a_daily_reading(self) -> None:
        """Un relevé du jour sur HPP/HCP l'emporte sur la saison."""
        readings = [
            _measurement(
                "2026-01-15", {"CONSUMPTION_OCTOFLEX_4_V4_HPP_0.0_37.0": "9.0"}
            )
        ]
        sensor = self._make_sensor(_octoflex_data(readings), is_tomorrow=False)

        with patch(
            "custom_components.octopus_french.utils.dt_util.now",
            return_value=datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Paris")),
        ):
            assert sensor._compute_native_value() == "ROUGE"
            attrs = sensor._compute_attributes()

        assert attrs["source"] == "measurements"
        assert attrs["reading_date"] == "2026-01-15"

    def test_today_falls_back_to_the_season_without_readings(self) -> None:
        """Sans relevé exploitable, la saison reste la source de la couleur du jour."""
        sensor = self._make_sensor(_octoflex_data(), is_tomorrow=False)

        with patch(
            "custom_components.octopus_french.utils.dt_util.now",
            return_value=datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Paris")),
        ):
            assert sensor._compute_native_value() == "HIVER"
            assert sensor._compute_attributes()["source"] == "season"


class TestTempoRateFollowsResolvedColor:
    """Le tarif en cours suit la couleur résolue, pas la couleur d'index (issue #84)."""

    def test_rate_uses_the_season_not_the_stale_index_color(self) -> None:
        """Un index resté sur ROUGE ne doit plus imposer le tarif Rouge en hiver."""
        data = _octoflex_data(index={"tempo_color": "ROUGE"})
        data["agreements"][0]["tariffs"]["consumption"] = {
            "tempo_hiver_hp": {"price_ttc": 0.1921, "price_ht": 0.1295},
            "tempo_rouge_hp": {"price_ttc": 0.6465, "price_ht": 0.5082},
        }

        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = data

        sensor = OctopusTempoCurrentRateSensor.__new__(OctopusTempoCurrentRateSensor)
        sensor.coordinator = coordinator
        sensor._prm_id = _OCTOFLEX_PRM

        with (
            patch(
                "custom_components.octopus_french.utils.dt_util.now",
                return_value=datetime(
                    2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Paris")
                ),
            ),
            patch.object(sensor, "_is_currently_hc", return_value=False),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.1921)
            assert sensor._compute_attributes()["tempo_color"] == "HIVER"
