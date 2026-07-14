"""Tests des extracteurs face aux réponses partielles de l'API (issue #51)."""

# L'API Kraken renvoie des sous-objets explicitement `null` sur les réponses
# partielles. Un défaut `.get("clé", {})` ne protège que si la clé est absente,
# pas si elle vaut `null` : ces tests verrouillent le cas `null`.

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.octopus_french.octopus_french import OctopusFrenchApiClient
from custom_components.octopus_french.sensor import _detect_tariff_type_for_meter


@pytest.fixture
def client() -> OctopusFrenchApiClient:
    """Return an API client; the extractors under test do no I/O."""
    return OctopusFrenchApiClient(
        email="user@example.com",
        password="hunter2",
        session=MagicMock(),
    )


def test_extract_ledgers_with_null_nested_objects(
    client: OctopusFrenchApiClient,
) -> None:
    """Null supplyPoints, node, meterPoint and creditStorage are tolerated."""
    account = {
        "properties": [
            {"supplyPoints": None},
            {"supplyPoints": {"edges": [{"node": None}]}},
            {"supplyPoints": {"edges": [{"node": {"meterPoint": None}}]}},
        ],
        "creditStorage": None,
    }

    assert client._extract_ledgers(account) == {}


def test_extract_supply_points_with_null_nested_objects(
    client: OctopusFrenchApiClient,
) -> None:
    """Null supplyPoints, node and meterPoint yield no meters rather than a crash."""
    properties = [
        {"supplyPoints": None},
        {"supplyPoints": {"edges": [{"node": None}]}},
        {"supplyPoints": {"edges": [{"node": {"meterPoint": None}}]}},
    ]

    assert client._extract_supply_points(properties) == {
        "electricity": [],
        "gas": [],
    }


def test_extract_supply_points_with_null_provider_calendar(
    client: OctopusFrenchApiClient,
) -> None:
    """A null providerCalendar leaves the meter without temporal classes."""
    properties = [
        {
            "supplyPoints": {
                "edges": [
                    {
                        "node": {
                            "externalIdentifier": "12345",
                            "meterPoint": {
                                "meterKind": "SMART",
                                "providerCalendar": None,
                            },
                        }
                    }
                ]
            }
        }
    ]

    [meter] = client._extract_supply_points(properties)["electricity"]

    assert meter["prm"] == "12345"
    assert meter["provider_temporal_classes"] == []


def test_extract_agreements_with_null_nested_objects(
    client: OctopusFrenchApiClient,
) -> None:
    """Null supplyPoint and product leave empty fields rather than crashing."""
    account = {
        "agreements": {
            "edges": [
                {
                    "node": {
                        "supplyContractNumber": "C-1",
                        "supplyPoint": None,
                        "product": None,
                    }
                }
            ]
        }
    }

    [agreement] = client._extract_agreements(account)

    assert agreement["contract_number"] == "C-1"
    assert agreement["prm"] is None
    assert agreement["supply_point_id"] is None
    assert agreement["product"] == {"code": None, "name": None, "display_name": None}
    assert agreement["tariffs"] is None


def test_extract_agreements_with_null_agreements(
    client: OctopusFrenchApiClient,
) -> None:
    """A null agreements block yields no agreement."""
    assert client._extract_agreements({"agreements": None}) == []


def test_extract_tariffs_with_null_consumption_rates(
    client: OctopusFrenchApiClient,
) -> None:
    """Null consumptionRates leaves the consumption rates unset."""
    tariffs = client._extract_tariffs({"consumptionRates": None})

    assert tariffs["consumption"] == {
        "heures_pleines": None,
        "heures_creuses": None,
    }


def test_detect_tariff_type_with_null_product_code() -> None:
    """A product whose code is null does not break tariff detection."""
    # _extract_agreements always sets product.code, possibly to None, so the
    # `.get("code", "")` default never fired and None.upper() used to raise.
    data = {
        "electricity": {"readings": []},
        "agreements": [
            {"prm": "12345", "is_active": True, "product": {"code": None}},
        ],
    }

    assert _detect_tariff_type_for_meter(data, "12345") == "UNKNOWN"


def test_detect_tariff_type_with_null_metadata() -> None:
    """A reading whose metaData is null leaves the tariff undetected."""
    data = {
        "electricity": {"readings": [{"metaData": None}]},
        "agreements": [],
    }

    assert _detect_tariff_type_for_meter(data, "12345") == "UNKNOWN"
