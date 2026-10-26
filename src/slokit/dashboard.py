"""Grafana dashboard JSON, one per service, one row per SLO."""

from __future__ import annotations

from typing import Any

from slokit.burnrate import DEFAULT_POLICY, fmt
from slokit.models import SLO, ServiceSpec
from slokit.rules import ERROR_RATIO, selector

Panel = dict[str, Any]
DATASOURCE = {"type": "prometheus", "uid": "${datasource}"}
SCHEMA_VERSION = 39

# Blue palette shared with the README and banner, red reserved for "budget gone".
NAVY = "#0b1f4d"
BLUE = "#2456c8"
SKY = "#5b8def"
ICE = "#9cc3ff"


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value


def _target(expr: str, legend: str, ref: str) -> dict[str, Any]:
    return {"datasource": DATASOURCE, "expr": expr, "legendFormat": legend, "refId": ref}


def _stat(
    ids: _Ids,
    title: str,
    expr: str,
    grid: dict[str, int],
    *,
    unit: str,
    decimals: int,
    steps: list[dict[str, Any]],
    description: str,
) -> Panel:
    return {
        "id": ids.next(),
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": DATASOURCE,
        "gridPos": grid,
        "targets": [_target(expr, title, "A")],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": decimals,
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": steps},
            },
            "overrides": [],
        },
        "options": {
            "colorMode": "background",
            "graphMode": "area",
            "justifyMode": "center",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "value",
        },
    }


def _timeseries(
    ids: _Ids,
    title: str,
    targets: list[dict[str, Any]],
    grid: dict[str, int],
    *,
    unit: str,
    description: str,
    steps: list[dict[str, Any]] | None = None,
) -> Panel:
    defaults: dict[str, Any] = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": "line",
            "lineWidth": 2,
            "fillOpacity": 8,
            "showPoints": "never",
            "spanNulls": True,
            "thresholdsStyle": {"mode": "line+area" if steps else "off"},
        },
    }
    if steps:
        defaults["thresholds"] = {"mode": "absolute", "steps": steps}
    return {
        "id": ids.next(),
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": DATASOURCE,
        "gridPos": grid,
        "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "right",
                "calcs": ["lastNotNull", "max"],
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def _slo_panels(spec: ServiceSpec, slo: SLO, ids: _Ids, y: int) -> list[Panel]:
    sel = selector(spec, slo)
    budget = fmt(slo.error_budget)
    period_ratio = ERROR_RATIO.format(window=slo.window)
    objective = fmt(slo.objective_ratio)
    burn_steps: list[dict[str, Any]] = [{"color": SKY, "value": None}]
    for w in sorted(DEFAULT_POLICY, key=lambda w: w.burn_rate):
        color = "orange" if w.severity.value == "ticket" else "red"
        burn_steps.append({"color": color, "value": float(w.burn_rate)})
    panels: list[Panel] = [
        {
            "id": ids.next(),
            "type": "row",
            "title": f"{slo.name}: {fmt(slo.objective)}% over {slo.window} ({slo.sli.type})",
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
            "panels": [],
        },
        _stat(
            ids,
            f"SLI ({slo.window})",
            f"1 - {period_ratio}{sel}",
            {"h": 6, "w": 6, "x": 0, "y": y + 1},
            unit="percentunit",
            decimals=3,
            steps=[{"color": "red", "value": None}, {"color": BLUE, "value": float(objective)}],
            description=slo.description,
        ),
        _stat(
            ids,
            "Error budget remaining",
            f"slo:period_error_budget_remaining:ratio{sel}",
            {"h": 6, "w": 6, "x": 6, "y": y + 1},
            unit="percentunit",
            decimals=1,
            steps=[
                {"color": "red", "value": None},
                {"color": "orange", "value": 0},
                {"color": SKY, "value": 0.25},
                {"color": BLUE, "value": 0.5},
            ],
            description=(
                "Share of the period's error budget still available. "
                "Below zero the policy freezes risky changes."
            ),
        ),
        _stat(
            ids,
            "Burn rate (1h)",
            f"{ERROR_RATIO.format(window='1h')}{sel} / {budget}",
            {"h": 6, "w": 6, "x": 12, "y": y + 1},
            unit="none",
            decimals=2,
            steps=[
                {"color": BLUE, "value": None},
                {"color": "orange", "value": 1},
                {"color": "red", "value": 6},
            ],
            description="1 means the budget lasts exactly the SLO period. 14.4 pages.",
        ),
        _stat(
            ids,
            "Objective",
            f"slo:objective:ratio{sel}",
            {"h": 6, "w": 6, "x": 18, "y": y + 1},
            unit="percentunit",
            decimals=3,
            steps=[{"color": NAVY, "value": None}],
            description=f"Target for {slo.window}. Error budget is {fmt(slo.error_budget * 100)}%.",
        ),
        _timeseries(
            ids,
            "Burn rate by alert window",
            [
                _target(f"{ERROR_RATIO.format(window=w)}{sel} / {budget}", w, chr(ord("A") + i))
                for i, w in enumerate(("1h", "6h", "1d", "3d"))
            ],
            {"h": 8, "w": 12, "x": 0, "y": y + 7},
            unit="none",
            steps=burn_steps,
            description=(
                "Long windows of the multi-window alerts. "
                "Lines mark the 1x, 3x, 6x and 14.4x thresholds."
            ),
        ),
        _timeseries(
            ids,
            "Error ratio",
            [
                _target(f"{ERROR_RATIO.format(window=w)}{sel}", w, chr(ord("A") + i))
                for i, w in enumerate(("5m", "30m", "2h", "6h"))
            ]
            + [_target(f"slo:error_budget:ratio{sel}", "budget", "Z")],
            {"h": 8, "w": 12, "x": 12, "y": y + 7},
            unit="percentunit",
            description="Short windows confirm a burn is still happening. The budget line is 1x.",
        ),
    ]
    return panels


def dashboard(spec: ServiceSpec) -> dict[str, Any]:
    ids = _Ids()
    panels: list[Panel] = []
    y = 0
    for slo in spec.slos:
        panels.extend(_slo_panels(spec, slo, ids, y))
        y += 15
    return {
        "uid": f"slo-{spec.service}",
        "title": f"SLO / {spec.service}",
        "description": f"Service level objectives for {spec.service}, owned by {spec.owner}.",
        "tags": ["slo", "slokit", spec.service],
        "editable": False,
        "timezone": "utc",
        "refresh": "1m",
        "schemaVersion": SCHEMA_VERSION,
        "time": {"from": "now-7d", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "label": "Prometheus",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {},
                    "hide": 0,
                }
            ]
        },
        "annotations": {
            "list": [
                {
                    "name": "Budget burn alerts",
                    "datasource": DATASOURCE,
                    "enable": True,
                    "iconColor": "red",
                    "expr": f'ALERTS{{alertstate="firing",service="{spec.service}"}}',
                    "titleFormat": "{{alertname}} ({{severity}})",
                    "tagKeys": "slo,severity",
                }
            ]
        },
        "links": [],
        "panels": panels,
    }
