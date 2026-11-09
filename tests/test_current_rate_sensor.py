"""Tests pour OctopusCurrentRateSensor (tarif HP/HC en cours, contrats HPHC)."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.octopus_french.sensors.descriptions import ELECTRICITY_SENSORS
from custom_components.octopus_french.sensors.electricity import (
    OctopusCurrentRateSensor,
)
from custom_components.octopus_french.utils import is_time_in_range

PRM_ID = "TEST_PRM"

CURRENT_RATE_DESCRIPTION = next(
    description
    for description in ELECTRICITY_SENSORS
    if description.key == "current_rate"
)

SINGLE_SEASON_RATES = {
    "heures_pleines": {"price_ttc": 0.1807},
    "heures_creuses": {"price_ttc": 0.1387},
}

TWO_SEASON_RATES = {
    "heures_pleines_ete": {"price_ttc": 0.17},
    "heures_creuses_ete": {"price_ttc": 0.15},
    "heures_pleines_hiver": {"price_ttc": 0.22},
    "heures_creuses_hiver": {"price_ttc": 0.16},
}


def _coordinator_data(
    consumption: dict[str, Any], off_peak_label: str | None
) -> dict[str, Any]:
    """Return coordinator data with one active agreement and its Linky meter."""
    return {
        "agreements": [
            {
                "prm": PRM_ID,
                "is_active": True,
                "tariffs": {"consumption": consumption},
            }
        ],
        "supply_points": {
            "electricity": [{"prm": PRM_ID, "offPeakLabel": off_peak_label}]
        },
    }


def _sensor_at(data: dict[str, Any], now: datetime) -> OctopusCurrentRateSensor:
    """Return a sensor whose state is computed at the given local time."""
    coordinator = MagicMock()
    coordinator.data = data
    with patch(
        "custom_components.octopus_french.sensors.electricity.dt_util.now",
        return_value=now,
    ):
        return OctopusCurrentRateSensor(coordinator, PRM_ID, CURRENT_RATE_DESCRIPTION)


@pytest.mark.parametrize(
    ("current", "start", "end", "expected"),
    [
        pytest.param(time(22, 0), "22:00", "06:00", True, id="overnight-start"),
        pytest.param(time(5, 59), "22:00", "06:00", True, id="overnight-last-minute"),
        pytest.param(time(6, 0), "22:00", "06:00", False, id="overnight-end-excluded"),
        pytest.param(time(21, 59), "22:00", "06:00", False, id="overnight-before"),
        pytest.param(time(12, 30), "12:30", "14:30", True, id="daytime-start"),
        pytest.param(time(14, 30), "12:30", "14:30", False, id="daytime-end-excluded"),
        pytest.param(time(23, 59), "22:00", "00:00", True, id="until-midnight"),
        pytest.param(time(0, 0), "22:00", "00:00", False, id="midnight-excluded"),
        pytest.param(time(3, 0), "invalid", "06:00", False, id="unparsable"),
    ],
)
def test_is_time_in_range(current: time, start: str, end: str, expected: bool) -> None:
    """La fin d'une plage HC est exclue : l'heure de fin est déjà en HP."""
    assert is_time_in_range(current, start, end) is expected


@pytest.mark.parametrize(
    ("consumption", "now", "expected_rate", "expected_period"),
    [
        pytest.param(
            SINGLE_SEASON_RATES,
            datetime(2026, 7, 15, 23, 0),
            0.1387,
            "HC",
            id="single-season-off-peak",
        ),
        pytest.param(
            SINGLE_SEASON_RATES,
            datetime(2026, 7, 15, 6, 0),
            0.1807,
            "HP",
            id="single-season-peak-at-range-end",
        ),
        pytest.param(
            TWO_SEASON_RATES,
            datetime(2026, 7, 15, 23, 0),
            0.15,
            "HC",
            id="summer-off-peak",
        ),
        pytest.param(
            TWO_SEASON_RATES,
            datetime(2026, 7, 15, 12, 0),
            0.17,
            "HP",
            id="summer-peak",
        ),
        pytest.param(
            TWO_SEASON_RATES,
            datetime(2026, 1, 15, 5, 59),
            0.16,
            "HC",
            id="winter-off-peak",
        ),
        pytest.param(
            TWO_SEASON_RATES,
            datetime(2026, 1, 15, 6, 0),
            0.22,
            "HP",
            id="winter-peak",
        ),
    ],
)
def test_current_rate_follows_period_and_season(
    consumption: dict[str, Any],
    now: datetime,
    expected_rate: float,
    expected_period: str,
) -> None:
    """Le tarif suit la plage HC (22h-6h) et, en deux saisons, la saison du jour."""
    sensor = _sensor_at(_coordinator_data(consumption, "HC (22H00-6H00)"), now)

    assert sensor.native_value == pytest.approx(expected_rate)
    assert sensor.extra_state_attributes == {
        "period_type": expected_period,
        "hc_source": "linky",
        "prm_id": PRM_ID,
    }


def test_current_rate_unknown_without_hc_schedule() -> None:
    """Sans plage HC connue, aucun tarif n'est inventé."""
    sensor = _sensor_at(
        _coordinator_data(SINGLE_SEASON_RATES, None), datetime(2026, 7, 15, 23, 0)
    )

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {
        "period_type": None,
        "hc_source": "none",
        "prm_id": PRM_ID,
    }


def test_current_rate_unknown_without_matching_rate() -> None:
    """Un contrat sans tarif HP/HC exploitable laisse l'état inconnu."""
    sensor = _sensor_at(
        _coordinator_data({}, "HC (22H00-6H00)"), datetime(2026, 7, 15, 23, 0)
    )

    assert sensor.native_value is None


def test_description_disabled_by_default() -> None:
    """Le capteur est un diagnostic désactivé par défaut."""
    assert CURRENT_RATE_DESCRIPTION.entity_registry_enabled_default is False
