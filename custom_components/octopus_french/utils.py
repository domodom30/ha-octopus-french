"""helpers functions."""

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    FRENCH_MONTH_NUMBERS,
    TARIFF_TYPE_HPHC_TWO_SEASON,
    TARIFF_TYPE_TEMPO,
    TEMPO_CALENDAR_COLORS,
    TEMPO_DEFAULT_SEASON_MONTHS,
    TEMPO_PRODUCT_CODE_KEYWORDS,
    TEMPO_SHORT_LABELS,
    TEMPO_STATISTICS_LABELS,
    TEMPO_TEMPORAL_CLASS_CODES,
    TEMPO_TEMPORAL_CLASS_TO_COLOR,
    TWO_SEASON_DEFAULT_SEASON_MONTHS,
    TWO_SEASON_TEMPORAL_CLASS_CODES,
    TWO_SEASON_TEMPORAL_CLASS_TO_SEASON,
)

_LOGGER = logging.getLogger(__name__)

_TEMPO_COLOR_TO_HC_KEY = {
    "ETE": "tempo_ete_hc",
    "HIVER": "tempo_hiver_hc",
    "ROUGE": "tempo_rouge_hc",
}

_TEMPO_COLOR_TO_HC_TEMPORAL_CODE = {
    "ETE": "HCE",
    "HIVER": "HCHI",
    "ROUGE": "HCP",
}

_TEMPO_SEASON_BY_CODE = {
    code: color
    for code, color in TEMPO_TEMPORAL_CLASS_TO_COLOR.items()
    if color != "ROUGE"
}

_TWO_SEASON_TO_HC_KEY = {
    "ETE": "heures_creuses_ete",
    "HIVER": "heures_creuses_hiver",
}

_TWO_SEASON_TO_HC_TEMPORAL_CODE = {
    "ETE": "HCB",
    "HIVER": "HCH",
}

_LINKY_FALLBACK_WARNED: set[str] = set()
_CANONICAL_CONSUMPTION_LABELS: frozenset[str] = frozenset(
    {"HEURES_PLEINES", "HEURES_CREUSES", "ABONNEMENT"}
)

_LABEL_SEGMENT_TO_CANONICAL: dict[str, str] = {
    "HP": "HEURES_PLEINES",
    "HC": "HEURES_CREUSES",
    "BASE": "BASE",
}

_TWO_SEASON_LABEL_ALIASES: dict[str, str] = {
    "HPB": "HEURES_PLEINES_ETE",
    "HCB": "HEURES_CREUSES_ETE",
    "HPH": "HEURES_PLEINES_HIVER",
    "HCH": "HEURES_CREUSES_HIVER",
}

_UNKNOWN_LABELS_WARNED: set[str] = set()

_MONTH_PATTERN = re.compile(
    "|".join(sorted(FRENCH_MONTH_NUMBERS, key=len, reverse=True)), re.IGNORECASE
)


def parse_off_peak_hours(off_peak_label: str | None) -> dict[str, Any]:
    """Parse off-peak hours label and extract time ranges."""
    result = {
        "type": None,
        "ranges": [],
        "total_hours": 0.0,
        "range_count": 0,
    }

    if not off_peak_label:
        return result

    try:
        if type_match := re.match(r"^([A-Z]+)", off_peak_label):
            result["type"] = type_match.group(1)

        time_pattern = re.compile(
            r"(\d{1,2})\s*[hH](\d{2})?\s*(?:-|à|a)\s*"
            r"(\d{1,2})\s*[hH](\d{2})?"
        )
        matches = time_pattern.findall(off_peak_label)

        total_minutes = 0

        for match in matches:
            start_hour_s, start_min_s, end_hour_s, end_min_s = match
            start_hour = int(start_hour_s)
            start_min = int(start_min_s or 0)
            end_hour = int(end_hour_s)
            end_min = int(end_min_s or 0)
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            duration_minutes = (
                end_minutes - start_minutes
                if end_minutes >= start_minutes
                else (24 * 60 - start_minutes) + end_minutes
            )

            total_minutes += duration_minutes

            result["ranges"].append(
                {
                    "start": f"{start_hour:02d}:{start_min:02d}",
                    "end": f"{end_hour:02d}:{end_min:02d}",
                    "start_minutes": start_minutes,
                    "end_minutes": end_minutes,
                    "duration_minutes": duration_minutes,
                    "duration_hours": round(duration_minutes / 60, 2),
                }
            )

        result["total_hours"] = round(total_minutes / 60, 2)
        result["range_count"] = len(result["ranges"])

    except (ValueError, AttributeError) as err:
        _LOGGER.warning("Failed to parse off-peak hours '%s': %s", off_peak_label, err)

    return result


def parse_time_slots(time_slots: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert structured timeSlots from the contract API to the HC schedule format."""

    result: dict[str, Any] = {
        "type": "HC",
        "ranges": [],
        "total_hours": 0.0,
        "range_count": 0,
        "source": "contract",
    }

    total_minutes = 0

    for slot in time_slots:
        start_str = slot.get("start") or ""
        end_str = slot.get("end") or ""
        if not start_str or not end_str:
            continue
        try:
            s_parts = start_str.split(":")
            e_parts = end_str.split(":")
            sh, sm = int(s_parts[0]), int(s_parts[1])
            eh, em = int(e_parts[0]), int(e_parts[1])

            start_minutes = sh * 60 + sm
            end_minutes = eh * 60 + em
            duration_minutes = (
                end_minutes - start_minutes
                if end_minutes >= start_minutes
                else (24 * 60 - start_minutes) + end_minutes
            )

            total_minutes += duration_minutes
            result["ranges"].append(
                {
                    "start": f"{sh:02d}:{sm:02d}",
                    "end": f"{eh:02d}:{em:02d}",
                    "start_minutes": start_minutes,
                    "end_minutes": end_minutes,
                    "duration_minutes": duration_minutes,
                    "duration_hours": round(duration_minutes / 60, 2),
                }
            )
        except (ValueError, IndexError) as err:
            _LOGGER.warning(
                "Failed to parse off-peak time slot '%s'-'%s': %s",
                start_str,
                end_str,
                err,
            )

    result["total_hours"] = round(total_minutes / 60, 2)
    result["range_count"] = len(result["ranges"])
    return result


def find_contract_hc_slots(
    data: dict[str, Any], prm_id: str, tempo_color: str | None = None
) -> list[dict[str, Any]] | None:
    """Return the HC timeSlots from the active contract for a given PRM, or None."""
    if tempo_color:
        hc_key = _TEMPO_COLOR_TO_HC_KEY.get(tempo_color.upper())
    elif season := resolve_two_season(data, prm_id):
        hc_key = _TWO_SEASON_TO_HC_KEY[season]
    else:
        hc_key = None

    for agreement in data.get("agreements", []):
        if agreement.get("prm") != prm_id or not agreement.get("is_active"):
            continue
        consumption = (agreement.get("tariffs") or {}).get("consumption", {})

        if (
            hc_key
            and (rate := consumption.get(hc_key))
            and (slots := rate.get("time_slots"))
        ):
            return slots

        hc_rate = consumption.get("heures_creuses") or {}
        if slots := hc_rate.get("time_slots"):
            return slots

        for key, rate in consumption.items():
            if (
                (key.endswith("_hc") or key.startswith("heures_creuses_"))
                and isinstance(rate, dict)
                and (slots := rate.get("time_slots"))
            ):
                return slots

    return None


def _find_electricity_meter(data: dict[str, Any], prm_id: str) -> dict[str, Any] | None:
    """Return the electricity meter matching the PRM, or None."""
    for meter in data.get("supply_points", {}).get("electricity", []):
        if meter.get("prm") == prm_id:
            return meter
    return None


def find_calendar_hc_ranges(
    data: dict[str, Any], prm_id: str, tempo_color: str | None = None
) -> dict[str, Any] | None:
    """Derive off-peak ranges from the meter's provider calendar."""
    meter = _find_electricity_meter(data, prm_id)
    if not meter:
        return None

    if tempo_color:
        wanted = _TEMPO_COLOR_TO_HC_TEMPORAL_CODE.get(tempo_color.upper(), "HC")
    elif season := resolve_two_season(data, prm_id):
        wanted = _TWO_SEASON_TO_HC_TEMPORAL_CODE[season]
    else:
        wanted = "HC"
    for temporal_class in meter.get("provider_temporal_classes") or []:
        if (temporal_class.get("code") or "").upper() != wanted:
            continue
        schedule = parse_off_peak_hours(temporal_class.get("description"))
        if schedule["range_count"] > 0:
            schedule["type"] = "HC"
            schedule["source"] = "calendar"
            return schedule
        return None

    return None


def _is_tempo_contract(data: dict[str, Any], prm_id: str) -> bool:
    """Return whether the PRM is on a Tempo contract."""
    for agreement in data.get("agreements", []):
        if agreement.get("prm") != prm_id or not agreement.get("is_active"):
            continue
        product_code = ((agreement.get("product") or {}).get("code") or "").upper()
        if any(kw in product_code for kw in TEMPO_PRODUCT_CODE_KEYWORDS):
            return True

    meter = _find_electricity_meter(data, prm_id) or {}
    codes = {
        (tc.get("code") or "").upper()
        for tc in meter.get("provider_temporal_classes") or []
    }
    return bool(codes & TEMPO_TEMPORAL_CLASS_CODES)


def resolve_hc_schedule(
    data: dict[str, Any], prm_id: str, tempo_color: str | None = None
) -> dict[str, Any]:
    """Return the PRM's off-peak ranges and their source."""
    if contract_slots := find_contract_hc_slots(data, prm_id, tempo_color):
        schedule = parse_time_slots(contract_slots)
        if schedule["range_count"] > 0:
            return schedule

    if schedule := find_calendar_hc_ranges(data, prm_id, tempo_color):
        return schedule

    meter = _find_electricity_meter(data, prm_id) or {}
    if off_peak_label := meter.get("offPeakLabel"):
        schedule = parse_off_peak_hours(off_peak_label)
        schedule["source"] = "linky"
        if _is_tempo_contract(data, prm_id) and prm_id not in _LINKY_FALLBACK_WARNED:
            _LINKY_FALLBACK_WARNED.add(prm_id)

        return schedule

    return {
        "type": None,
        "ranges": [],
        "total_hours": 0.0,
        "range_count": 0,
        "source": "none",
    }


def _parse_season_months(description: str | None) -> tuple[int, int] | None:
    """Return the month bounds of a temporal class description, or None."""
    if not description:
        return None
    months = _MONTH_PATTERN.findall(description)
    if len(months) < 2:
        return None
    return (
        FRENCH_MONTH_NUMBERS[months[0].lower()],
        FRENCH_MONTH_NUMBERS[months[1].lower()],
    )


def _month_in_range(month: int, bounds: tuple[int, int]) -> bool:
    """Return whether a month falls in a range, allowing year wraparound."""
    start, end = bounds
    if start <= end:
        return start <= month <= end
    return month >= start or month <= end


def _season_for_day(
    meter: dict[str, Any],
    season_by_code: dict[str, str],
    default_months: dict[str, tuple[int, int]],
    day: date,
) -> str | None:
    """Return the season of a date from the meter calendar months."""
    bounds: dict[str, tuple[int, int]] = {}
    for temporal_class in meter.get("provider_temporal_classes") or []:
        season = season_by_code.get((temporal_class.get("code") or "").upper())
        if season is None or season in bounds:
            continue
        if months := _parse_season_months(temporal_class.get("description")):
            bounds[season] = months

    for season, months in (bounds or default_months).items():
        if _month_in_range(day.month, months):
            return season

    return None


def resolve_tempo_season(
    data: dict[str, Any], prm_id: str, day: date | None = None
) -> str | None:
    """Return the OctoTempo season (`ETE` / `HIVER`) for a date."""
    if not _is_tempo_contract(data, prm_id):
        return None

    return _season_for_day(
        _find_electricity_meter(data, prm_id) or {},
        _TEMPO_SEASON_BY_CODE,
        TEMPO_DEFAULT_SEASON_MONTHS,
        day or dt_util.now().date(),
    )


def _is_two_season_contract(data: dict[str, Any], prm_id: str) -> bool:
    """Return whether the PRM is on a two-season peak/off-peak contract."""
    meter = _find_electricity_meter(data, prm_id) or {}
    codes = {
        (tc.get("code") or "").upper()
        for tc in meter.get("provider_temporal_classes") or []
    }
    if codes & TWO_SEASON_TEMPORAL_CLASS_CODES:
        return True

    for agreement in data.get("agreements", []):
        if agreement.get("prm") != prm_id or not agreement.get("is_active"):
            continue
        consumption = (agreement.get("tariffs") or {}).get("consumption") or {}
        if any(key in consumption for key in _TWO_SEASON_TO_HC_KEY.values()):
            return True

    return False


def resolve_two_season(
    data: dict[str, Any], prm_id: str, day: date | None = None
) -> str | None:
    """Return the two-season contract season for a date, or None."""
    if not _is_two_season_contract(data, prm_id):
        return None

    return _season_for_day(
        _find_electricity_meter(data, prm_id) or {},
        TWO_SEASON_TEMPORAL_CLASS_TO_SEASON,
        TWO_SEASON_DEFAULT_SEASON_MONTHS,
        day or dt_util.now().date(),
    )


def _measurement_color(label: str) -> str | None:
    """Return the Tempo color carried by a statistic label, or None."""
    segments = {segment.upper() for segment in (label or "").split("_")}
    for code in segments & TEMPO_TEMPORAL_CLASS_CODES:
        return TEMPO_TEMPORAL_CLASS_TO_COLOR[code]
    for color in segments & TEMPO_CALENDAR_COLORS:
        return color
    return None


def tempo_color_from_measurements(
    readings: list[dict[str, Any]], day: date | None = None
) -> tuple[str | None, str | None]:
    """Return the Tempo color from daily readings and the day it applies to."""
    totals: dict[date, dict[str, float]] = {}

    for reading in readings or []:
        local_day = reading_local_day(reading.get("startAt"))
        if local_day is None or (day is not None and local_day.date() != day):
            continue
        for stat in (reading.get("metaData") or {}).get("statistics", []):
            color = _measurement_color(stat.get("label", ""))
            if color is None:
                continue
            try:
                value = float(stat.get("value"))
            except (TypeError, ValueError):
                continue
            bucket = totals.setdefault(local_day.date(), {})
            bucket[color] = bucket.get(color, 0.0) + value

    for measured_day in sorted(totals, reverse=True):
        color, consumed = max(totals[measured_day].items(), key=lambda item: item[1])
        if consumed > 0:
            return color, measured_day.isoformat()

    return None, None


def resolve_tempo_color(
    data: dict[str, Any], prm_id: str, days_ahead: int = 0
) -> dict[str, Any]:
    """Return the Tempo color of a day and its source."""
    target = dt_util.now().date() + timedelta(days=days_ahead)
    result: dict[str, Any] = {
        "color": None,
        "source": None,
        "date": target.isoformat(),
        "reading_date": None,
    }

    if days_ahead == 0:
        readings = (
            data.get("electricity_by_prm", {}).get(prm_id, {}).get("readings") or []
        )
        color, reading_date = tempo_color_from_measurements(readings, target)
        result["reading_date"] = reading_date
        if color == "ROUGE":
            return result | {"color": color, "source": "measurements"}

    if season := resolve_tempo_season(data, prm_id, target):
        return result | {"color": season, "source": "season"}

    index_data = data.get("electricity_by_prm", {}).get(prm_id, {}).get("index") or {}
    color = index_data.get("tempo_color")
    if isinstance(color, str):
        return result | {
            "color": color,
            "source": "index",
            "reading_date": index_data.get("tempo_color_date"),
        }

    return result


def get_tempo_color_for_prm(data: dict[str, Any], prm_id: str) -> str | None:
    """Return the current Tempo color for a PRM."""
    return resolve_tempo_color(data, prm_id)["color"]


def is_electricity_meter_active(meter: dict[str, Any]) -> bool:
    """Return whether an electricity supply point should be exposed."""
    if meter.get("distributorStatus") != "RESIL":
        return True
    powered_status = meter.get("poweredStatus")
    return powered_status is not None and powered_status != "LIMI"


def normalize_consumption_label(label: str) -> str:
    """Normalize API label variants to their canonical form."""
    if not label:
        return label
    if label in ("HEURES_BASE", "BASE"):
        return "BASE"
    if (
        label in _CANONICAL_CONSUMPTION_LABELS
        or label in TEMPO_STATISTICS_LABELS
        or label in TEMPO_SHORT_LABELS
    ):
        return label

    if label.startswith("CONSUMPTION_"):
        segments = set(label.split("_"))
        for temporal_code, canonical in _TWO_SEASON_LABEL_ALIASES.items():
            if temporal_code in segments:
                return canonical
        if segments & TEMPO_TEMPORAL_CLASS_CODES:
            return label
        for segment, canonical in _LABEL_SEGMENT_TO_CANONICAL.items():
            if segment in segments:
                return canonical

    if label not in _UNKNOWN_LABELS_WARNED:
        _UNKNOWN_LABELS_WARNED.add(label)
        _LOGGER.warning(
            "Unrecognized consumption label '%s': it will not feed any monthly "
            "total or statistic, please report it so it can be mapped",
            label,
        )
    return label


def normalize_provider_calendar(meter: dict) -> str:
    """Derive the tariff family (BASE/HPHC/TEMPO) from the provider calendar."""
    classes = meter.get("provider_temporal_classes") or []
    codes = {c.get("code") for c in classes if c.get("code")}
    if codes & TEMPO_TEMPORAL_CLASS_CODES:
        return TARIFF_TYPE_TEMPO
    if codes & TWO_SEASON_TEMPORAL_CLASS_CODES:
        return TARIFF_TYPE_HPHC_TWO_SEASON
    if len(codes) >= 2:
        return "HPHC"
    if len(codes) == 1:
        return "BASE"

    calendar_id = (meter.get("providerCalendar") or {}).get("id", "") or ""
    upper = calendar_id.upper()
    if any(kw in upper for kw in TEMPO_PRODUCT_CODE_KEYWORDS):
        return TARIFF_TYPE_TEMPO
    if "HPHC" in upper or "_HC" in upper:
        return "HPHC"
    if "BASE" in upper:
        return "BASE"
    return calendar_id


RATE_KEY_TO_CONSUMPTION_KEY: dict[str, str] = {
    "rate_base": "base",
    "cost_base": "base",
    "cost": "base",
    "rate_peak_hours": "heures_pleines",
    "cost_peak_hours": "heures_pleines",
    "rate_off_peak_hours": "heures_creuses",
    "cost_off_peak_hours": "heures_creuses",
    "rate_summer_peak_hours": "heures_pleines_ete",
    "cost_summer_peak_hours": "heures_pleines_ete",
    "rate_summer_off_peak_hours": "heures_creuses_ete",
    "cost_summer_off_peak_hours": "heures_creuses_ete",
    "rate_winter_peak_hours": "heures_pleines_hiver",
    "cost_winter_peak_hours": "heures_pleines_hiver",
    "rate_winter_off_peak_hours": "heures_creuses_hiver",
    "cost_winter_off_peak_hours": "heures_creuses_hiver",
    "rate_tempo_ete_hp": "tempo_ete_hp",
    "cost_tempo_ete_hp": "tempo_ete_hp",
    "rate_tempo_ete_hc": "tempo_ete_hc",
    "cost_tempo_ete_hc": "tempo_ete_hc",
    "rate_tempo_hiver_hp": "tempo_hiver_hp",
    "cost_tempo_hiver_hp": "tempo_hiver_hp",
    "rate_tempo_hiver_hc": "tempo_hiver_hc",
    "cost_tempo_hiver_hc": "tempo_hiver_hc",
    "rate_tempo_rouge_hp": "tempo_rouge_hp",
    "cost_tempo_rouge_hp": "tempo_rouge_hp",
    "rate_tempo_rouge_hc": "tempo_rouge_hc",
    "cost_tempo_rouge_hc": "tempo_rouge_hc",
}


def get_tariff_rate_for_key(
    data: dict[str, Any], prm_id: str, key: str
) -> float | None:
    """Return the active contract rate incl. tax (€/kWh) for a sensor key."""

    consumption_key = RATE_KEY_TO_CONSUMPTION_KEY.get(key)
    if not consumption_key:
        return None

    for agreement in data.get("agreements", []):
        if agreement.get("prm") == prm_id and agreement.get("is_active"):
            consumption = (agreement.get("tariffs") or {}).get("consumption", {})
            rate = consumption.get(consumption_key)
            if rate:
                return rate.get("price_ttc")

    _LOGGER.debug("No tariff rate found in agreements for %s, key %s", prm_id, key)
    return None


def convert_sensor_date(date_string: str | None) -> str | None:
    """Convert an ISO 8601 date to YYYY-MM-DD."""
    if not date_string:
        return None

    dt = datetime.fromisoformat(date_string)

    return dt.strftime("%Y-%m-%d")


def reading_local_day(start_at: str | None) -> datetime | None:
    """Return local midnight of a reading's calendar day."""
    if not start_at:
        return None
    try:
        return (
            datetime.fromisoformat(start_at)
            .astimezone(dt_util.DEFAULT_TIME_ZONE)
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
    except (ValueError, TypeError, AttributeError) as err:
        _LOGGER.warning("Failed to parse reading date %s: %s", start_at, err)
        return None


def _spread_over_days(
    start_at: str | None, end_at: str | None, value: float
) -> dict[datetime, float]:
    """Spread a period's value evenly over its calendar days."""
    first_day = reading_local_day(start_at)
    if first_day is None or value <= 0:
        return {}

    last_day = reading_local_day(end_at)
    if last_day is None or last_day <= first_day:
        return {first_day: value}

    day_count = (last_day - first_day).days
    share = value / day_count
    return {first_day + timedelta(days=offset): share for offset in range(day_count)}


def gas_daily_values(gas_data: dict[str, Any]) -> dict[datetime, float]:
    """Return a continuous daily gas consumption series (kWh)."""
    daily: dict[datetime, float] = {}

    for source in ("monthly", "index"):
        for reading in gas_data.get(source) or []:
            for day, value in _spread_over_days(
                reading.get("startAt"),
                reading.get("endAt"),
                float(reading.get("value") or 0),
            ).items():
                daily[day] = daily.get(day, 0.0) + value

    measured: dict[datetime, float] = {}
    for reading in gas_data.get("daily") or []:
        day = reading_local_day(reading.get("startAt"))
        value = reading.get("value")

        if day is not None and value is not None:
            measured[day] = measured.get(day, 0.0) + float(value)

    if any(value > 0 for value in measured.values()):
        daily |= measured
        last_measured = max(measured)
        daily = {day: value for day, value in daily.items() if day <= last_measured}

    return daily


def gas_month_total(gas_data: dict[str, Any], month: str) -> float:
    """Return the local gas consumption (kWh) of month `YYYY-MM`."""
    for reading in gas_data.get("monthly") or []:
        day = reading_local_day(reading.get("startAt"))
        if day is not None and day.strftime("%Y-%m") == month:
            return round(float(reading.get("value") or 0), 2)

    total = sum(
        value
        for day, value in gas_daily_values(gas_data).items()
        if day.strftime("%Y-%m") == month
    )
    return round(total, 2)
