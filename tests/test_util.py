"""Unit tests for the pure value helpers.

These deliberately depend only on the standard library so they can be run
without a Home Assistant development environment:

    python3 -m pytest tests/test_util.py
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

# Loaded by path: importing the package would pull in Home Assistant, and these
# helpers are deliberately free of it.
_UTIL_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "nepviewer"
    / "util.py"
)
_spec = importlib.util.spec_from_file_location("nepviewer_util", _UTIL_PATH)
util = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(util)

as_float = util.as_float
corrected_timestamp = util.corrected_timestamp
dig = util.dig
to_kwh = util.to_kwh
to_watts = util.to_watts

# 2026-09-19 15:24:29 America/Los_Angeles, as the API reports it: the local
# wall clock encoded as if it were UTC.
RAW_TS = 1789831469
TRUE_TS = RAW_TS + 7 * 3600
NOW = TRUE_TS + 58


def test_as_float_accepts_api_strings() -> None:
    assert as_float("0.109") == pytest.approx(0.109)
    assert as_float(176) == 176.0
    assert as_float(None) is None
    assert as_float("") is None
    assert as_float(True) is None


def test_to_watts_scales_by_tag() -> None:
    assert to_watts(176, "W") == 176.0
    assert to_watts(1.2, "kW") == 1200.0
    assert to_watts(1, "MW") == 1_000_000.0
    assert to_watts(5, "bananas") is None
    assert to_watts(None, "W") is None


def test_to_kwh_scales_by_tag() -> None:
    assert to_kwh("0.109", "kWh") == pytest.approx(0.109)
    assert to_kwh(109, "Wh") == pytest.approx(0.109)
    assert to_kwh(2, "MWh") == 2000.0


def test_module_energy_is_wh_despite_kwh_tag() -> None:
    """A module reporting 109 matches a device total of 0.109 kWh."""
    module = {"todayPower": 109, "todayPowerUnit": "kWh"}
    assert to_kwh(module["todayPower"], "Wh") == pytest.approx(0.109)


def test_dig_survives_missing_levels() -> None:
    data = {"production": {"today": "0.109"}}
    assert dig(data, "production", "today") == "0.109"
    assert dig(data, "production", "missing") is None
    assert dig(data, "nothing", "here") is None
    assert dig(None, "production") is None


def test_corrected_timestamp_undoes_westward_shift() -> None:
    """A UTC-7 site: the raw value looks 7 hours old, the corrected one is live."""
    assert corrected_timestamp(RAW_TS, "America/Los_Angeles", now=NOW) == TRUE_TS


def test_corrected_timestamp_undoes_eastward_shift() -> None:
    """A UTC+2 site: the raw value lands in the future and must be rejected."""
    true_ts = 1789856727
    raw = true_ts + 2 * 3600
    assert corrected_timestamp(raw, "Europe/Berlin", now=true_ts + 60) == true_ts


def test_corrected_timestamp_leaves_real_utc_alone() -> None:
    """If NEP ever stores true UTC, the raw value stays the best candidate."""
    true_ts = 1789856727
    assert corrected_timestamp(true_ts, "America/Los_Angeles", now=true_ts + 60) == true_ts


def test_corrected_timestamp_without_timezone() -> None:
    assert corrected_timestamp(RAW_TS, None, now=NOW) == RAW_TS
    assert corrected_timestamp(RAW_TS, "Not/AZone", now=NOW) == RAW_TS


def test_corrected_timestamp_handles_missing_value() -> None:
    assert corrected_timestamp(None, "America/Los_Angeles") is None
    assert corrected_timestamp(0, "America/Los_Angeles") is None


def test_offline_device_stays_old() -> None:
    """A device silent for days is still far past any staleness threshold."""
    days_ago = NOW - 3 * 86400
    corrected = corrected_timestamp(days_ago, "America/Los_Angeles", now=NOW)
    assert NOW - corrected > 2 * 86400
