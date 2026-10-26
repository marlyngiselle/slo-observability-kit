"""Spec validation: good input loads, bad input fails with a message a human can act on."""

from __future__ import annotations

from pathlib import Path

import pytest

from slokit.models import SpecError, load_all, parse_spec
from tests.conftest import SPECS


def test_minimal_spec_loads(minimal_yaml: str) -> None:
    spec = parse_spec(minimal_yaml)
    assert spec.service == "demo-api"
    assert spec.slos[0].window == "28d"
    assert str(spec.slos[0].error_budget) == "0.001"


def test_examples_all_load() -> None:
    services = [spec.service for _, spec in load_all([SPECS])]
    assert services == ["checkout-api", "ingestion-pipeline", "search"]


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("objective: 99.9", "objective: 90", "page alert could never fire"),
        ("objective: 99.9", "objective: 100", "less than 100"),
        ("good_filter:", "bad_filter:", "template must contain exactly one of"),
        ("type: availability", "type: latency", "type latency needs the latency template fields"),
        ("service: demo-api", "service: Demo API", "lowercase letters, digits or hyphens"),
        ("owner: demo-team", "owner: demo-team\nonwer: typo", "onwer: unknown field"),
        (
            "    objective: 99.9",
            "    objective: 99.9\n    window: 7d",
            "window: Input should be '28d' or '30d'",
        ),
        ("runbook_url: https://runbooks.example.com/demo-api", "runbook_url: wiki", "runbook_url"),
    ],
)
def test_invalid_specs_explain_themselves(
    minimal_yaml: str, old: str, new: str, message: str
) -> None:
    assert old in minimal_yaml
    with pytest.raises(SpecError) as exc:
        parse_spec(minimal_yaml.replace(old, new, 1), source="demo.yaml")
    assert "demo.yaml" in str(exc.value)
    assert message in str(exc.value)


def test_raw_queries_need_window_placeholder(minimal_yaml: str) -> None:
    raw = minimal_yaml.split("      template:")[0] + (
        "      queries:\n"
        "        good: sum(rate(ok_total[5m]))\n"
        "        total: sum(rate(all_total[{{window}}]))\n"
    )
    with pytest.raises(SpecError, match=r"slos\.0\.sli\.queries\.good: query must contain"):
        parse_spec(raw)


def test_queries_and_template_are_exclusive(minimal_yaml: str) -> None:
    both = minimal_yaml + (
        "      queries:\n"
        "        good: sum(rate(ok_total[{{window}}]))\n"
        "        total: sum(rate(all_total[{{window}}]))\n"
    )
    with pytest.raises(SpecError, match="set exactly one of 'queries'"):
        parse_spec(both)


def test_duplicate_slo_names(minimal_yaml: str) -> None:
    slo = minimal_yaml.split("slos:\n")[1]
    with pytest.raises(SpecError, match="used twice"):
        parse_spec(minimal_yaml + slo)


def test_reserved_labels_are_rejected(minimal_yaml: str) -> None:
    text = minimal_yaml.replace("owner: demo-team", "owner: demo-team\nlabels:\n  severity: low")
    with pytest.raises(SpecError, match="set by slokit"):
        parse_spec(text)


def test_latency_metric_without_suffix(minimal_yaml: str) -> None:
    text = (
        minimal_yaml.replace("type: availability", "type: latency")
        .replace('good_filter: code!~"5.."', 'le: "0.3"')
        .replace("http_requests_total", "http_duration_seconds_bucket")
    )
    with pytest.raises(SpecError, match="without the _bucket suffix"):
        parse_spec(text)


def test_not_yaml() -> None:
    with pytest.raises(SpecError, match="not valid YAML"):
        parse_spec("a: [", source="broken.yaml")


def test_all_errors_reported_at_once(tmp_path: Path, minimal_yaml: str) -> None:
    (tmp_path / "a.yaml").write_text(minimal_yaml.replace("objective: 99.9", "objective: 42"))
    (tmp_path / "b.yaml").write_text(minimal_yaml.replace("owner: demo-team", "owner: X"))
    with pytest.raises(SpecError) as exc:
        load_all([tmp_path])
    assert "a.yaml" in str(exc.value) and "b.yaml" in str(exc.value)


def test_duplicate_services_across_files(tmp_path: Path, minimal_yaml: str) -> None:
    (tmp_path / "a.yaml").write_text(minimal_yaml)
    (tmp_path / "b.yml").write_text(minimal_yaml)
    with pytest.raises(SpecError, match="already defined"):
        load_all([tmp_path])


def test_missing_path() -> None:
    with pytest.raises(SpecError, match="no such file"):
        load_all([Path("does/not/exist.yaml")])
