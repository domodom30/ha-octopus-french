"""Tests pour OctopusCurrentRateSensor (tarif HP/HC en cours, contrats HPHC)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.const import CURRENCY_EURO

from custom_components.octopus_french.sensors.electricity import (
    OctopusCurrentRateSensor,
)


def _make_coordinator(
    consumption: dict,
    prm_id: str = "TEST_PRM",
) -> MagicMock:
    """Construit un coordinateur factice avec un contrat actif et ses tarifs."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {
        "agreements": [
            {
                "prm": prm_id,
                "is_active": True,
                "tariffs": {"consumption": consumption},
            }
        ],
        "supply_points": {"electricity": []},
    }
    return coordinator


def _make_sensor(
    coordinator: MagicMock,
    prm_id: str = "TEST_PRM",
) -> OctopusCurrentRateSensor:
    """Instancie le capteur sans passer par HA."""
    config = SensorEntityDescription(
        key="current_rate",
        native_unit_of_measurement=f"{CURRENCY_EURO}/kWh",
        suggested_display_precision=4,
    )
    sensor = OctopusCurrentRateSensor.__new__(OctopusCurrentRateSensor)
    sensor.coordinator = coordinator
    sensor._prm_id = prm_id
    sensor._sensor_config = config
    return sensor


_RANGES_SCHEDULE = {
    "type": "HC",
    "ranges": [{"start": "22:00", "end": "06:00"}],
    "total_hours": 8.0,
    "range_count": 1,
    "source": "contract",
}

_NO_SCHEDULE = {
    "type": None,
    "ranges": [],
    "total_hours": 0.0,
    "range_count": 0,
    "source": "none",
}


class TestCurrentRateSensorSingleSeason:
    """Contrat HPHC classique (une seule saison)."""

    def test_returns_peak_rate_during_hp(self) -> None:
        """Hors plage HC → tarif heures pleines."""
        coordinator = _make_coordinator(
            {"heures_pleines": {"price_ttc": 0.1807}}, prm_id="TEST_PRM"
        )
        sensor = _make_sensor(coordinator)

        with (
            patch.object(sensor, "_resolve_hc_schedule", return_value=_RANGES_SCHEDULE),
            patch.object(sensor, "_is_currently_hc", return_value=False),
            patch(
                "custom_components.octopus_french.sensors.electricity.resolve_two_season",
                return_value=None,
            ),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.1807)

    def test_returns_off_peak_rate_during_hc(self) -> None:
        """En plage HC → tarif heures creuses."""
        coordinator = _make_coordinator(
            {"heures_creuses": {"price_ttc": 0.1387}}, prm_id="TEST_PRM"
        )
        sensor = _make_sensor(coordinator)

        with (
            patch.object(sensor, "_resolve_hc_schedule", return_value=_RANGES_SCHEDULE),
            patch.object(sensor, "_is_currently_hc", return_value=True),
            patch(
                "custom_components.octopus_french.sensors.electricity.resolve_two_season",
                return_value=None,
            ),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.1387)

    def test_falls_back_to_base_rate_without_hc_schedule(self) -> None:
        """Sans plage HC (contrat BASE) → tarif base."""
        coordinator = _make_coordinator({"base": {"price_ttc": 0.2016}})
        sensor = _make_sensor(coordinator)

        with patch.object(sensor, "_resolve_hc_schedule", return_value=_NO_SCHEDULE):
            assert sensor._compute_native_value() == pytest.approx(0.2016)

    def test_extra_attributes_contain_period_and_source(self) -> None:
        """Les attributs exposent la période HP/HC et la source des horaires."""
        coordinator = _make_coordinator({"heures_creuses": {"price_ttc": 0.1387}})
        sensor = _make_sensor(coordinator)

        with (
            patch.object(sensor, "_resolve_hc_schedule", return_value=_RANGES_SCHEDULE),
            patch.object(sensor, "_is_currently_hc", return_value=True),
        ):
            attrs = sensor._compute_attributes()

        assert attrs["period_type"] == "HC"
        assert attrs["hc_source"] == "contract"
        assert attrs["prm_id"] == "TEST_PRM"


class TestCurrentRateSensorTwoSeason:
    """Contrat HPHC deux saisons : le bon registre saisonnier doit être choisi."""

    def test_summer_off_peak(self) -> None:
        coordinator = _make_coordinator(
            {"heures_creuses_ete": {"price_ttc": 0.15}}
        )
        sensor = _make_sensor(coordinator)

        with (
            patch.object(sensor, "_resolve_hc_schedule", return_value=_RANGES_SCHEDULE),
            patch.object(sensor, "_is_currently_hc", return_value=True),
            patch(
                "custom_components.octopus_french.sensors.electricity.resolve_two_season",
                return_value="ETE",
            ),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.15)

    def test_winter_peak(self) -> None:
        coordinator = _make_coordinator(
            {"heures_pleines_hiver": {"price_ttc": 0.22}}
        )
        sensor = _make_sensor(coordinator)

        with (
            patch.object(sensor, "_resolve_hc_schedule", return_value=_RANGES_SCHEDULE),
            patch.object(sensor, "_is_currently_hc", return_value=False),
            patch(
                "custom_components.octopus_french.sensors.electricity.resolve_two_season",
                return_value="HIVER",
            ),
        ):
            assert sensor._compute_native_value() == pytest.approx(0.22)


class TestCurrentRateSensorSetup:
    """Vérifie que la plateforme crée le capteur pour les bons types de contrat."""

    def test_description_registered(self) -> None:
        """La description `current_rate` existe et est désactivée par défaut."""
        from custom_components.octopus_french.sensors.descriptions import (
            ELECTRICITY_SENSORS,
        )

        description = next(s for s in ELECTRICITY_SENSORS if s.key == "current_rate")
        assert description.entity_registry_enabled_default is False
