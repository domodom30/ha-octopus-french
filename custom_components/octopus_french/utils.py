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
        # Extract type (HC, HP, etc.)
        if type_match := re.match(r"^([A-Z]+)", off_peak_label):
            result["type"] = type_match.group(1)

        # Extract time ranges: format like "0H50-6H50" or "14H50-16H50"
        time_pattern = r"(\d+)H(\d+)-(\d+)H(\d+)"
        matches = re.findall(time_pattern, off_peak_label)

        total_minutes = 0

        for match in matches:
            start_hour, start_min, end_hour, end_min = map(int, match)

            # Convert to minutes since midnight
            start_minutes = start_hour * 60 + start_min
            end_minutes = end_hour * 60 + end_min

            # Calculate duration (handle ranges that cross midnight)
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


def convert_sensor_date(date_string):
    """Convertit une date au format ISO 8601 vers le format YYYY-MM-DD."""
    if not date_string:
        return None

    dt = datetime.fromisoformat(date_string)

    return dt.strftime("%Y-%m-%d")
