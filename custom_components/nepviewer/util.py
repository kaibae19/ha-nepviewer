"""Value helpers for the NEPViewer integration.

The API tags most numbers with their own unit string, and one of those tags is
wrong: the per-module ``todayPower``/``totalPower`` fields claim ``kWh`` while
actually carrying Wh (a module reporting 109 lines up with a device total of
0.109 kWh). Conversions therefore go through these helpers rather than trusting
the payload blindly.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

POWER_FACTORS = {"W": 1.0, "KW": 1000.0, "MW": 1_000_000.0}
ENERGY_FACTORS = {"WH": 0.001, "KWH": 1.0, "MWH": 1000.0}


def as_float(value: Any) -> float | None:
    """Return value as a float, or None if it is not numeric.

    Production figures arrive as strings ("0.109"), power as numbers.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_watts(value: Any, unit: Any) -> float | None:
    """Convert a tagged power reading to watts."""
    number = as_float(value)
    if number is None:
        return None
    factor = POWER_FACTORS.get(str(unit or "W").strip().upper())
    if factor is None:
        return None
    return round(number * factor, 3)


def to_kwh(value: Any, unit: Any) -> float | None:
    """Convert a tagged energy reading to kWh."""
    number = as_float(value)
    if number is None:
        return None
    factor = ENERGY_FACTORS.get(str(unit or "kWh").strip().upper())
    if factor is None:
        return None
    return round(number * factor, 4)


def dig(data: dict[str, Any] | None, *path: str) -> Any:
    """Walk a nested dict, returning None if any step is missing."""
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def corrected_timestamp(
    raw: int | None, tz_name: str | None, now: float | None = None
) -> int | None:
    """Return the true unix timestamp of a reading reported by the API.

    The backend stores an inverter's local wall clock as if it were UTC, so at
    a site on UTC-7 every reading looks seven hours old and a site on UTC+2
    would look two hours into the future. Both the raw value and the value
    reinterpreted in the site's timezone are considered, and the most recent
    one that is not in the future wins -- which keeps working unchanged if NEP
    ever starts storing real UTC.
    """
    if not raw:
        return None

    candidates = [int(raw)]
    if tz_name:
        try:
            wall = datetime.fromtimestamp(raw, UTC).replace(tzinfo=ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError, OverflowError, OSError):
            pass
        else:
            candidates.append(int(wall.timestamp()))

    # Allow a little clock skew before calling a timestamp "future".
    cutoff = (now if now is not None else time.time()) + 300
    usable = [ts for ts in candidates if ts <= cutoff]
    return max(usable) if usable else min(candidates)
