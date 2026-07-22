"""
Tests pour le scoping par PRM du coordinator électricité.

Vérifie qu'un compte avec plusieurs points de livraison (plusieurs Linky)
récupère et stocke les relevés/index de CHAQUE PRM séparément, et non plus
uniquement ceux du premier (bug de scoping mono-PRM).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from custom_components.octopus_french.coordinator import (
    OctopusFrenchDataUpdateCoordinator,
)


def _make_coordinator(
    account_data: dict[str, Any],
) -> OctopusFrenchDataUpdateCoordinator:
    """Instancie le coordinator sans passer par l'init lourd de DataUpdateCoordinator."""
    coordinator = OctopusFrenchDataUpdateCoordinator.__new__(
        OctopusFrenchDataUpdateCoordinator
    )
    coordinator.account_number = "ACC-123"

    api_client = AsyncMock()
    api_client.get_account_data.return_value = account_data

    async def _readings(
        account_id: str,
        start: str,
        end: str,
        prm_id: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return [{"startAt": "2026-05-01T00:00:00", "prm": prm_id, "value": prm_id}]

    async def _index(account_number: str, prm_id: str) -> dict[str, Any]:
        return {"prm": prm_id, "tariff_type": "BASE"}

    api_client.get_energy_readings.side_effect = _readings
    api_client.get_electricity_index.side_effect = _index
    api_client.get_all_payment_requests.return_value = {}
    coordinator.api_client = api_client
    return coordinator


async def test_electricity_scoped_per_prm() -> None:
    """Chaque PRM doit obtenir ses propres relevés et index."""
    account_data = {
        "account_id": "ID-1",
        "account_number": "ACC-123",
        "supply_points": {
            "electricity": [
                {"prm": "PRM_A", "distributorStatus": "SERVC"},
                {"prm": "PRM_B", "distributorStatus": "SERVC"},
            ],
            "gas": [],
        },
        "agreements": [],
        "ledgers": {},
    }

    coordinator = _make_coordinator(account_data)
    result = await coordinator._fetch_all_data()

    by_prm = result["electricity_by_prm"]
    assert set(by_prm) == {"PRM_A", "PRM_B"}
    # Chaque PRM porte SES propres données, pas celles du premier.
    assert by_prm["PRM_A"]["readings"][0]["prm"] == "PRM_A"
    assert by_prm["PRM_B"]["readings"][0]["prm"] == "PRM_B"
    assert by_prm["PRM_A"]["index"]["prm"] == "PRM_A"
    assert by_prm["PRM_B"]["index"]["prm"] == "PRM_B"


async def test_resiliated_supply_point_is_filtered_out() -> None:
    """Un point de livraison résilié (RESIL) est exclu du fetch."""
    account_data = {
        "account_id": "ID-1",
        "account_number": "ACC-123",
        "supply_points": {
            "electricity": [
                {"prm": "PRM_A", "distributorStatus": "SERVC"},
                {"prm": "PRM_OLD", "distributorStatus": "RESIL"},
            ],
            "gas": [],
        },
        "agreements": [],
        "ledgers": {},
    }

    coordinator = _make_coordinator(account_data)
    result = await coordinator._fetch_all_data()

    assert set(result["electricity_by_prm"]) == {"PRM_A"}
