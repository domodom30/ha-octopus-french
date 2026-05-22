"""helpers functions."""

from datetime import datetime
import logging
import re
from typing import Any

_LOGGER = logging.getLogger(__name__)


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

        time_pattern = r"(\d+)H(\d+)-(\d+)H(\d+)"
        matches = re.findall(time_pattern, off_peak_label)

        total_minutes = 0

        for match in matches:
            start_hour, start_min, end_hour, end_min = map(int, match)
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
    """Convert structured timeSlots from the contract API to the HC schedule format.

    Produces the same dict shape as parse_off_peak_hours() so the two sources
    are interchangeable downstream.  The 'source' key distinguishes them.

    time_slots items are expected to have 'start' and 'end' in HH:MM:SS format,
    as returned by _extract_tariffs() after mapping startAt/endAt.
    """
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
            _LOGGER.warning("Impossible de parser le créneau '%s'–'%s': %s", start_str, end_str, err)

    result["total_hours"] = round(total_minutes / 60, 2)
    result["range_count"] = len(result["ranges"])
    return result


def find_contract_hc_slots(data: dict[str, Any], prm_id: str) -> list[dict[str, Any]] | None:
    """Return the HC timeSlots from the active contract for a given PRM, or None.

    Checks heures_creuses first (HP/HC contract), then any *_hc key (Tempo).
    """
    for agreement in data.get("agreements", []):
        if agreement.get("prm") != prm_id or not agreement.get("is_active"):
            continue
        consumption = (agreement.get("tariffs") or {}).get("consumption", {})

        # Contrat HP/HC standard
        hc_rate = consumption.get("heures_creuses") or {}
        if slots := hc_rate.get("time_slots"):
            return slots

        # Contrat OctoTempo : prendre les créneaux HC d'une couleur (identiques)
        for key, rate in consumption.items():
            if key.endswith("_hc") and isinstance(rate, dict):
                if slots := rate.get("time_slots"):
                    return slots

    return None


def convert_sensor_date(date_string):
    """Convertit une date au format ISO 8601 vers le format YYYY-MM-DD."""
    if not date_string:
        return None

    dt = datetime.fromisoformat(date_string)

    return dt.strftime("%Y-%m-%d")
