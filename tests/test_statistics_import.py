"""Tests pour l'import idempotent des statistiques long-terme (électricité).

Vérifie que la fenêtre de récupération chevauchante du coordinator ne fait pas
double-compter un jour dans la somme cumulée — le bug qui corrompait la
consommation journalière affichée par le tableau de bord Énergie.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import zoneinfo

from custom_components.octopus_french.sensors import electricity
from custom_components.octopus_french.sensors.electricity import (
    OctopusElectricitySensor,
)
import pytest

from homeassistant.util import dt as dt_util

PARIS = zoneinfo.ZoneInfo("Europe/Paris")
STAT_ID = "octopus_french:PRM1_energy_peak_hours"


@pytest.fixture
def paris_tz():
    """Force le fuseau local sur Europe/Paris pour la durée du test."""
    original = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(PARIS)
    yield
    dt_util.set_default_time_zone(original)


def _paris_day(day: int) -> datetime:
    """Minuit local (Europe/Paris) pour un jour de juin 2026."""
    return datetime(2026, 6, day, tzinfo=PARIS)


def _reading(start_at: str, value: float, label: str = "HEURES_PLEINES") -> dict:
    """Construire un nœud de mesure DAY_INTERVAL minimal."""
    return {
        "startAt": start_at,
        "metaData": {"statistics": [{"label": label, "value": value}]},
    }


def _make_sensor(key: str, readings: list[dict]) -> OctopusElectricitySensor:
    """Instancier le capteur sans passer par l'init lourd de CoordinatorEntity."""
    sensor = OctopusElectricitySensor.__new__(OctopusElectricitySensor)
    sensor._prm_id = "PRM1"
    sensor._sensor_config = SimpleNamespace(key=key)
    sensor.entity_id = f"sensor.octopus_{key}"
    sensor._attr_unique_id = f"uid_{key}"
    sensor._attr_native_unit_of_measurement = "kWh"
    sensor._current_month = None
    sensor._last_imported_date = None
    sensor._import_in_progress = False
    sensor.hass = MagicMock()
    sensor.coordinator = SimpleNamespace(data={"electricity": {"readings": readings}})
    return sensor


class _FakeStatsStore:
    """Recorder en mémoire : upsert par `start` + get_last_statistics."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[float, dict]] = {}

    async def executor(self, func, *args):
        # get_last_statistics(hass, 1, sid, ...) ou statistics_during_period(hass, start, end, {sid}, ...)
        if func.__name__ == "statistics_during_period":
            return self._during_period(*args)
        statistic_id = args[2]
        rows = self.rows.get(statistic_id)
        if not rows:
            return {}
        last = max(rows.values(), key=lambda r: r["start"])
        return {statistic_id: [{"sum": last["sum"], "start": last["start"]}]}

    def _during_period(self, hass, start, end, sid_set, period, units, types):
        statistic_id = next(iter(sid_set))
        rows = self.rows.get(statistic_id)
        if not rows:
            return {}
        end_ts = end.timestamp()
        result = [
            {"start": r["start"], "sum": r["sum"]}
            for r in sorted(rows.values(), key=lambda r: r["start"])
            if r["start"] < end_ts
        ]
        return {statistic_id: result} if result else {}

    def prefill(self, statistic_id: str, entries: list[tuple[datetime, float, float]]) -> None:
        """Injecter des lignes (start, state, sum) — pour simuler des données déjà écrites."""
        bucket = self.rows.setdefault(statistic_id, {})
        for day, state, total in entries:
            ts = day.timestamp()
            bucket[ts] = {"start": ts, "state": state, "sum": total}

    def add(self, hass, metadata, statistics) -> None:
        bucket = self.rows.setdefault(metadata["statistic_id"], {})
        for stat in statistics:
            ts = stat["start"].timestamp()
            bucket[ts] = {"start": ts, "state": stat["state"], "sum": stat["sum"]}

    def states(self, statistic_id: str) -> list[float]:
        rows = sorted(self.rows[statistic_id].values(), key=lambda r: r["start"])
        return [round(r["state"], 6) for r in rows]

    def changes(self, statistic_id: str) -> list[float]:
        """Conso/jour telle que dérivée par le dashboard = diff des sommes."""
        rows = sorted(self.rows[statistic_id].values(), key=lambda r: r["start"])
        changes: list[float] = []
        prev: float | None = None
        for row in rows:
            changes.append(round(row["sum"] - (prev or 0.0), 6))
            prev = row["sum"]
        return changes


async def _run_import(sensor: OctopusElectricitySensor, store: _FakeStatsStore) -> None:
    fake_instance = SimpleNamespace(async_add_executor_job=store.executor)
    with (
        patch.object(electricity, "get_instance", return_value=fake_instance),
        patch.object(
            electricity, "async_add_external_statistics", side_effect=store.add
        ),
    ):
        await sensor._async_import_statistics()


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_overlapping_window_does_not_double_count() -> None:
    """Réimporter une fenêtre chevauchante n'ajoute aucun jour deux fois."""
    store = _FakeStatsStore()

    first = [
        _reading("2026-06-14T00:00:00+02:00", 5.0),
        _reading("2026-06-15T00:00:00+02:00", 6.0),
        _reading("2026-06-16T00:00:00+02:00", 7.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", first), store)

    # Deuxième cycle : 15 et 16 reviennent (un avec un offset UTC différent), 17 nouveau.
    second = [
        _reading("2026-06-15T00:00:00+02:00", 6.0),
        _reading("2026-06-15T22:00:00+00:00", 7.0),  # = 16 juin Paris, offset +00:00
        _reading("2026-06-17T00:00:00+02:00", 8.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", second), store)

    # Un seul point par jour, valeurs réelles préservées, et conso/jour = valeur du jour.
    assert store.states(STAT_ID) == [5.0, 6.0, 7.0, 8.0]
    assert store.changes(STAT_ID) == [5.0, 6.0, 7.0, 8.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_same_day_mixed_offsets_collapsed() -> None:
    """Deux relevés du même jour calendaire (offsets différents) = un seul point."""
    store = _FakeStatsStore()

    readings = [
        _reading("2026-06-16T00:00:00+02:00", 7.0),
        _reading("2026-06-15T22:00:00+00:00", 7.0),  # même jour Paris
    ]
    await _run_import(_make_sensor("energy_peak_hours", readings), store)

    assert store.states(STAT_ID) == [7.0]
    assert store.changes(STAT_ID) == [7.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_reimport_same_data_is_noop() -> None:
    """Rejouer exactement les mêmes readings ne modifie pas les sommes."""
    store = _FakeStatsStore()

    readings = [
        _reading("2026-06-14T00:00:00+02:00", 5.0),
        _reading("2026-06-15T00:00:00+02:00", 6.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", readings), store)
    await _run_import(_make_sensor("energy_peak_hours", list(readings)), store)

    assert store.states(STAT_ID) == [5.0, 6.0]
    assert store.changes(STAT_ID) == [5.0, 6.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_rewrite_heals_previously_doubled_sums() -> None:
    """Des sommes déjà doublées (bug <= 3.2.5) sont réécrites correctement (issue #46).

    La fenêtre contiguë est réécrite depuis l'ancre : le dashboard, qui affiche les
    diffs de sommes, retrouve les bonnes barres journalières.
    """
    store = _FakeStatsStore()
    # Sommes corrompues : cumul gonflé par un double-comptage de la fenêtre.
    store.prefill(
        STAT_ID,
        [
            (_paris_day(14), 5.0, 5.0),
            (_paris_day(15), 6.0, 17.0),
            (_paris_day(16), 7.0, 30.0),
        ],
    )

    readings = [
        _reading("2026-06-14T00:00:00+02:00", 5.0),
        _reading("2026-06-15T00:00:00+02:00", 6.0),
        _reading("2026-06-16T00:00:00+02:00", 7.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", readings), store)

    assert store.changes(STAT_ID) == [5.0, 6.0, 7.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_gap_in_window_falls_back_to_append_only() -> None:
    """Une fenêtre trouée ne réécrit pas : les jours voisins déjà écrits sont préservés."""
    store = _FakeStatsStore()
    # Un jour central déjà présent (cumul 11 = 5 + 6).
    store.prefill(STAT_ID, [(_paris_day(15), 6.0, 11.0)])

    # Fenêtre non contiguë : 14 et 16, trou le 15.
    readings = [
        _reading("2026-06-14T00:00:00+02:00", 5.0),
        _reading("2026-06-16T00:00:00+02:00", 7.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", readings), store)

    # Append-only : le 15 (déjà importé) reste intact, le 16 s'empile dessus.
    rows = store.rows[STAT_ID]
    assert rows[_paris_day(15).timestamp()]["sum"] == 11.0
    assert rows[_paris_day(16).timestamp()]["sum"] == 18.0
    assert _paris_day(14).timestamp() not in rows


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_mixed_offsets_across_cycles_do_not_double() -> None:
    """Régression 3.2.5 : même instant réémis avec un offset UTC différent, sans doubler."""
    store = _FakeStatsStore()

    await _run_import(
        _make_sensor(
            "energy_peak_hours", [_reading("2026-06-16T00:00:00+02:00", 7.0)]
        ),
        store,
    )
    # 2e cycle : le 16 revient en offset +00:00 (= même instant Paris) + le 17 nouveau.
    second = [
        _reading("2026-06-15T22:00:00+00:00", 7.0),
        _reading("2026-06-17T00:00:00+02:00", 8.0),
    ]
    await _run_import(_make_sensor("energy_peak_hours", second), store)

    assert store.states(STAT_ID) == [7.0, 8.0]
    assert store.changes(STAT_ID) == [7.0, 8.0]


@pytest.mark.usefixtures("paris_tz")
def test_coordinator_update_always_schedules_import() -> None:
    """Chaque mise à jour du coordinator replanifie l'import (issue #45).

    Le verrou « one-shot » figeait les statistiques après le premier import ;
    l'import étant idempotent, il doit désormais tourner à chaque cycle.
    """
    sensor = _make_sensor("energy_peak_hours", [])
    sensor._async_import_statistics = MagicMock(return_value=None)
    sensor.async_write_ha_state = MagicMock()

    sensor._handle_coordinator_update()
    sensor._handle_coordinator_update()

    assert sensor._async_import_statistics.call_count == 2
    assert sensor.hass.async_create_task.call_count == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_reentrant_import_is_skipped() -> None:
    """Un import lancé pendant qu'un autre est en cours sort sans rien écrire."""
    store = _FakeStatsStore()
    sensor = _make_sensor(
        "energy_peak_hours", [_reading("2026-06-14T00:00:00+02:00", 5.0)]
    )
    sensor._import_in_progress = True

    await _run_import(sensor, store)

    assert STAT_ID not in store.rows
    assert sensor._import_in_progress is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_import_resets_in_progress_flag() -> None:
    """Le garde de ré-entrance est bien remis à False après un import."""
    store = _FakeStatsStore()
    sensor = _make_sensor(
        "energy_peak_hours", [_reading("2026-06-14T00:00:00+02:00", 5.0)]
    )

    await _run_import(sensor, store)

    assert sensor._import_in_progress is False
    assert store.states(STAT_ID) == [5.0]


@pytest.mark.usefixtures("paris_tz")
@pytest.mark.parametrize(
    ("key", "resets_monthly"),
    [
        ("energy_peak_hours", True),
        ("energy_off_peak_hours", True),
        ("cost_base", True),
        ("subscription", True),
        ("contract", False),
        ("subscribed_power", False),
        ("rate_base", False),
    ],
)
def test_last_reset_only_on_monthly_total_sensors(
    key: str, resets_monthly: bool
) -> None:
    """Les capteurs de total mensuel exposent last_reset = 1er du mois (minuit local).

    Sans ça, leur remise à 0 le 1er produit un `change` négatif dans les
    statistiques TOTAL auto-générées par HA.
    """
    sensor = _make_sensor(key, [])

    if resets_monthly:
        expected = dt_util.start_of_local_day().replace(day=1)
        assert sensor.last_reset == expected
        assert sensor.last_reset.day == 1
        assert (sensor.last_reset.hour, sensor.last_reset.minute) == (0, 0)
        assert sensor.last_reset.tzinfo is not None
    else:
        assert sensor.last_reset is None
