"""
Tests du chemin gaz (Gazpar) — issue #79.

La consommation et le coût gaz restaient à 0 : les buckets de
`property.measurements` sont la seule source interrogée, alors qu'un compteur
qui n'y publie rien expose encore ses relevés d'index via `gasReading`.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.util import dt as dt_util

from custom_components.octopus_french.coordinator import (
    OctopusFrenchDataUpdateCoordinator,
)
from custom_components.octopus_french.sensors.gas import OctopusGasSensor
from custom_components.octopus_french.statistics_import import (
    OctopusStatisticsImporter,
)
from custom_components.octopus_french.utils import gas_daily_values, gas_month_total

PCE_A = "12345678901234"
PCE_B = "12345678901235"


@pytest.fixture(autouse=True)
def _paris_timezone() -> None:
    """Fixe le fuseau local : les relevés de l'API sont datés en UTC."""
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Paris"))
    yield
    dt_util.set_default_time_zone(previous)


def _monthly(start_at: str, value: str) -> dict[str, Any]:
    """Bucket MONTH_INTERVAL tel que renvoyé par `property.measurements`."""
    return {
        "__typename": "IntervalMeasurementType",
        "startAt": start_at,
        "value": value,
    }


def _index(start_at: str, end_at: str, consumption: float) -> dict[str, Any]:
    """Relevé d'index normalisé par `get_gas_readings`."""
    return {"value": consumption, "startAt": start_at, "endAt": end_at}


def test_monthly_total_uses_local_month() -> None:
    """Un bucket daté en UTC appartient au mois de son minuit local."""
    # 2026-07-31T22:00Z est le 1er août à Paris : le mois d'août, pas juillet.
    gas_data = {"monthly": [_monthly("2026-07-31T22:00:00+00:00", "22.0000")]}

    assert gas_month_total(gas_data, "2026-08") == 22.0
    assert gas_month_total(gas_data, "2026-07") == 0.0


def test_monthly_total_prefers_consolidated_bucket() -> None:
    """Le bucket mensuel de l'API prime sur la somme des relevés quotidiens."""
    gas_data = {
        "monthly": [_monthly("2026-08-01T00:00:00+02:00", "22.0000")],
        "daily": [
            {"startAt": "2026-08-01T02:00:00+02:00", "value": "1.5"},
            {"startAt": "2026-08-02T02:00:00+02:00", "value": "2.5"},
        ],
    }

    assert gas_month_total(gas_data, "2026-08") == 22.0


def test_index_period_spanning_two_months_is_prorated() -> None:
    """Un relevé d'index à cheval alimente les deux mois qu'il couvre."""
    # 30/06 22:00Z → 18/07 22:00Z = 1er au 19 juillet local, 18 jours à 2 kWh.
    gas_data = {
        "index": [_index("2026-06-30T22:00:00+00:00", "2026-07-18T22:00:00+00:00", 36)]
    }

    assert gas_month_total(gas_data, "2026-07") == 36.0
    assert gas_month_total(gas_data, "2026-06") == 0.0

    daily = gas_daily_values(gas_data)
    assert len(daily) == 18
    assert all(value == 2.0 for value in daily.values())


def test_daily_series_falls_back_to_monthly_buckets() -> None:
    """Sans relevé quotidien, le bucket mensuel est étalé sur ses jours."""
    gas_data = {
        "monthly": [
            {
                "startAt": "2026-06-01T00:00:00+02:00",
                "endAt": "2026-07-01T00:00:00+02:00",
                "value": "30",
            }
        ]
    }

    daily = gas_daily_values(gas_data)

    assert len(daily) == 30
    assert all(value == 1.0 for value in daily.values())


def test_zero_days_are_kept_and_null_ignored() -> None:
    """Un jour mesuré à 0 est une donnée ; un relevé sans valeur n'en est pas une."""
    gas_data = {
        "daily": [
            {"startAt": "2026-08-01T02:00:00+02:00", "value": None},
            {"startAt": "2026-08-02T02:00:00+02:00", "value": "0E-18"},
            {"startAt": "2026-08-03T02:00:00+02:00", "value": "1.25"},
        ]
    }

    assert gas_daily_values(gas_data) == {
        dt_util.parse_datetime("2026-08-02T00:00:00+02:00"): 0.0,
        dt_util.parse_datetime("2026-08-03T00:00:00+02:00"): 1.25,
    }
    # Les zéros ne changent pas la somme du mois.
    assert gas_month_total(gas_data, "2026-08") == 1.25


def test_daily_series_is_contiguous_with_zero_days() -> None:
    """Sans trou, l'import de statistiques retrouve sa branche contiguë."""
    gas_data = {
        "daily": [
            {"startAt": f"2026-08-{day:02d}T02:00:00+02:00", "value": value}
            for day, value in ((1, "1.5"), (2, "0E-18"), (3, "0E-18"), (4, "2.5"))
        ]
    }

    days = sorted(gas_daily_values(gas_data))

    assert len(days) == (days[-1] - days[0]).days + 1


def test_all_zero_daily_falls_back_to_monthly() -> None:
    """Une série quotidienne entièrement nulle laisse la main au cumul mensuel."""
    gas_data = {
        "daily": [
            {"startAt": "2026-08-01T02:00:00+02:00", "value": "0E-18"},
            {"startAt": "2026-08-02T02:00:00+02:00", "value": "0E-18"},
        ],
        "monthly": [
            {
                "startAt": "2026-08-01T00:00:00+02:00",
                "endAt": "2026-09-01T00:00:00+02:00",
                "value": "31",
            }
        ],
    }

    daily = gas_daily_values(gas_data)

    assert len(daily) == 31
    assert all(value == 1.0 for value in daily.values())


def test_daily_series_layers_monthly_then_daily() -> None:
    """Les mesures quotidiennes remplacent l'estimation, sans trouer la série."""
    gas_data = {
        "monthly": [
            {
                "startAt": "2026-08-01T00:00:00+02:00",
                "endAt": "2026-09-01T00:00:00+02:00",
                "value": "31",
            }
        ],
        "daily": [
            {"startAt": "2026-08-03T02:00:00+02:00", "value": "5"},
            {"startAt": "2026-08-04T02:00:00+02:00", "value": "0E-18"},
        ],
    }

    daily = gas_daily_values(gas_data)
    days = sorted(daily)

    assert len(days) == (days[-1] - days[0]).days + 1
    assert daily[dt_util.parse_datetime("2026-08-03T00:00:00+02:00")] == 5.0
    assert daily[dt_util.parse_datetime("2026-08-04T00:00:00+02:00")] == 0.0
    # Les jours sans mesure gardent le prorata du cumul mensuel.
    assert daily[dt_util.parse_datetime("2026-08-01T00:00:00+02:00")] == 1.0


def test_daily_series_stops_at_last_measured_day() -> None:
    """Rien n'est extrapolé après la dernière mesure : GrDF publie en retard."""
    gas_data = {
        "monthly": [
            {
                "startAt": "2026-08-01T00:00:00+02:00",
                "endAt": "2026-09-01T00:00:00+02:00",
                "value": "31",
            }
        ],
        "daily": [{"startAt": "2026-08-03T02:00:00+02:00", "value": "5"}],
    }

    assert max(gas_daily_values(gas_data)) == dt_util.parse_datetime(
        "2026-08-03T00:00:00+02:00"
    )


def test_monthly_bucket_without_end_at_covers_single_day() -> None:
    """Filet si l'API cesse de renvoyer endAt : le cumul retombe sur un jour."""
    gas_data = {"monthly": [_monthly("2026-08-01T00:00:00+02:00", "31")]}

    assert gas_daily_values(gas_data) == {
        dt_util.parse_datetime("2026-08-01T00:00:00+02:00"): 31.0
    }


def _make_coordinator(
    gas_points: list[dict[str, Any]],
    monthly: list[dict[str, Any]],
    index: list[dict[str, Any]],
) -> OctopusFrenchDataUpdateCoordinator:
    """Coordinator instrumenté, sans l'init lourd de DataUpdateCoordinator."""
    coordinator = OctopusFrenchDataUpdateCoordinator.__new__(
        OctopusFrenchDataUpdateCoordinator
    )
    coordinator.account_number = "ACC-123"

    api_client = AsyncMock()
    api_client.get_account_data.return_value = {
        "account_id": "PROP-1",
        "account_number": "ACC-123",
        "supply_points": {"electricity": [], "gas": gas_points},
        "agreements": [],
        "ledgers": {},
    }

    async def _readings(
        property_id: str, start: str, end: str, meter_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        if kwargs.get("reading_frequency") == "MONTH_INTERVAL":
            return [dict(reading, prm=meter_id) for reading in monthly]
        return []

    async def _gas_readings(
        account_number: str, pce_ref: str, start: str, end: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [dict(reading, prm=pce_ref) for reading in index]

    api_client.get_energy_readings.side_effect = _readings
    api_client.get_gas_readings.side_effect = _gas_readings
    api_client.get_all_payment_requests.return_value = {}
    coordinator.api_client = api_client
    return coordinator


async def test_gas_falls_back_to_gas_reading_when_measurements_empty() -> None:
    """Sans bucket dans `measurements`, les relevés d'index prennent le relais."""
    coordinator = _make_coordinator(
        [{"prm": PCE_A, "property_id": "PROP-1"}],
        monthly=[],
        index=[_index("2026-06-30T22:00:00+00:00", "2026-07-18T22:00:00+00:00", 36)],
    )

    result = await coordinator._fetch_all_data()

    gas_data = result["gas_by_pce"][PCE_A]
    assert gas_data["source"] == "gasReading"
    assert len(gas_data["index"]) == 1
    coordinator.api_client.get_gas_readings.assert_awaited_once()


async def test_gas_prefers_measurements_when_available() -> None:
    """Avec des buckets mensuels, `gasReading` n'est pas interrogée."""
    coordinator = _make_coordinator(
        [{"prm": PCE_A, "property_id": "PROP-1"}],
        monthly=[_monthly("2026-08-01T00:00:00+02:00", "22.0000")],
        index=[],
    )

    result = await coordinator._fetch_all_data()

    gas_data = result["gas_by_pce"][PCE_A]
    assert gas_data["source"] == "measurements"
    coordinator.api_client.get_gas_readings.assert_not_awaited()
    # La clé historique reste alimentée pour les diagnostics.
    assert result["gas"] == gas_data["monthly"]


async def test_gas_warns_when_every_source_is_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Une absence totale de relevé doit laisser une trace (cœur de l'issue #79)."""
    coordinator = _make_coordinator(
        [{"prm": PCE_A, "property_id": "PROP-1"}], monthly=[], index=[]
    )

    with caplog.at_level(logging.WARNING):
        result = await coordinator._fetch_all_data()

    assert result["gas_by_pce"][PCE_A]["source"] is None
    assert f"No gas reading returned for PCE {PCE_A}" in caplog.text


async def test_gas_readings_are_scoped_per_pce() -> None:
    """Chaque PCE porte ses propres relevés, pas ceux du premier compteur."""
    coordinator = _make_coordinator(
        [
            {"prm": PCE_A, "property_id": "PROP-1"},
            {"prm": PCE_B, "property_id": "PROP-2"},
        ],
        monthly=[_monthly("2026-08-01T00:00:00+02:00", "22.0000")],
        index=[],
    )

    result = await coordinator._fetch_all_data()

    by_pce = result["gas_by_pce"]
    assert set(by_pce) == {PCE_A, PCE_B}
    assert by_pce[PCE_A]["monthly"][0]["prm"] == PCE_A
    assert by_pce[PCE_B]["monthly"][0]["prm"] == PCE_B


def _make_sensor(key: str, data: dict[str, Any]) -> OctopusGasSensor:
    """Capteur gaz monté sur un `coordinator.data` minimal."""
    sensor = OctopusGasSensor.__new__(OctopusGasSensor)
    sensor.coordinator = SimpleNamespace(data=data, statistics_importer=None)
    sensor._pce_ref = PCE_A
    sensor._sensor_config = SensorEntityDescription(key=key)
    sensor._current_month = "2026-08"
    sensor._get_current_month = lambda: "2026-08"
    return sensor


def _gas_sensor_data(gas_by_pce: dict[str, Any], price_ttc: float = 0.1022) -> dict:
    return {
        "gas_by_pce": gas_by_pce,
        "gas": [],
        "supply_points": {"gas": [{"prm": PCE_A}]},
        "agreements": [
            {
                "prm": PCE_A,
                "is_active": True,
                "tariffs": {"consumption": {"base": {"price_ttc": price_ttc}}},
            }
        ],
    }


def test_sensor_consumption_reads_its_own_pce() -> None:
    """Le capteur lit le bucket de SON PCE."""
    data = _gas_sensor_data(
        {
            PCE_A: {"monthly": [_monthly("2026-08-01T00:00:00+02:00", "22.0000")]},
            PCE_B: {"monthly": [_monthly("2026-08-01T00:00:00+02:00", "999")]},
        }
    )

    assert _make_sensor("consumption", data)._compute_native_value() == 22.0


def test_sensor_cost_derives_from_base_rate() -> None:
    """Le coût suit la consommation du mois au tarif TTC du taux `base`."""
    data = _gas_sensor_data(
        {PCE_A: {"monthly": [_monthly("2026-08-01T00:00:00+02:00", "22.0000")]}}
    )

    assert _make_sensor("cost", data)._compute_native_value() == round(22.0 * 0.1022, 2)


def test_sensor_falls_back_to_legacy_gas_key() -> None:
    """Un `coordinator.data` sans `gas_by_pce` reste exploitable."""
    data = _gas_sensor_data({})
    data["gas"] = [_monthly("2026-08-01T00:00:00+02:00", "22.0000")]

    assert _make_sensor("consumption", data)._compute_native_value() == 22.0


def test_sensor_exposes_source_attribute() -> None:
    """La source des relevés est exposée pour le diagnostic."""
    data = _gas_sensor_data(
        {
            PCE_A: {
                "monthly": [_monthly("2026-08-01T00:00:00+02:00", "22.0000")],
                "daily": [{"startAt": "2026-08-01T02:00:00+02:00", "value": "1.5"}],
                "source": "measurements",
            }
        }
    )

    attributes = _make_sensor("consumption", data)._compute_attributes()

    assert attributes["source"] == "measurements"
    assert attributes["readings_count"] == 2


def _daily(start_at: str, value: str) -> dict[str, Any]:
    """Relevé DAY_INTERVAL tel que renvoyé par `property.measurements`."""
    return {"startAt": start_at, "value": value}


def test_latest_reading_prefers_daily_readings() -> None:
    """Avec des relevés quotidiens, l'état est celui du jour le plus récent."""
    data = _gas_sensor_data(
        {
            PCE_A: {
                "daily": [
                    _daily("2026-08-22T02:00:00+02:00", "0.33"),
                    _daily("2026-08-23T02:00:00+02:00", "1.88"),
                ],
                "monthly": [_monthly("2026-08-01T00:00:00+02:00", "22.0000")],
                "source": "measurements",
            }
        }
    )

    sensor = _make_sensor("gas_latest_reading", data)

    assert sensor._compute_native_value() == 1.88
    assert sensor._compute_attributes()["source"] == "daily"


def test_latest_reading_ignores_reading_order() -> None:
    """L'API ne garantit pas l'ordre : le relevé le plus récent doit gagner."""
    data = _gas_sensor_data(
        {
            PCE_A: {
                "daily": [
                    _daily("2026-08-23T02:00:00+02:00", "1.88"),
                    _daily("2026-08-21T02:00:00+02:00", "9.99"),
                    _daily("2026-08-22T02:00:00+02:00", "0.33"),
                ]
            }
        }
    )

    assert _make_sensor("gas_latest_reading", data)._compute_native_value() == 1.88


def test_latest_reading_falls_back_to_index_readings() -> None:
    """Sans relevé quotidien, le dernier relevé d'index prend le relais."""
    data = _gas_sensor_data(
        {
            PCE_A: {
                "index": [
                    _index(
                        "2026-06-30T22:00:00+00:00", "2026-07-18T22:00:00+00:00", 22
                    ),
                    _index(
                        "2026-07-31T22:00:00+00:00", "2026-08-18T22:00:00+00:00", 11
                    ),
                ],
                "source": "gasReading",
            }
        }
    )

    sensor = _make_sensor("gas_latest_reading", data)

    assert sensor._compute_native_value() == 11.0
    assert sensor._compute_attributes()["source"] == "index"


def test_latest_reading_is_none_without_readings() -> None:
    """Sans aucun relevé, le capteur reste vide : 0 kWh serait un faux relevé."""
    data = _gas_sensor_data({PCE_A: {"monthly": [], "daily": [], "index": []}})

    sensor = _make_sensor("gas_latest_reading", data)

    assert sensor._compute_native_value() is None
    assert sensor._compute_attributes() == {}


def test_latest_reading_attributes() -> None:
    """Dates, coût et index du compteur accompagnent la valeur."""
    reading = _index("2026-07-31T22:00:00+00:00", "2026-08-18T22:00:00+00:00", 22)
    reading |= {"indexStartValue": 4609, "indexEndValue": 4611}
    data = _gas_sensor_data({PCE_A: {"index": [reading]}}, price_ttc=0.1188)

    attributes = _make_sensor("gas_latest_reading", data)._compute_attributes()

    assert attributes["date_releve"] == "2026-07-31"
    assert attributes["date_fin"] == "2026-08-18"
    assert attributes["cout_euro"] == round(22 * 0.1188, 2)
    assert attributes["index_debut"] == 4609
    assert attributes["index_fin"] == 4611


def test_latest_reading_omits_meter_index_for_measurements() -> None:
    """Les relevés `measurements` ne portent pas d'index compteur."""
    data = _gas_sensor_data(
        {PCE_A: {"daily": [_daily("2026-08-23T02:00:00+02:00", "1.88")]}}
    )

    attributes = _make_sensor("gas_latest_reading", data)._compute_attributes()

    assert "index_debut" not in attributes
    assert attributes["date_fin"] is None


async def test_statistics_are_imported_for_every_pce() -> None:
    """Les statistiques long-terme couvrent chaque PCE, pas seulement le premier."""
    coordinator = SimpleNamespace(
        data={
            "electricity_by_prm": {},
            "agreements": [
                {
                    "prm": pce,
                    "is_active": True,
                    "tariffs": {"consumption": {"base": {"price_ttc": 0.1}}},
                }
                for pce in (PCE_A, PCE_B)
            ],
            "gas_by_pce": {
                PCE_A: {
                    "daily": [{"startAt": "2026-08-01T02:00:00+02:00", "value": "10"}]
                },
                PCE_B: {
                    "daily": [{"startAt": "2026-08-01T02:00:00+02:00", "value": "20"}]
                },
            },
            "supply_points": {"gas": [{"prm": PCE_A}, {"prm": PCE_B}]},
        }
    )
    importer = OctopusStatisticsImporter(MagicMock(), coordinator)
    imported: dict[str, dict] = {}

    async def _capture(statistic_id: str, daily_values: dict, **kwargs: Any) -> None:
        imported[statistic_id] = daily_values

    importer._async_import_statistic = _capture

    await importer._async_import_gas()

    assert set(imported) == {
        f"octopus_french:{PCE_A}_consumption",
        f"octopus_french:{PCE_A}_cost",
        f"octopus_french:{PCE_B}_consumption",
        f"octopus_french:{PCE_B}_cost",
    }
    assert list(imported[f"octopus_french:{PCE_A}_consumption"].values()) == [10.0]
    assert list(imported[f"octopus_french:{PCE_B}_cost"].values()) == [
        pytest.approx(2.0)
    ]
