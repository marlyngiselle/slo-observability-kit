"""Rule generation: names, windows, thresholds and PromQL that Prometheus will accept."""

from __future__ import annotations

import re
from typing import Any

import pytest

from slokit.burnrate import DEFAULT_POLICY, SLI_WINDOWS, Severity, fmt
from slokit.models import ServiceSpec, load_all, parse_spec
from slokit.rules import alert_rule, count_rules, error_ratio_expr, pascal, rule_groups
from tests.conftest import SPECS


@pytest.fixture
def spec(minimal_yaml: str) -> ServiceSpec:
    return parse_spec(minimal_yaml)


def _rules(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for g in doc["groups"] for r in g["rules"]]


def test_one_error_ratio_per_window(spec: ServiceSpec) -> None:
    records = [r["record"] for r in _rules(rule_groups(spec)) if "record" in r]
    for window in [*SLI_WINDOWS, "28d"]:
        assert f"slo:sli_error:ratio_rate{window}" in records
    assert count_rules(rule_groups(spec)) == (len(SLI_WINDOWS) + 7, 2)


def test_window_is_substituted_everywhere(spec: ServiceSpec) -> None:
    expr = error_ratio_expr(spec.slos[0], "6h")
    assert "{{window}}" not in expr
    assert expr.count("[6h]") == 2


def test_empty_good_series_counts_as_zero(spec: ServiceSpec) -> None:
    # Without "or vector(0)" a total outage (no good requests at all) would return no data
    # and the alert that matters most would never fire.
    assert "or vector(0)" in error_ratio_expr(spec.slos[0], "5m")


@pytest.mark.parametrize("severity", list(Severity))
def test_alert_thresholds(spec: ServiceSpec, severity: Severity) -> None:
    rule = alert_rule(spec, spec.slos[0], severity)
    expected = [w for w in DEFAULT_POLICY if w.severity is severity]
    found = re.findall(r"ratio_rate(\w+)\{[^}]*\} > ([0-9.]+)", rule["expr"])
    assert found == [
        pair
        for w in expected
        for pair in (
            (w.long_window, fmt(w.burn_rate * spec.slos[0].error_budget)),
            (w.short_window, fmt(w.burn_rate * spec.slos[0].error_budget)),
        )
    ]
    assert rule["labels"]["severity"] == severity.value


def test_page_and_ticket_route_to_their_teams(spec: ServiceSpec) -> None:
    page = alert_rule(spec, spec.slos[0], Severity.PAGE)
    ticket = alert_rule(spec, spec.slos[0], Severity.TICKET)
    assert page["labels"]["team"] == "demo-oncall"
    assert ticket["labels"]["team"] == "demo-team"
    assert page["alert"] == ticket["alert"] == "DemoApiAvailabilityBudgetBurn"
    assert page["for"] == "2m" and ticket["for"] == "15m"


def test_alert_annotations(spec: ServiceSpec) -> None:
    ann = alert_rule(spec, spec.slos[0], Severity.PAGE)["annotations"]
    assert ann["runbook_url"] == "https://runbooks.example.com/demo-api#availability"
    assert ann["dashboard"] == "/d/slo-demo-api"
    assert "{{ $value | humanizePercentage }}" in ann["description"]
    assert "14.4x over 1h/5m" in ann["description"]


def test_custom_labels_reach_every_rule(minimal_yaml: str) -> None:
    spec = parse_spec(
        minimal_yaml.replace("owner: demo-team", "owner: demo-team\nlabels: {tier: '1'}")
    )
    assert all(r["labels"]["tier"] == "1" for r in _rules(rule_groups(spec)))


def test_period_ratio_uses_slo_window(minimal_yaml: str) -> None:
    spec = parse_spec(minimal_yaml.replace("objective: 99.9", "objective: 99.9\n    window: 30d"))
    rules = {r.get("record"): r for r in _rules(rule_groups(spec))}
    assert "[30d]" in rules["slo:sli_error:ratio_rate30d"]["expr"]
    assert rules["slo:time_period:days"]["expr"] == "vector(30)"


def test_latency_template_targets_bucket(minimal_yaml: str) -> None:
    spec = parse_spec(
        minimal_yaml.replace("type: availability", "type: latency")
        .replace("http_requests_total", "http_request_duration_seconds")
        .replace('good_filter: code!~"5.."', 'le: "0.25"')
    )
    expr = error_ratio_expr(spec.slos[0], "5m")
    assert 'http_request_duration_seconds_bucket{job="demo-api",le="0.25"}[5m]' in expr
    assert 'http_request_duration_seconds_count{job="demo-api"}[5m]' in expr


def test_freshness_template_uses_subquery(minimal_yaml: str) -> None:
    spec = parse_spec(
        minimal_yaml.replace("type: availability", "type: freshness")
        .replace("http_requests_total", "job_last_success_timestamp_seconds")
        .replace('good_filter: code!~"5.."', "max_age_seconds: 600")
    )
    expr = error_ratio_expr(spec.slos[0], "1h")
    assert "< bool 600)[1h:1m]" in expr
    assert "count_over_time(" in expr


def test_pascal() -> None:
    assert pascal("checkout-api", "latency-p95") == "CheckoutApiLatencyP95"


def test_every_generated_expression_parses() -> None:
    promql = pytest.importorskip("promql_parser")
    exprs = [
        (spec.service, r.get("record") or r["alert"], r["expr"])
        for _, spec in load_all([SPECS])
        for r in _rules(rule_groups(spec))
    ]
    assert len(exprs) == 48
    for service, name, expr in exprs:
        try:
            promql.parse(expr)
        except Exception as exc:  # pragma: no cover - only reached on a regression
            pytest.fail(f"{service} {name}: {exc}\n{expr}")
