"""SLO specification schema and loader.

A spec file describes one service and one or more SLOs. Every field is checked
before anything is generated, and unknown keys are rejected so a typo cannot
silently drop an alert.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)

from slokit.burnrate import DEFAULT_POLICY, fmt, max_burn_rate

WINDOW_PLACEHOLDER = "{{window}}"

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"
Slug = Annotated[str, Field(pattern=SLUG_PATTERN)]
LabelName = Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")]
RESERVED_LABELS = frozenset({"service", "slo", "severity", "team", "alertname"})


class SpecError(Exception):
    """A spec file could not be loaded. The message is meant for humans."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# SLI sources ----------------------------------------------------------------


class RawQueries(_Strict):
    """Hand-written PromQL. Both queries must return one series without labels."""

    good: str
    total: str

    @field_validator("good", "total")
    @classmethod
    def _has_window(cls, value: str) -> str:
        if WINDOW_PLACEHOLDER not in value:
            raise ValueError(
                f"query must contain the {WINDOW_PLACEHOLDER} placeholder so slokit can "
                "render it for every window, for example rate(metric[{{window}}])"
            )
        return value.strip()


class AvailabilityTemplate(_Strict):
    """Good events are requests whose labels match good_filter."""

    metric: str = Field(pattern=r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
    selector: str
    good_filter: str


class LatencyTemplate(_Strict):
    """Good events are requests that land in the histogram bucket le."""

    metric: str = Field(
        pattern=r"^[a-zA-Z_:][a-zA-Z0-9_:]*$",
        description="Histogram base name, without the _bucket or _count suffix.",
    )
    selector: str
    le: str = Field(description="Bucket boundary, exactly as exposed in the le label.")
    percentile: int | None = Field(default=None, ge=1, le=99)

    @field_validator("metric")
    @classmethod
    def _no_suffix(cls, value: str) -> str:
        for suffix in ("_bucket", "_count", "_sum"):
            if value.endswith(suffix):
                raise ValueError(f"use the histogram base name, without the {suffix} suffix")
        return value

    @field_validator("le")
    @classmethod
    def _numeric_le(cls, value: str) -> str:
        try:
            float(value)
        except ValueError as exc:
            raise ValueError(f'le must be a number such as "0.4", got {value!r}') from exc
        return value


class FreshnessTemplate(_Strict):
    """Good events are evaluation steps where the data is younger than max_age_seconds."""

    metric: str = Field(
        pattern=r"^[a-zA-Z_:][a-zA-Z0-9_:]*$",
        description="Gauge holding the unix timestamp of the last successful run.",
    )
    selector: str
    max_age_seconds: int = Field(gt=0)
    resolution: Literal["30s", "1m", "5m"] = "1m"


_TEMPLATE_KEYS = {"good_filter": "availability", "le": "latency", "max_age_seconds": "freshness"}


def _template_kind(value: Any) -> str | None:
    """Pick the template model from the one key that only it has."""
    if isinstance(value, BaseModel):
        return {
            AvailabilityTemplate: "availability",
            LatencyTemplate: "latency",
            FreshnessTemplate: "freshness",
        }.get(type(value))
    if isinstance(value, dict):
        kinds = [kind for key, kind in _TEMPLATE_KEYS.items() if key in value]
        return kinds[0] if len(kinds) == 1 else None
    return None


Template = Annotated[
    Annotated[AvailabilityTemplate, Tag("availability")]
    | Annotated[LatencyTemplate, Tag("latency")]
    | Annotated[FreshnessTemplate, Tag("freshness")],
    Discriminator(
        _template_kind,
        custom_error_type="template_kind",
        custom_error_message=(
            "template must contain exactly one of good_filter (availability), "
            "le (latency) or max_age_seconds (freshness)"
        ),
    ),
]


class SLI(_Strict):
    type: Literal["availability", "latency", "freshness"]
    queries: RawQueries | None = None
    template: Template | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SLI:
        if (self.queries is None) == (self.template is None):
            raise ValueError("set exactly one of 'queries' (raw PromQL) or 'template'")
        templates: dict[str, type[BaseModel]] = {
            "availability": AvailabilityTemplate,
            "latency": LatencyTemplate,
            "freshness": FreshnessTemplate,
        }
        expected = templates[self.type]
        if self.template is not None and not isinstance(self.template, expected):
            raise ValueError(
                f"type {self.type} needs the {self.type} template fields: "
                f"{', '.join(expected.__pydantic_fields__)}"
            )
        return self

    def good_query(self) -> str:
        return self._render()[0]

    def total_query(self) -> str:
        return self._render()[1]

    def _render(self) -> tuple[str, str]:
        if self.queries is not None:
            return self.queries.good, self.queries.total
        t = self.template
        w = WINDOW_PLACEHOLDER
        if isinstance(t, AvailabilityTemplate):
            good = f"sum(rate({t.metric}{{{_join(t.selector, t.good_filter)}}}[{w}]))"
            total = f"sum(rate({t.metric}{{{t.selector}}}[{w}]))"
            return good, total
        if isinstance(t, LatencyTemplate):
            le = f'le="{t.le}"'
            good = f"sum(rate({t.metric}_bucket{{{_join(t.selector, le)}}}[{w}]))"
            total = f"sum(rate({t.metric}_count{{{t.selector}}}[{w}]))"
            return good, total
        if isinstance(t, FreshnessTemplate):
            age = f"(time() - max({t.metric}{{{t.selector}}}))"
            good = f"sum_over_time(({age} < bool {t.max_age_seconds})[{w}:{t.resolution}])"
            total = f"count_over_time({age}[{w}:{t.resolution}])"
            return good, total
        raise AssertionError("unreachable: validated by _exactly_one_source")


def _join(*matchers: str) -> str:
    return ",".join(m.strip() for m in matchers if m.strip())


# SLOs and routing -----------------------------------------------------------


class Route(_Strict):
    team: Slug
    channel: str | None = None


class Alerting(_Strict):
    page: Route
    ticket: Route
    runbook_url: str = Field(pattern=r"^https?://\S+$")


class SLO(_Strict):
    name: Slug
    description: str
    sli: SLI
    objective: Decimal = Field(gt=Decimal(50), lt=Decimal(100), description="Percent, e.g. 99.9")
    window: Literal["28d", "30d"] = "28d"

    @property
    def objective_ratio(self) -> Decimal:
        return self.objective / Decimal(100)

    @property
    def error_budget(self) -> Decimal:
        return Decimal(1) - self.objective_ratio

    @model_validator(mode="after")
    def _alerts_can_fire(self) -> SLO:
        steepest = max_burn_rate(DEFAULT_POLICY)
        needed = steepest * self.error_budget
        if needed >= 1:
            floor = (Decimal(1) - Decimal(1) / steepest) * 100
            raise ValueError(
                f"objective {fmt(self.objective)}% leaves a {fmt(self.error_budget * 100)}% "
                f"error budget, so a {fmt(steepest)}x burn would need an error ratio of "
                f"{fmt(needed * 100)}% and the page alert could never fire. Use an objective "
                f"above {floor:.2f}%"
            )
        return self


class ServiceSpec(_Strict):
    api_version: Literal["slokit/v1"] = Field(alias="apiVersion")
    service: Slug
    owner: Slug
    labels: dict[LabelName, str] = Field(default_factory=dict)
    alerting: Alerting
    slos: list[SLO] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def _no_reserved(cls, value: dict[str, str]) -> dict[str, str]:
        clash = sorted(RESERVED_LABELS.intersection(value))
        if clash:
            raise ValueError(f"labels {clash} are set by slokit and cannot be overridden")
        return value

    @model_validator(mode="after")
    def _unique_slo_names(self) -> ServiceSpec:
        seen: set[str] = set()
        for slo in self.slos:
            if slo.name in seen:
                raise ValueError(f"SLO name {slo.name!r} is used twice in this service")
            seen.add(slo.name)
        return self


# Loading --------------------------------------------------------------------


def _format_errors(source: str, err: ValidationError) -> str:
    lines = [f"{source}: {err.error_count()} problem(s) in the SLO spec"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "string_pattern_mismatch":
            ctx = e.get("ctx") or {}
            hint = (
                "use 2 to 63 lowercase letters, digits or hyphens, starting with a letter"
                if ctx.get("pattern") == SLUG_PATTERN
                else f"must match {ctx.get('pattern')}"
            )
            msg = f"{e['input']!r} is not allowed here, {hint}"
        elif e["type"] == "extra_forbidden":
            msg = "unknown field (check the spelling, unknown keys are rejected)"
        lines.append(f"  - {loc or '(root)'}: {msg}")
    return "\n".join(lines)


def parse_spec(text: str, source: str = "<string>") -> ServiceSpec:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{source}: not valid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{source}: expected a mapping at the top level")
    try:
        return ServiceSpec.model_validate(data)
    except ValidationError as exc:
        raise SpecError(_format_errors(source, exc)) from exc


def load_spec(path: Path) -> ServiceSpec:
    return parse_spec(path.read_text(encoding="utf-8"), source=str(path))


def discover(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into their *.yaml and *.yml files, sorted."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted([*path.glob("*.yaml"), *path.glob("*.yml")]))
        elif path.is_file():
            files.append(path)
        else:
            raise SpecError(f"{path}: no such file or directory")
    if not files:
        raise SpecError("no SLO spec files found")
    return files


def load_all(paths: Iterable[Path]) -> list[tuple[Path, ServiceSpec]]:
    """Load every spec, collecting all errors before failing."""
    loaded: list[tuple[Path, ServiceSpec]] = []
    errors: list[str] = []
    owners: dict[str, Path] = {}
    for path in discover(paths):
        try:
            spec = load_spec(path)
        except SpecError as exc:
            errors.append(str(exc))
            continue
        if spec.service in owners:
            errors.append(
                f"{path}: service {spec.service!r} is already defined in {owners[spec.service]}"
            )
            continue
        owners[spec.service] = path
        loaded.append((path, spec))
    if errors:
        raise SpecError("\n".join(errors))
    return loaded
