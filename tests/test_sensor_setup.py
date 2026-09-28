"""Tests du setup de la plateforme sensor — unicité des unique_ids.

Régression : en tarif Tempo, les sensors contract/subscription/subscribed_power
étaient ajoutés deux fois (une fois par la boucle générique, une fois par le
bloc Tempo), provoquant une collision de unique_id à chaque démarrage.
"""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.octopus_french import sensor as sensor_platform

_TEMPO_DATA = {
    "supply_points": {
        "electricity": [
            {
                "prm": "PRM1",
                "id": "meterpoint-graphql-id",
                "meterKind": "LINKY",
                "provider_temporal_classes": [{"code": "HPP"}, {"code": "HCP"}],
            }
        ],
        "gas": [],
    },
    "electricity_by_prm": {"PRM1": {"readings": [], "index": None}},
    "agreements": [],
    "ledgers": {},
    "gas": [],
    "payment_requests": {},
}


def _make_entry(data: dict) -> SimpleNamespace:
    """Construire une fausse config entry avec runtime_data."""
    coordinator = MagicMock()
    coordinator.data = data
    return SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=coordinator,
            account_number="A-123",
            intelligent_coordinator=None,
        )
    )


async def test_tempo_setup_has_no_duplicate_unique_ids() -> None:
    """Un compteur Tempo ne doit produire aucun unique_id en double."""
    entry = _make_entry(_TEMPO_DATA)
    added: list = []

    await sensor_platform.async_setup_entry(MagicMock(), entry, added.extend)

    unique_ids = [entity.unique_id for entity in added]
    duplicates = [uid for uid, count in Counter(unique_ids).items() if count > 1]
    assert not duplicates, f"unique_ids en double : {duplicates}"

    # Les sensors communs sont bien présents, mais une seule fois chacun.
    for key in ("contract", "subscription", "subscribed_power"):
        assert unique_ids.count(f"octopus_french_PRM1_{key}") == 1

    # Le setup Tempo expose bien les sensors spécifiques.
    assert "octopus_french_PRM1_tempo_color_today" in unique_ids


_CLASSIC_HPHC_DATA = {
    "supply_points": {
        "electricity": [
            {
                "prm": "PRM1",
                "id": "meterpoint-graphql-id",
                "meterKind": "LINKY",
                "provider_temporal_classes": [{"code": "HP"}, {"code": "HC"}],
            }
        ],
        "gas": [],
    },
    "electricity_by_prm": {
        "PRM1": {
            "readings": [],
            "index": {"tariff_type": "HPHC", "hp": {}, "hc": {}},
        }
    },
    "agreements": [],
    "ledgers": {},
    "gas": [],
    "payment_requests": {},
}

_TWO_SEASON_HPHC_DATA = {
    "supply_points": {
        "electricity": [
            {
                "prm": "PRM1",
                "id": "meterpoint-graphql-id",
                "meterKind": "LINKY",
                "provider_temporal_classes": [
                    {"code": "HPB"},
                    {"code": "HCB"},
                    {"code": "HPH"},
                    {"code": "HCH"},
                ],
            }
        ],
        "gas": [],
    },
    "electricity_by_prm": {
        "PRM1": {
            "readings": [],
            "index": {
                "tariff_type": "HPHC_2_SAISONS",
                "hp_ete": {},
                "hc_ete": {},
                "hp_hiver": {},
                "hc_hiver": {},
            },
        }
    },
    "agreements": [],
    "ledgers": {},
    "gas": [],
    "payment_requests": {},
}

_CLASSIC_ONLY_KEYS = {
    "energy_peak_hours",
    "energy_off_peak_hours",
    "cost_peak_hours",
    "cost_off_peak_hours",
    "rate_peak_hours",
    "rate_off_peak_hours",
}
_CLASSIC_ONLY_INDEX_KEYS = {
    "meter_index_peak_hours",
    "meter_index_off_peak_hours",
}
_TWO_SEASON_ONLY_KEYS = {
    "energy_summer_peak_hours",
    "energy_summer_off_peak_hours",
    "energy_winter_peak_hours",
    "energy_winter_off_peak_hours",
    "cost_summer_peak_hours",
    "cost_summer_off_peak_hours",
    "cost_winter_peak_hours",
    "cost_winter_off_peak_hours",
    "rate_summer_peak_hours",
    "rate_summer_off_peak_hours",
    "rate_winter_peak_hours",
    "rate_winter_off_peak_hours",
}
_TWO_SEASON_ONLY_INDEX_KEYS = {
    "meter_index_summer_peak_hours",
    "meter_index_summer_off_peak_hours",
    "meter_index_winter_peak_hours",
    "meter_index_winter_off_peak_hours",
}


async def test_classic_hphc_meter_gets_only_classic_sensors() -> None:
    """Un compteur HP/HC classique ne reçoit ni capteurs ni index deux saisons.

    Ils resteraient indisponibles en permanence : ses relevés ne portent que
    les registres HP et HC (issue #85).
    """
    entry = _make_entry(_CLASSIC_HPHC_DATA)
    added: list = []

    await sensor_platform.async_setup_entry(MagicMock(), entry, added.extend)

    keys = {entity.unique_id.removeprefix("octopus_french_PRM1_") for entity in added}

    assert keys >= _CLASSIC_ONLY_KEYS
    assert keys >= _CLASSIC_ONLY_INDEX_KEYS
    assert not (_TWO_SEASON_ONLY_KEYS & keys)
    assert not (_TWO_SEASON_ONLY_INDEX_KEYS & keys)


async def test_two_season_meter_gets_only_seasonal_sensors() -> None:
    """Un compteur HP/HC deux-saisons ne reçoit ni capteurs ni index classiques.

    Sans cette scission, un compte deux-saisons voit ses coûts comptés deux
    fois (une fois sous cost_peak_hours, une fois sous cost_summer_peak_hours)
    puisque les deux capteurs captent les mêmes statistiques (issue #85).
    """
    entry = _make_entry(_TWO_SEASON_HPHC_DATA)
    added: list = []

    await sensor_platform.async_setup_entry(MagicMock(), entry, added.extend)

    keys = {entity.unique_id.removeprefix("octopus_french_PRM1_") for entity in added}

    assert keys >= _TWO_SEASON_ONLY_KEYS
    assert keys >= _TWO_SEASON_ONLY_INDEX_KEYS
    assert not (_CLASSIC_ONLY_KEYS & keys)
    assert not (_CLASSIC_ONLY_INDEX_KEYS & keys)
