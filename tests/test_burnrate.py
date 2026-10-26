"""The alerting math, checked against the numbers in the SRE workbook."""

from __future__ import annotations

from decimal import Decimal

import pytest

from slokit.burnrate import (
    DEFAULT_POLICY,
    SLI_WINDOWS,
    BurnRateWindow,
    Severity,
    first_alert,
    fmt,
    required_windows,
    windows_for,
)
from slokit.durations import parse_duration


def test_policy_matches_workbook() -> None:
    table = [(w.severity, fmt(w.burn_rate), w.long_window, w.short_window) for w in DEFAULT_POLICY]
    assert table == [
        (Severity.PAGE, "14.4", "1h", "5m"),
        (Severity.PAGE, "6", "6h", "30m"),
        (Severity.TICKET, "3", "1d", "2h"),
        (Severity.TICKET, "1", "3d", "6h"),
    ]


@pytest.mark.parametrize(
    "window", DEFAULT_POLICY, ids=lambda w: f"{w.long_window}-{w.short_window}"
)
def test_short_window_is_one_twelfth_of_long(window: BurnRateWindow) -> None:
    assert parse_duration(window.long_window) == 12 * parse_duration(window.short_window)


@pytest.mark.parametrize(
    ("index", "expected_percent"),
    [(0, "2"), (1, "5"), (2, "10"), (3, "10")],
)
def test_budget_consumed_on_30d_matches_workbook(index: int, expected_percent: str) -> None:
    consumed = DEFAULT_POLICY[index].budget_consumed("30d") * 100
    assert consumed == Decimal(expected_percent)


def test_budget_consumed_on_28d_is_slightly_higher() -> None:
    assert fmt((DEFAULT_POLICY[0].budget_consumed("28d") * 100).quantize(Decimal("0.01"))) == "2.14"


@pytest.mark.parametrize(("index", "hours"), [(0, "50"), (1, "120"), (2, "240"), (3, "720")])
def test_time_to_exhaustion_on_30d(index: int, hours: str) -> None:
    assert DEFAULT_POLICY[index].time_to_exhaustion_hours("30d") == Decimal(hours)


@pytest.mark.parametrize(
    ("burn", "budget", "threshold"),
    [(0, "0.001", "0.0144"), (1, "0.001", "0.006"), (0, "0.05", "0.72"), (3, "0.005", "0.005")],
)
def test_threshold_is_burn_rate_times_budget(burn: int, budget: str, threshold: str) -> None:
    assert fmt(DEFAULT_POLICY[burn].threshold(Decimal(budget))) == threshold


def test_recorded_windows_cover_the_policy() -> None:
    assert set(required_windows()) <= set(SLI_WINDOWS)
    assert list(SLI_WINDOWS) == sorted(SLI_WINDOWS, key=parse_duration)


def test_windows_for_severity() -> None:
    assert [fmt(w.burn_rate) for w in windows_for(Severity.PAGE)] == ["14.4", "6"]
    assert [fmt(w.burn_rate) for w in windows_for(Severity.TICKET)] == ["3", "1"]


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Decimal("0.0010000"), "0.001"),
        (Decimal("28"), "28"),
        (Decimal("1E+1"), "10"),
        (Decimal("0"), "0"),
    ],
)
def test_fmt(value: Decimal, text: str) -> None:
    assert fmt(value) == text


@pytest.mark.parametrize(("text", "seconds"), [("5m", 300), ("1h", 3600), ("28d", 2419200)])
def test_parse_duration(text: str, seconds: int) -> None:
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "5", "1h30m", "0m", "-1h", "1y"])
def test_parse_duration_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration(text)


@pytest.mark.parametrize(
    ("error_ratio", "burn", "minutes"),
    [
        ("1", "14.4", "0.864"),
        ("0.1", "14.4", "8.64"),
        ("0.02", "14.4", "43.2"),
        ("0.01", "6", "216"),
        ("0.005", "3", "864"),
        ("0.002", "1", "2160"),
    ],
)
def test_first_alert_for_step_change(error_ratio: str, burn: str, minutes: str) -> None:
    hit = first_alert(Decimal(error_ratio), Decimal("0.001"))
    assert hit is not None
    window, after = hit
    assert (fmt(window.burn_rate), fmt(after)) == (burn, minutes)


def test_no_alert_below_budget() -> None:
    assert first_alert(Decimal("0.0009"), Decimal("0.001")) is None
