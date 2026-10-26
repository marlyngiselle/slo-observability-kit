"""Prometheus recording and alerting rules for a service spec."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from slokit.burnrate import (
    DEFAULT_POLICY,
    SLI_WINDOWS,
    BurnRateWindow,
    Severity,
    fmt,
    windows_for,
)
from slokit.models import SLO, WINDOW_PLACEHOLDER, ServiceSpec

Rule = dict[str, Any]

ERROR_RATIO = "slo:sli_error:ratio_rate{window}"
ALERT_FOR = {Severity.PAGE: "2m", Severity.TICKET: "15m"}


def pascal(*parts: str) -> str:
    """checkout-api, availability -> CheckoutApiAvailability."""
    words = re.split(r"[-_\s]+", " ".join(parts))
    return "".join(w[:1].upper() + w[1:] for w in words if w)


def selector(spec: ServiceSpec, slo: SLO) -> str:
    return f'{{service="{spec.service}",slo="{slo.name}"}}'


def base_labels(spec: ServiceSpec, slo: SLO) -> dict[str, str]:
    return {"service": spec.service, "slo": slo.name, **dict(sorted(spec.labels.items()))}


def error_ratio_expr(slo: SLO, window: str) -> str:
    """1 - good/total. An empty good series means zero good events, never "no data"."""
    good = slo.sli.good_query().replace(WINDOW_PLACEHOLDER, window)
    total = slo.sli.total_query().replace(WINDOW_PLACEHOLDER, window)
    return f"1 - (\n  ({good})\n  or vector(0)\n)\n/\n({total})\n"


def sli_recording_rules(spec: ServiceSpec, slo: SLO) -> list[Rule]:
    labels = base_labels(spec, slo)
    return [
        {
            "record": ERROR_RATIO.format(window=w),
            "expr": error_ratio_expr(slo, w),
            "labels": labels,
        }
        for w in SLI_WINDOWS
    ]


def meta_recording_rules(spec: ServiceSpec, slo: SLO) -> list[Rule]:
    """SLO metadata and period-level budget, used by dashboards and humans."""
    labels = base_labels(spec, slo)
    sel = selector(spec, slo)
    budget = fmt(slo.error_budget)
    period = slo.window
    short = ERROR_RATIO.format(window="5m")
    period_ratio = ERROR_RATIO.format(window=period)
    return [
        {
            "record": "slo:objective:ratio",
            "expr": f"vector({fmt(slo.objective_ratio)})",
            "labels": labels,
        },
        {"record": "slo:error_budget:ratio", "expr": f"vector({budget})", "labels": labels},
        {"record": "slo:time_period:days", "expr": f"vector({period[:-1]})", "labels": labels},
        {
            "record": period_ratio,
            "expr": (
                f"sum_over_time({short}{sel}[{period}])\n"
                f"/\n"
                f"count_over_time({short}{sel}[{period}])\n"
            ),
            "labels": labels,
        },
        {
            "record": "slo:current_burn_rate:ratio",
            "expr": f"{short}{sel} / {budget}",
            "labels": labels,
        },
        {
            "record": "slo:period_burn_rate:ratio",
            "expr": f"{period_ratio}{sel} / {budget}",
            "labels": labels,
        },
        {
            "record": "slo:period_error_budget_remaining:ratio",
            "expr": f"1 - slo:period_burn_rate:ratio{sel}",
            "labels": labels,
        },
    ]


def _condition(spec: ServiceSpec, slo: SLO, w: BurnRateWindow) -> str:
    sel = selector(spec, slo)
    threshold = fmt(w.threshold(slo.error_budget))
    long_ratio = ERROR_RATIO.format(window=w.long_window)
    short_ratio = ERROR_RATIO.format(window=w.short_window)
    return f"(\n  {long_ratio}{sel} > {threshold}\n  and\n  {short_ratio}{sel} > {threshold}\n)"


def alert_rule(spec: ServiceSpec, slo: SLO, severity: Severity) -> Rule:
    windows = windows_for(severity, DEFAULT_POLICY)
    route = spec.alerting.page if severity is Severity.PAGE else spec.alerting.ticket
    expr = "\nor\n".join(_condition(spec, slo, w) for w in windows) + "\n"
    pairs = ", ".join(f"{fmt(w.burn_rate)}x over {w.long_window}/{w.short_window}" for w in windows)
    exhaustion = ", ".join(
        f"{fmt(w.time_to_exhaustion_hours(slo.window).quantize(Decimal('0.1')))}h at "
        f"{fmt(w.burn_rate)}x"
        for w in windows
    )
    labels: dict[str, str] = {
        "severity": severity.value,
        "team": route.team,
        **base_labels(spec, slo),
    }
    if route.channel:
        labels["channel"] = route.channel
    verb = "fast" if severity is Severity.PAGE else "steadily"
    return {
        "alert": f"{pascal(spec.service, slo.name)}BudgetBurn",
        "expr": expr,
        "for": ALERT_FOR[severity],
        "labels": labels,
        "annotations": {
            "summary": f"{spec.service} {slo.name} is burning its error budget {verb}",
            "description": (
                f"{slo.description} Objective {fmt(slo.objective)}% over {slo.window}. "
                f"Long window error ratio is {{{{ $value | humanizePercentage }}}} against a "
                f"budget of {fmt(slo.error_budget * 100)}%. Fires on {pairs}. "
                f"Budget exhaustion at that rate: {exhaustion}."
            ),
            "runbook_url": f"{spec.alerting.runbook_url}#{slo.name}",
            "dashboard": f"/d/slo-{spec.service}",
        },
    }


def rule_groups(spec: ServiceSpec) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for slo in spec.slos:
        prefix = f"slo-{spec.service}-{slo.name}"
        groups.append({"name": f"{prefix}-sli", "rules": sli_recording_rules(spec, slo)})
        groups.append({"name": f"{prefix}-meta", "rules": meta_recording_rules(spec, slo)})
        groups.append(
            {
                "name": f"{prefix}-alerts",
                "rules": [alert_rule(spec, slo, s) for s in (Severity.PAGE, Severity.TICKET)],
            }
        )
    return {"groups": groups}


def count_rules(doc: dict[str, Any]) -> tuple[int, int]:
    """(recording rules, alerting rules) in a rule file document."""
    rules = [r for g in doc["groups"] for r in g["rules"]]
    return sum("record" in r for r in rules), sum("alert" in r for r in rules)
