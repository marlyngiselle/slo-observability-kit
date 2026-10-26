"""Multi-window, multi-burn-rate alerting math.

The policy follows the alerting chapter of the Google SRE workbook. Each alert
pairs a long window, which proves the burn is significant, with a short window
that is one twelfth of it, which proves the burn is still happening and lets the
alert reset quickly once the incident is over.

A burn rate of 1 consumes exactly the whole error budget over the SLO period.
A burn rate of 14.4 sustained for one hour consumes 2% of a 30 day budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from slokit.durations import parse_duration


class Severity(StrEnum):
    """Who gets interrupted. A page wakes a human, a ticket waits for working hours."""

    PAGE = "page"
    TICKET = "ticket"


@dataclass(frozen=True)
class BurnRateWindow:
    """One long/short window pair and the burn rate that triggers it."""

    severity: Severity
    burn_rate: Decimal
    long_window: str
    short_window: str

    def threshold(self, error_budget: Decimal) -> Decimal:
        """Error ratio above which both windows must sit for the alert to fire."""
        return self.burn_rate * error_budget

    def budget_consumed(self, period: str) -> Decimal:
        """Fraction of the whole period's budget spent while the long window fires."""
        return (
            self.burn_rate
            * Decimal(parse_duration(self.long_window))
            / Decimal(parse_duration(period))
        )

    def time_to_exhaustion_hours(self, period: str) -> Decimal:
        """Hours until a full budget is gone if this burn rate is sustained."""
        return Decimal(parse_duration(period)) / Decimal(3600) / self.burn_rate

    def detection_minutes(self, error_ratio: Decimal, error_budget: Decimal) -> Decimal | None:
        """Minutes for the long window to cross the threshold after a step change.

        Returns None when the error ratio never reaches the threshold. The short
        window, being twelve times shorter, always crosses first.
        """
        threshold = self.threshold(error_budget)
        if error_ratio <= threshold:
            return None
        return Decimal(parse_duration(self.long_window)) / 60 * threshold / error_ratio


DEFAULT_POLICY: tuple[BurnRateWindow, ...] = (
    BurnRateWindow(Severity.PAGE, Decimal("14.4"), "1h", "5m"),
    BurnRateWindow(Severity.PAGE, Decimal("6"), "6h", "30m"),
    BurnRateWindow(Severity.TICKET, Decimal("3"), "1d", "2h"),
    BurnRateWindow(Severity.TICKET, Decimal("1"), "3d", "6h"),
)

# Every window the recording rules must provide, shortest first.
SLI_WINDOWS: tuple[str, ...] = ("5m", "30m", "1h", "2h", "6h", "1d", "3d")


def required_windows(policy: tuple[BurnRateWindow, ...] = DEFAULT_POLICY) -> list[str]:
    """Windows referenced by a policy, sorted by length."""
    windows = {w.long_window for w in policy} | {w.short_window for w in policy}
    return sorted(windows, key=parse_duration)


def windows_for(
    severity: Severity, policy: tuple[BurnRateWindow, ...] = DEFAULT_POLICY
) -> list[BurnRateWindow]:
    """Policy entries of one severity, in policy order."""
    return [w for w in policy if w.severity is severity]


def max_burn_rate(policy: tuple[BurnRateWindow, ...] = DEFAULT_POLICY) -> Decimal:
    """The steepest burn rate in a policy."""
    return max(w.burn_rate for w in policy)


def first_alert(
    error_ratio: Decimal,
    error_budget: Decimal,
    policy: tuple[BurnRateWindow, ...] = DEFAULT_POLICY,
) -> tuple[BurnRateWindow, Decimal] | None:
    """The policy entry that fires first for a sustained error ratio, and after how long."""
    hits = [
        (w, minutes)
        for w in policy
        if (minutes := w.detection_minutes(error_ratio, error_budget)) is not None
    ]
    return min(hits, key=lambda hit: hit[1]) if hits else None


def fmt(value: Decimal) -> str:
    """Render a Decimal without exponent or trailing zeros ("0.0144", "28")."""
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
