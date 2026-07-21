"""Tests for OctopusFrenchDataUpdateCoordinator's per-contract (PRM) data fetch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.octopus_french.coordinator import OctopusFrenchDataUpdateCoordinator


def _make_coordinator(api_client: MagicMock) -> OctopusFrenchDataUpdateCoordinator:
    """Instantiate the coordinator without going through HA's heavy __init__."""
    coordinator = OctopusFrenchDataUpdateCoordinator.__new__(OctopusFrenchDataUpdateCoordinator)
    coordinator.api_client = api_client
    coordinator.account_number = "A-XXXX"
    return coordinator


def _make_api_client(electricity_supply_points: list[dict]) -> MagicMock:
    """Build a fake API client whose per-PRM responses are keyed by market_supply_point_id."""
    client = MagicMock()
    client.get_account_data = AsyncMock(
        return_value={
            "account_id": "PROP-1",
            "account_number": "A-XXXX",
            "ledgers": {},
            "supply_points": {"electricity": electricity_supply_points, "gas": []},
            "agreements": [],
        }
    )

    async def fake_get_energy_readings(
        property_id, start_at, end_at, market_supply_point_id, **kwargs
    ):
        return [{"prm": market_supply_point_id, "value": f"readings-{market_supply_point_id}"}]

    async def fake_get_electricity_index(account_number, prm_id):
        return {"tariff_type": "BASE", "prm": prm_id}

    client.get_energy_readings = AsyncMock(side_effect=fake_get_energy_readings)
    client.get_electricity_index = AsyncMock(side_effect=fake_get_electricity_index)
    client.get_all_payment_requests = AsyncMock(return_value={})
    return client


@pytest.mark.asyncio
async def test_fetch_all_data_scopes_readings_and_index_per_prm() -> None:
    """Two electricity PRMs on the same account must each get their own readings/index.

    Regression test for issue #56: previously only
    electricity_supply_points[0] was ever fetched, and every PRM's sensors
    read from a single shared account_data["electricity"] blob.
    """
    api_client = _make_api_client(
        [
            {"prm": "PRM1", "distributorStatus": "ACTIF"},
            {"prm": "PRM2", "distributorStatus": "ACTIF"},
        ]
    )
    coordinator = _make_coordinator(api_client)

    result = await coordinator._fetch_all_data()

    assert set(result["electricity_by_prm"].keys()) == {"PRM1", "PRM2"}

    prm1_data = result["electricity_by_prm"]["PRM1"]
    prm2_data = result["electricity_by_prm"]["PRM2"]

    assert prm1_data["readings"] == [{"prm": "PRM1", "value": "readings-PRM1"}]
    assert prm2_data["readings"] == [{"prm": "PRM2", "value": "readings-PRM2"}]
    assert prm1_data["index"] == {"tariff_type": "BASE", "prm": "PRM1"}
    assert prm2_data["index"] == {"tariff_type": "BASE", "prm": "PRM2"}

    # Both PRMs must have been queried, each with its own market_supply_point_id.
    queried_prms = {
        call.args[3] for call in api_client.get_energy_readings.await_args_list
    }
    assert queried_prms == {"PRM1", "PRM2"}


@pytest.mark.asyncio
async def test_fetch_all_data_single_prm_still_works() -> None:
    """A single-contract account (the common case) still gets its data."""
    api_client = _make_api_client([{"prm": "PRM1", "distributorStatus": "ACTIF"}])
    coordinator = _make_coordinator(api_client)

    result = await coordinator._fetch_all_data()

    assert set(result["electricity_by_prm"].keys()) == {"PRM1"}
    assert result["electricity_by_prm"]["PRM1"]["readings"] == [
        {"prm": "PRM1", "value": "readings-PRM1"}
    ]


@pytest.mark.asyncio
async def test_fetch_all_data_no_electricity_supply_points() -> None:
    """An account with no electricity supply point must not crash and returns no data."""
    api_client = _make_api_client([])
    coordinator = _make_coordinator(api_client)

    result = await coordinator._fetch_all_data()

    assert result["electricity_by_prm"] == {}


@pytest.mark.asyncio
async def test_fetch_all_data_filters_out_terminated_meters() -> None:
    """A RESIL (terminated) meter must not be fetched or appear in electricity_by_prm."""
    api_client = _make_api_client(
        [
            {"prm": "PRM1", "distributorStatus": "ACTIF"},
            {"prm": "PRM_TERMINATED", "distributorStatus": "RESIL"},
        ]
    )
    coordinator = _make_coordinator(api_client)

    result = await coordinator._fetch_all_data()

    assert set(result["electricity_by_prm"].keys()) == {"PRM1"}
