"""
Tests pour l'import idempotent des statistiques long-terme (électricité).

L'import est centralisé dans OctopusStatisticsImporter (une passe par cycle de
coordinator). Vérifie que la fenêtre de récupération chevauchante ne fait pas
double-compter un jour dans la somme cumulée — le bug qui corrompait la
consommation journalière affichée par le tableau de bord Énergie — et que les
coûts privilégient le montant réel de l'API (costInclTax) sur kWh x tarif.
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.octopus_french import statistics_import
from custom_components.octopus_french.sensors.electricity import (
    OctopusElectricitySensor,
)
from custom_components.octopus_french.statistics_import import (
    OctopusStatisticsImporter,
)

PARIS = zoneinfo.ZoneInfo("Europe/Paris")
STAT_ID = "octopus_french:PRM1_energy_peak_hours"
COST_STAT_ID = "octopus_french:PRM1_cost_peak_hours"

_AGREEMENT_HP = [
    {
        "prm": "PRM1",
        "is_active": True,
        "tariffs": {"consumption": {"heures_pleines": {"price_ttc": 0.25}}},
    }
]


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


def _cost_reading(
    start_at: str,
    kwh: float | None = None,
    cents: int | None = None,
    label: str = "HEURES_PLEINES",
) -> dict:
    """Relevé avec, au choix, le montant API (centimes) et/ou la consommation."""
    stat: dict[str, Any] = {"label": label}
    if kwh is not None:
        stat["value"] = kwh
    if cents is not None:
        stat["costInclTax"] = {"estimatedAmount": cents}
    return {"startAt": start_at, "metaData": {"statistics": [stat]}}


def _make_importer(
    readings: list[dict], agreements: list[dict] | None = None
) -> OctopusStatisticsImporter:
    """Instancier l'importer sur un coordinator.data minimal."""
    coordinator = SimpleNamespace(
        data={
            "electricity_by_prm": {"PRM1": {"readings": readings}},
            "agreements": agreements or [],
            "gas": [],
            "supply_points": {"gas": []},
        }
    )
    return OctopusStatisticsImporter(MagicMock(), coordinator)


class _FakeStatsStore:
    """Recorder en mémoire : upsert par `start` + get_last_statistics."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[float, dict]] = {}

    async def executor(self, func, *args: Any):
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

    def prefill(
        self, statistic_id: str, entries: list[tuple[datetime, float, float]]
    ) -> None:
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


async def _run_import(
    importer: OctopusStatisticsImporter, store: _FakeStatsStore
) -> None:
    fake_instance = SimpleNamespace(async_add_executor_job=store.executor)
    with (
        patch.object(statistics_import, "get_instance", return_value=fake_instance),
        patch.object(
            statistics_import, "async_add_external_statistics", side_effect=store.add
        ),
    ):
        await importer.async_import_all()


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
    await _run_import(_make_importer(first), store)

    # Deuxième cycle : 15 et 16 reviennent (un avec un offset UTC différent), 17 nouveau.
    second = [
        _reading("2026-06-15T00:00:00+02:00", 6.0),
        _reading("2026-06-15T22:00:00+00:00", 7.0),  # = 16 juin Paris, offset +00:00
        _reading("2026-06-17T00:00:00+02:00", 8.0),
    ]
    await _run_import(_make_importer(second), store)

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
    await _run_import(_make_importer(readings), store)

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
    await _run_import(_make_importer(readings), store)
    await _run_import(_make_importer(list(readings)), store)

    assert store.states(STAT_ID) == [5.0, 6.0]
    assert store.changes(STAT_ID) == [5.0, 6.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_rewrite_heals_previously_doubled_sums() -> None:
    """
    Des sommes déjà doublées (bug <= 3.2.5) sont réécrites correctement (issue #46).

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
    await _run_import(_make_importer(readings), store)

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
    await _run_import(_make_importer(readings), store)

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
        _make_importer([_reading("2026-06-16T00:00:00+02:00", 7.0)]),
        store,
    )
    # 2e cycle : le 16 revient en offset +00:00 (= même instant Paris) + le 17 nouveau.
    second = [
        _reading("2026-06-15T22:00:00+00:00", 7.0),
        _reading("2026-06-17T00:00:00+02:00", 8.0),
    ]
    await _run_import(_make_importer(second), store)

    assert store.states(STAT_ID) == [7.0, 8.0]
    assert store.changes(STAT_ID) == [7.0, 8.0]


@pytest.mark.usefixtures("paris_tz")
def test_coordinator_update_always_schedules_import() -> None:
    """
    Chaque mise à jour du coordinator replanifie l'import (issue #45).

    L'import étant idempotent, le listener doit relancer une passe à chaque cycle.
    """
    importer = _make_importer([])
    importer.async_import_all = MagicMock(return_value=None)

    importer.schedule_import()
    importer.schedule_import()

    assert importer.async_import_all.call_count == 2
    assert importer.hass.async_create_task.call_count == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_reentrant_import_is_skipped() -> None:
    """Un import lancé pendant qu'un autre est en cours sort sans rien écrire."""
    store = _FakeStatsStore()
    importer = _make_importer([_reading("2026-06-14T00:00:00+02:00", 5.0)])
    importer._import_in_progress = True

    await _run_import(importer, store)

    assert STAT_ID not in store.rows
    assert importer._import_in_progress is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_import_resets_in_progress_flag() -> None:
    """Le garde de ré-entrance est bien remis à False après un import."""
    store = _FakeStatsStore()
    importer = _make_importer([_reading("2026-06-14T00:00:00+02:00", 5.0)])

    await _run_import(importer, store)

    assert importer._import_in_progress is False
    assert store.states(STAT_ID) == [5.0]
    assert importer.last_imported[STAT_ID] == _paris_day(14).isoformat()


# --------------------------------------------------------------------- coûts


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_cost_uses_api_amount_when_available() -> None:
    """Le coût importé est le montant API (centimes), pas kWh x tarif actuel."""
    store = _FakeStatsStore()
    readings = [_cost_reading("2026-06-14T00:00:00+02:00", kwh=10.0, cents=312)]

    await _run_import(_make_importer(readings, agreements=_AGREEMENT_HP), store)

    # 3.12 € (API) et non 10 x 0.25 = 2.50 € (tarif actuel).
    assert store.states(COST_STAT_ID) == [3.12]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_cost_falls_back_to_current_rate() -> None:
    """Sans costInclTax, le coût retombe sur kWh x tarif du contrat actif."""
    store = _FakeStatsStore()
    readings = [_cost_reading("2026-06-14T00:00:00+02:00", kwh=10.0)]

    await _run_import(_make_importer(readings, agreements=_AGREEMENT_HP), store)

    assert store.states(COST_STAT_ID) == [2.5]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_cost_skipped_without_amount_or_rate() -> None:
    """Ni montant API ni tarif : pas de statistique de coût (l'énergie reste importée)."""
    store = _FakeStatsStore()
    readings = [_cost_reading("2026-06-14T00:00:00+02:00", kwh=10.0)]

    await _run_import(_make_importer(readings, agreements=[]), store)

    assert COST_STAT_ID not in store.rows
    assert store.states(STAT_ID) == [10.0]


@pytest.mark.usefixtures("paris_tz")
def test_monthly_cost_display_prefers_api_amount() -> None:
    """L'état mensuel affiché suit la même logique costInclTax-d'abord."""
    current_month_day = dt_util.now().replace(day=1).strftime("%Y-%m-%dT00:00:00%z")
    sensor = _make_slim_sensor(
        "cost_peak_hours",
        [
            _cost_reading(current_month_day, kwh=10.0, cents=312),
        ],
        agreements=_AGREEMENT_HP,
    )

    assert sensor._calculate_monthly_total() == 3.12


@pytest.mark.usefixtures("paris_tz")
def test_monthly_cost_display_falls_back_to_rate() -> None:
    """Sans montant API, l'état mensuel retombe sur kWh x tarif."""
    current_month_day = dt_util.now().replace(day=1).strftime("%Y-%m-%dT00:00:00%z")
    sensor = _make_slim_sensor(
        "cost_peak_hours",
        [_cost_reading(current_month_day, kwh=10.0)],
        agreements=_AGREEMENT_HP,
    )

    assert sensor._calculate_monthly_total() == 2.5


# ------------------------------------------------------------------- sensors


def _make_slim_sensor(
    key: str, readings: list[dict], agreements: list[dict] | None = None
) -> OctopusElectricitySensor:
    """Instancier le capteur sans passer par l'init lourd de CoordinatorEntity."""
    sensor = OctopusElectricitySensor.__new__(OctopusElectricitySensor)
    sensor._prm_id = "PRM1"
    sensor._sensor_config = SimpleNamespace(key=key)
    sensor._current_month = None
    sensor.coordinator = SimpleNamespace(
        data={
            "electricity_by_prm": {"PRM1": {"readings": readings}},
            "agreements": agreements or [],
        }
    )
    return sensor


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
    """
    Les capteurs de total mensuel exposent last_reset = 1er du mois (minuit local).

    Sans ça, leur remise à 0 le 1er produit un `change` négatif dans les
    statistiques TOTAL auto-générées par HA.
    """
    sensor = _make_slim_sensor(key, [])
    last_reset = sensor._compute_last_reset()

    if resets_monthly:
        expected = dt_util.start_of_local_day().replace(day=1)
        assert last_reset is not None
        assert last_reset == expected
        assert last_reset.day == 1
        assert (last_reset.hour, last_reset.minute) == (0, 0)
        assert last_reset.tzinfo is not None
    else:
        assert last_reset is None
