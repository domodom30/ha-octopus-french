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
