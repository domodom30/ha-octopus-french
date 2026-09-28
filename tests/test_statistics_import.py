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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
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


def _make_gas_importer(gas_data: dict[str, Any]) -> OctopusStatisticsImporter:
    """Importer monté sur un seul PCE, sans électricité."""
    coordinator = SimpleNamespace(
        data={
            "electricity_by_prm": {},
            "agreements": [
                {
                    "prm": "12345678901234",
                    "is_active": True,
                    "tariffs": {"consumption": {"base": {"price_ttc": 0.1}}},
                }
            ],
            "gas_by_pce": {"12345678901234": gas_data},
            "supply_points": {"gas": [{"prm": "12345678901234"}]},
        }
    )
    return OctopusStatisticsImporter(MagicMock(), coordinator)


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_gas_partial_daily_coverage_does_not_double_count_month() -> None:
    """Des mesures quotidiennes partielles ne se cumulent pas au mois déjà compté.

    Reproduit la corruption observée en base : le cumul mensuel de juin restait
    écrit, et les relevés quotidiens de la seconde moitié du mois s'ajoutaient
    par-dessus au lieu de le remplacer.
    """
    store = _FakeStatsStore()
    statistic_id = "octopus_french:12345678901234_consumption"
    store.prefill(
        statistic_id,
        [
            (datetime(2026, 5, 1, tzinfo=PARIS), 300.0, 300.0),
            (datetime(2026, 6, 1, tzinfo=PARIS), 60.0, 360.0),
        ],
    )

    importer = _make_gas_importer(
        {
            "monthly": [
                {
                    "startAt": "2026-06-01T00:00:00+02:00",
                    "endAt": "2026-07-01T00:00:00+02:00",
                    "value": "60",
                }
            ],
            # L'API ne publie les mesures que depuis le 15.
            "daily": [
                {"startAt": f"2026-06-{day:02d}T02:00:00+02:00", "value": "1"}
                for day in range(15, 31)
            ],
        }
    )

    await _run_import(importer, store)

    states = store.states(statistic_id)
    # Mai intact, puis les 30 jours de juin : prorata jusqu'au 14, mesures ensuite.
    assert states == [300.0] + [2.0] * 14 + [1.0] * 16
    # Le point du 1er juin ne porte plus le cumul mensuel de 60 kWh.
    june_first = store.rows[statistic_id][
        datetime(2026, 6, 1, tzinfo=PARIS).timestamp()
    ]
    assert june_first["state"] == 2.0
    # Juin compté une seule fois : 28 kWh estimés + 16 kWh mesurés.
    assert store.rows[statistic_id][datetime(2026, 6, 30, tzinfo=PARIS).timestamp()][
        "sum"
    ] == pytest.approx(344.0)


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
async def test_zero_kwh_day_keeps_series_contiguous() -> None:
    """Un jour mesuré à 0 kWh est importé au lieu d'être écarté (issue #79).

    L'écarter trouait la série, ce qui faisait basculer l'import sur son cumul
    incrémental : les sommes déjà écrites n'étaient plus recalculées et le
    tableau de bord Énergie affichait un trou au lieu d'un jour à zéro.
    """
    store = _FakeStatsStore()
    # Sommes déjà faussées sur le 14 : seule la réécriture les corrige.
    store.prefill(STAT_ID, [(_paris_day(14), 5.0, 99.0)])

    readings = [
        _cost_reading("2026-06-14T00:00:00+02:00", kwh=5.0),
        _cost_reading("2026-06-15T00:00:00+02:00", kwh=0.0),
        _cost_reading("2026-06-16T00:00:00+02:00", kwh=7.0),
    ]
    await _run_import(_make_importer(readings, agreements=_AGREEMENT_HP), store)

    assert store.states(STAT_ID) == [5.0, 0.0, 7.0]
    # Série contiguë → réécriture depuis 0, les sommes faussées sont corrigées.
    assert store.changes(STAT_ID) == [5.0, 0.0, 7.0]
    # Le coût suit la même règle : 0 kWh x tarif = 0 €, pas une absence.
    assert store.states(COST_STAT_ID) == [1.25, 0.0, 1.75]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_two_season_readings_route_to_seasonal_statistics() -> None:
    """Les relevés deux saisons alimentent les séries saisonnières (issue #85).

    Ni les séries HP/HC classiques, ni un seul palier de puissance : le palier
    interpolé dans le label brut varie d'un abonnement à l'autre.
    """
    store = _FakeStatsStore()
    agreement = [
        {
            "prm": "PRM1",
            "is_active": True,
            "tariffs": {"consumption": {"heures_pleines_ete": {"price_ttc": 0.22}}},
        }
    ]
    readings = [
        _cost_reading(
            "2026-06-14T00:00:00+02:00",
            kwh=4.0,
            label="CONSUMPTION_HPHC_2_SAISONS_HPB_9.0_10.0",
        ),
        _cost_reading(
            "2026-06-15T00:00:00+02:00",
            kwh=6.0,
            label="CONSUMPTION_HPHC_2_SAISONS_HPB_36.0_37.0",
        ),
    ]
    await _run_import(_make_importer(readings, agreements=agreement), store)

    energy_summer_id = "octopus_french:PRM1_energy_summer_peak_hours"
    cost_summer_id = "octopus_french:PRM1_cost_summer_peak_hours"

    assert store.states(energy_summer_id) == [4.0, 6.0]
    assert store.states(cost_summer_id) == [pytest.approx(0.88), pytest.approx(1.32)]
    assert STAT_ID not in store.rows
    assert COST_STAT_ID not in store.rows


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


@pytest.mark.usefixtures("paris_tz")
@pytest.mark.parametrize(
    ("readings", "expected_total", "expected_month"),
    [
        pytest.param(
            [
                _cost_reading("2026-08-30T00:00:00+02:00", cents=90),
                _cost_reading("2026-08-31T00:00:00+02:00", cents=97),
            ],
            1.87,
            "2026-08",
            id="before_first_reading_of_month",
        ),
        pytest.param(
            [
                _cost_reading("2026-08-30T00:00:00+02:00", cents=90),
                _cost_reading("2026-08-31T00:00:00+02:00", cents=97),
                _cost_reading("2026-09-01T00:00:00+02:00", cents=196),
            ],
            1.96,
            "2026-09",
            id="after_first_reading_of_month",
        ),
        pytest.param(
            [_cost_reading("2026-08-31T22:00:00+00:00", cents=100)],
            1.0,
            "2026-09",
            id="utc_start_at_classified_in_local_month",
        ),
        pytest.param([], 0.0, "2026-09", id="no_readings_uses_wall_clock"),
    ],
)
def test_monthly_total_follows_data_month(
    freezer: FrozenDateTimeFactory,
    readings: list[dict],
    expected_total: float,
    expected_month: str,
) -> None:
    """
    Le mois affiché bascule au premier relevé du nouveau mois (issue #87).

    Le 2 septembre, les relevés des 30 et 31 août viennent d'arriver (J+2) :
    ils doivent compter dans le total d'août au lieu d'être perdus.
    """
    freezer.move_to("2026-09-02T10:00:00+02:00")
    sensor = _make_slim_sensor("cost_peak_hours", readings)

    assert sensor._compute_native_value() == expected_total
    assert sensor._current_month == expected_month
    year, month = map(int, expected_month.split("-"))
    assert sensor._compute_last_reset() == datetime(year, month, 1, tzinfo=PARIS)


def _make_recompute_importer(
    readings: list[dict], prm_id: str = "PRM1"
) -> tuple[OctopusStatisticsImporter, AsyncMock]:
    """Importer branché sur un client d'API factice, pour le recalcul."""
    api_client = AsyncMock()
    api_client.get_energy_readings.return_value = readings
    coordinator = SimpleNamespace(
        api_client=api_client,
        data={
            "account_id": "ACC1",
            "electricity_by_prm": {prm_id: {"readings": []}},
            "agreements": _AGREEMENT_HP,
            "gas": [],
            "gas_by_pce": {},
            "supply_points": {
                "electricity": [{"prm": prm_id, "property_id": "PROP1"}],
                "gas": [],
            },
        },
    )
    return OctopusStatisticsImporter(MagicMock(), coordinator), api_client


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_recompute_rewrites_days_outside_the_routine_window() -> None:
    """Le recalcul réécrit des journées que le cycle courant ne redemande plus."""
    store = _FakeStatsStore()
    # Sommes fausses déjà écrites, comme après un défaut de calcul corrigé depuis.
    store.prefill(
        STAT_ID,
        [
            (_paris_day(1), 99.0, 99.0),
            (_paris_day(2), 99.0, 198.0),
            (_paris_day(3), 99.0, 297.0),
        ],
    )

    readings = [
        _reading("2026-06-01T00:00:00+02:00", 10.0),
        _reading("2026-06-02T00:00:00+02:00", 20.0),
        _reading("2026-06-03T00:00:00+02:00", 30.0),
    ]
    importer, api_client = _make_recompute_importer(readings)

    fake_instance = SimpleNamespace(async_add_executor_job=store.executor)
    with (
        patch.object(statistics_import, "get_instance", return_value=fake_instance),
        patch.object(
            statistics_import, "async_add_external_statistics", side_effect=store.add
        ),
    ):
        imported = await importer.async_recompute_electricity(_paris_day(1))

    assert imported[STAT_ID] == 3
    assert store.states(STAT_ID) == [10.0, 20.0, 30.0]
    assert store.changes(STAT_ID) == [10.0, 20.0, 30.0]

    # La fenêtre demandée à l'API part bien de la date fournie.
    start_at = api_client.get_energy_readings.call_args.args[1]
    assert start_at.startswith("2026-06-01")


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_recompute_ignores_the_last_imported_guard() -> None:
    """Le garde-fou de l'import incrémental ne doit pas bloquer une réécriture."""
    store = _FakeStatsStore()
    readings = [
        _reading("2026-06-01T00:00:00+02:00", 10.0),
        _reading("2026-06-02T00:00:00+02:00", 20.0),
    ]
    importer, _ = _make_recompute_importer(readings)
    importer.last_imported[STAT_ID] = _paris_day(5).isoformat()

    fake_instance = SimpleNamespace(async_add_executor_job=store.executor)
    with (
        patch.object(statistics_import, "get_instance", return_value=fake_instance),
        patch.object(
            statistics_import, "async_add_external_statistics", side_effect=store.add
        ),
    ):
        await importer.async_recompute_electricity(_paris_day(1))

    assert store.states(STAT_ID) == [10.0, 20.0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("paris_tz")
async def test_recompute_targets_a_single_prm_when_asked() -> None:
    """Le paramètre PRM restreint le recalcul à un compteur."""
    importer, api_client = _make_recompute_importer([])

    await importer.async_recompute_electricity(_paris_day(1), prm_id="PRM_AUTRE")

    api_client.get_energy_readings.assert_not_called()


@pytest.mark.asyncio
async def test_orphan_statistics_spare_the_active_meters() -> None:
    """Seules les séries qu'aucun compteur actif ne peut alimenter sont listées."""
    importer, _ = _make_recompute_importer([])
    importer.coordinator.data["gas_by_pce"] = {"PCE1": {}}

    listed = [
        {"statistic_id": "octopus_french:PRM1_energy_peak_hours"},
        {"statistic_id": "octopus_french:PRM1_cost_peak_hours"},
        {"statistic_id": "octopus_french:PCE1_consumption"},
        # Vestige d'un contrat BASE abandonné, et compteur qui n'existe plus.
        {"statistic_id": "octopus_french:PRM_PARTI_energy_base"},
        {"statistic_id": "octopus_french:PRM1_energy_inconnu"},
        # Série d'une autre intégration : jamais touchée.
        {"statistic_id": "sensor.autre_integration"},
    ]

    fake_instance = SimpleNamespace(
        async_add_executor_job=AsyncMock(return_value=listed)
    )
    with patch.object(statistics_import, "get_instance", return_value=fake_instance):
        orphans = await importer.async_find_orphan_statistic_ids()

    assert orphans == [
        "octopus_french:PRM1_energy_inconnu",
        "octopus_french:PRM_PARTI_energy_base",
    ]


@pytest.mark.asyncio
async def test_purge_without_ids_touches_nothing() -> None:
    """Une purge sans identifiant ne doit pas appeler le recorder."""
    importer, _ = _make_recompute_importer([])
    executor = AsyncMock()

    with patch.object(
        statistics_import,
        "get_instance",
        return_value=SimpleNamespace(async_add_executor_job=executor),
    ):
        await importer.async_purge_orphan_statistics([])

    executor.assert_not_called()
