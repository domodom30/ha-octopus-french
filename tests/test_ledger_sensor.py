"""Tests pour les capteurs Facture électricité / gaz (demandes de paiement)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.octopus_french.sensors.descriptions import LEDGER_SENSORS
from custom_components.octopus_french.sensors.ledger import OctopusLedgerSensor

ELECTRICITY_BILL = next(d for d in LEDGER_SENSORS if d.key == "electricity_bill")
GAS_BILL = next(d for d in LEDGER_SENSORS if d.key == "gas_bill")


def _make_sensor(payment_requests: dict, description=ELECTRICITY_BILL):
    coordinator = MagicMock()
    coordinator.data = {"payment_requests": payment_requests, "ledgers": {}}
    return OctopusLedgerSensor(coordinator, "A-12345678", description)


def test_cleared_bill_shows_total_amount():
    """Une facture prélevée (customerAmount=0) affiche son montant total."""
    sensor = _make_sensor(
        {
            "FRA_ELECTRICITY_LEDGER": {
                "paymentStatus": "CLEARED",
                "totalAmount": 7210,
                "customerAmount": 0,
                "expectedPaymentDate": "2026-10-13",
            }
        }
    )
    assert sensor.native_value == pytest.approx(72.10)
    attrs = sensor.extra_state_attributes
    assert attrs["payment_status"] == "cleared"
    assert attrs["total_amount"] == pytest.approx(72.10)
    assert attrs["customer_amount"] == 0


def test_gas_bill_uses_gas_ledger():
    """Le capteur gaz lit la demande de paiement du ledger gaz."""
    sensor = _make_sensor(
        {
            "FRA_ELECTRICITY_LEDGER": {"totalAmount": 7210, "customerAmount": 0},
            "FRA_GAS_LEDGER": {"totalAmount": 11916, "customerAmount": 0},
        },
        GAS_BILL,
    )
    assert sensor.native_value == pytest.approx(119.16)


def test_falls_back_to_customer_amount_without_total():
    """Sans totalAmount, on retombe sur customerAmount."""
    sensor = _make_sensor({"FRA_ELECTRICITY_LEDGER": {"customerAmount": 5000}})
    assert sensor.native_value == pytest.approx(50.0)


def test_no_payment_request():
    """Aucune demande de paiement : pas de valeur, statut no_data."""
    sensor = _make_sensor({})
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {
        "ledger_type": "FRA_ELECTRICITY_LEDGER",
        "status": "no_data",
    }


def test_attributes_tolerate_null_amounts():
    """Des montants à null ne font pas planter le calcul des attributs."""
    sensor = _make_sensor(
        {
            "FRA_ELECTRICITY_LEDGER": {
                "paymentStatus": None,
                "totalAmount": None,
                "customerAmount": None,
            }
        }
    )
    assert sensor.native_value is None
    attrs = sensor.extra_state_attributes
    assert attrs["payment_status"] == ""
    assert attrs["total_amount"] is None
    assert attrs["customer_amount"] is None
