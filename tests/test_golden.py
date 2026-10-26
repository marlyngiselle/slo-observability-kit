"""Golden files: the committed examples are exactly what the generator produces today."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from slokit.generate import diff, render
from slokit.models import load_all
from tests.conftest import GENERATED, SPECS

OUTPUT = render(load_all([SPECS]))


@pytest.mark.parametrize("rel", sorted(OUTPUT.files))
def test_matches_committed_file(rel: str) -> None:
    committed = (GENERATED / rel).read_text(encoding="utf-8")
    assert committed == OUTPUT.files[rel], (
        f"{rel} is stale. Run: slokit generate examples/slos -o examples/generated"
    )


def test_no_orphan_files() -> None:
    on_disk = {p.relative_to(GENERATED).as_posix() for p in GENERATED.rglob("*") if p.is_file()}
    assert on_disk == set(OUTPUT.files)


def test_counts() -> None:
    assert (OUTPUT.slos, OUTPUT.recording_rules, OUTPUT.alert_rules, OUTPUT.dashboards) == (
        3,
        42,
        6,
        3,
    )


@pytest.mark.parametrize("path", sorted(GENERATED.rglob("*.yaml")), ids=lambda p: p.name)
def test_rule_files_are_valid_prometheus_shape(path: Path) -> None:
    doc = yaml.safe_load(path.read_text())
    assert set(doc) == {"groups"}
    names = [g["name"] for g in doc["groups"]]
    assert len(names) == len(set(names)), "group names must be unique per file"
    for group in doc["groups"]:
        for rule in group["rules"]:
            assert ("record" in rule) != ("alert" in rule)
            assert set(rule) <= {"record", "alert", "expr", "for", "labels", "annotations"}


@pytest.mark.parametrize("path", sorted(GENERATED.rglob("*.json")), ids=lambda p: p.name)
def test_dashboards_are_valid_json(path: Path) -> None:
    board = json.loads(path.read_text())
    assert board["uid"] == f"slo-{path.stem}"
    ids = [p["id"] for p in board["panels"]]
    assert len(ids) == len(set(ids))
    for panel in board["panels"]:
        grid = panel["gridPos"]
        assert grid["x"] + grid["w"] <= 24
    titles = {p["title"] for p in board["panels"]}
    assert {"Error budget remaining", "Burn rate by alert window"} <= titles


def test_diff_reports_stale_files(tmp_path: Path) -> None:
    assert len(diff(OUTPUT, tmp_path)) == len(OUTPUT.files)
