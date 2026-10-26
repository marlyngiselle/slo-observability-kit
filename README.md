<div align="center">

<img src=".github/assets/slo-observability-kit-banner.svg" alt="slo-observability-kit" width="100%">

<h1>slo-observability-kit</h1>

<p>Describe an SLO in a short YAML file. Get the recording rules, multi-window burn-rate alerts, Grafana dashboard and error-budget policy that make it real.</p>

<p>
<img src="https://img.shields.io/badge/Python-3.11%2B-0b1f4d?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+">
<img src="https://img.shields.io/badge/Prometheus-rules%20%2B%20alerts-14347f?style=for-the-badge&logo=prometheus&logoColor=white" alt="Prometheus">
<img src="https://img.shields.io/badge/Grafana-dashboards-1d47a6?style=for-the-badge&logo=grafana&logoColor=white" alt="Grafana">
<img src="https://img.shields.io/badge/OpenTelemetry-collector-2456c8?style=for-the-badge&logo=opentelemetry&logoColor=white" alt="OpenTelemetry">
<img src="https://img.shields.io/badge/CI-promtool%20checked-3a6fe0?style=for-the-badge&logo=githubactions&logoColor=white" alt="CI">
<img src="https://img.shields.io/badge/License-MIT-5b8def?style=for-the-badge" alt="MIT license">
</p>

</div>

## In numbers

| What | Count | Measured with |
| --- | --- | --- |
| Example services and SLOs | 3 | `slokit validate examples/slos` |
| Prometheus rules generated | 48 (42 recording, 6 alerting) | `slokit generate examples/slos` |
| Error ratio windows per SLO | 7 (5m to 3d) plus the SLO period | `SLI_WINDOWS` in `src/slokit/burnrate.py` |
| Burn-rate window pairs | 4 (2 page, 2 ticket) | `DEFAULT_POLICY` in `src/slokit/burnrate.py` |
| Dashboard panels generated | 21 across 3 dashboards | `examples/generated/grafana/dashboards/` |
| Tests | 97, all passing | `pytest` |

## What it is

A small, typed generator and a local stack for running SLOs the way the SRE workbook
describes them. Teams describe what good looks like for their service. slokit turns that
into PromQL that pages only when the error budget is genuinely at risk, a dashboard that
shows how much budget is left, and a written policy that says what happens when it runs out.

It is built for platform teams who want every service to get the same, reviewed alerting
math instead of a hand-copied rule file per team.

## Architecture

```mermaid
flowchart LR
    subgraph SPEC["fa:fa-file-code Specs"]
        Y1["checkout-api.yaml<br/>availability 99.9%"]
        Y2["search.yaml<br/>latency p95 under 400 ms"]
        Y3["ingestion-pipeline.yaml<br/>freshness 99.5%"]
    end

    subgraph GEN["fa:fa-gears slokit"]
        V["validate<br/>pydantic schema"]
        R["render<br/>burn-rate math"]
    end

    subgraph OUT["fa:fa-box-archive Generated and committed"]
        PR["Recording rules<br/>7 windows + period"]
        AL["Burn-rate alerts<br/>page and ticket"]
        DB["Grafana dashboard"]
        PO["Error-budget policy"]
    end

    subgraph RUN["fa:fa-server Runtime"]
        APP["Workloads<br/>OTLP and /metrics"]
        OC["OpenTelemetry Collector<br/>PII scrub, k8s metadata"]
        PM["Prometheus"]
        AM["Alertmanager<br/>routing and inhibition"]
        GF["Grafana"]
        TR["Tracing backend"]
    end

    Y1 & Y2 & Y3 --> V --> R
    R --> PR & AL & DB & PO
    APP --> OC
    OC -- "remote write" --> PM
    OC -- "OTLP traces" --> TR
    PR & AL --> PM
    PM -- "alerts" --> AM
    DB --> GF
    PM --> GF
    AM -- "page" --> PG["fa:fa-bell On-call pager"]
    AM -- "ticket" --> TK["fa:fa-ticket Team queue"]

    classDef spec fill:#0b1f4d,stroke:#5b8def,stroke-width:2px,color:#ffffff
    classDef gen fill:#14347f,stroke:#9cc3ff,stroke-width:2px,color:#ffffff
    classDef out fill:#2456c8,stroke:#9cc3ff,stroke-width:2px,color:#ffffff
    classDef run fill:#1d47a6,stroke:#9cc3ff,stroke-width:2px,color:#ffffff
    classDef page fill:#b3261e,stroke:#ffb4ab,stroke-width:2px,color:#ffffff
    classDef ticket fill:#8a5a00,stroke:#ffd27a,stroke-width:2px,color:#ffffff
    class Y1,Y2,Y3 spec
    class V,R gen
    class PR,AL,DB,PO out
    class APP,OC,PM,AM,GF,TR run
    class PG page
    class TK ticket
    style SPEC fill:#eaf1ff,stroke:#0b1f4d,stroke-width:2px,color:#0b1f4d
    style GEN fill:#eaf1ff,stroke:#14347f,stroke-width:2px,color:#0b1f4d
    style OUT fill:#eaf1ff,stroke:#2456c8,stroke-width:2px,color:#0b1f4d
    style RUN fill:#eaf1ff,stroke:#1d47a6,stroke-width:2px,color:#0b1f4d
```

## From spec to page

```mermaid
sequenceDiagram
    autonumber
    actor Eng as Service team
    participant CLI as slokit
    participant CI as CI pipeline
    participant P as Prometheus
    participant A as Alertmanager
    actor On as On-call

    Eng->>CLI: slokit generate examples/slos
    CLI-->>Eng: rules, dashboard, policy
    Eng->>CI: pull request with spec and output
    CI->>CI: ruff, mypy, pytest, drift check
    CI->>CI: promtool check rules, amtool check-config
    CI-->>Eng: green, ready to merge
    P->>P: record error ratio every 30s on 7 windows
    P->>A: 1h and 5m both above 14.4x budget
    A->>On: page routed by team label
    A-->>Eng: ticket muted while the page fires
```

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

slokit validate examples/slos
slokit generate examples/slos -o examples/generated
slokit burn-rates --objective 99.9 --window 28d

docker compose up -d
```

| Open | For |
| --- | --- |
| <http://localhost:3000> | Grafana, folder "SLOs", one dashboard per service |
| <http://localhost:9090/alerts> | Prometheus rules and alert states |
| <http://localhost:9093> | Alertmanager routing and silences |
| <http://localhost:16686> | Jaeger, traces received through the collector |

Simulate an incident by raising the checkout error ratio to 5%. That is 50 times the budget,
and the page alert fires within about 20 minutes.

```bash
CHECKOUT_ERROR_RATIO=0.05 docker compose up -d demo-service
```

## A spec

```yaml
apiVersion: slokit/v1
service: checkout-api
owner: payments-team
alerting:
  page: { team: payments-oncall, channel: "#payments-oncall" }
  ticket: { team: payments-team }
  runbook_url: https://runbooks.example.com/checkout-api
slos:
  - name: availability
    description: Checkout requests that do not fail with a server error.
    objective: 99.9
    window: 28d
    sli:
      type: availability
      template:
        metric: http_server_requests_total
        selector: service="checkout-api"
        good_filter: code!~"5.."
```

| SLI type | Template inputs | Good event |
| --- | --- | --- |
| `availability` | `metric`, `selector`, `good_filter` | A request matching `good_filter` |
| `latency` | `metric`, `selector`, `le` | A request in the histogram bucket `le` |
| `freshness` | `metric`, `selector`, `max_age_seconds` | A minute in which the last success is recent enough |
| any | `queries.good`, `queries.total` | Whatever your PromQL says, with a `{{window}}` placeholder |

## Burn-rate policy

| Severity | Burn rate | Long / short window | Error ratio at 99.9% | Budget spent when it fires (30d) | Budget gone in |
| --- | --- | --- | --- | --- | --- |
| page | 14.4x | 1h / 5m | 1.44% | 2% | 50 h |
| page | 6x | 6h / 30m | 0.6% | 5% | 120 h |
| ticket | 3x | 1d / 2h | 0.3% | 10% | 240 h |
| ticket | 1x | 3d / 6h | 0.1% | 10% | 720 h |

Both windows must be above the threshold. The long one proves the burn matters, the short
one proves it is still happening. The derivation, detection times and the 28 day variant
are in [docs/burn-rate-math.md](docs/burn-rate-math.md).

## What gets generated

| Output | Path | Highlights |
| --- | --- | --- |
| Recording rules | `prometheus/rules/<service>.rules.yaml` | `slo:sli_error:ratio_rate{5m..3d}`, period ratio, objective, budget, burn rates |
| Alert rules | same file | One page and one ticket alert per SLO, `severity`, `team`, `runbook_url`, `dashboard` |
| Dashboard | `grafana/dashboards/<service>.json` | SLI over the period, budget remaining, burn rate per alert window with threshold lines |
| Policy | `policies/<service>.md` | Budget in minutes, routing table, actions at 50%, 25% and 0% budget left |

An empty good series is treated as zero good events (`or vector(0)`), so a total outage
pages instead of returning no data.

## Delivery

```mermaid
flowchart LR
    PUSH["fa:fa-code-branch push or PR"]:::trigger --> PY

    subgraph PY["python job, 3.11 and 3.12"]
        direction LR
        RUFF["ruff check<br/>ruff format"] --> MYPY["mypy strict"] --> TEST["pytest<br/>97 tests"] --> DRIFT["regenerate<br/>git diff --exit-code"]
    end

    subgraph PT["prometheus job"]
        direction LR
        RULES["promtool<br/>check rules"] --> CONF["promtool<br/>check config"] --> AMT["amtool<br/>check-config"] --> JSON["dashboards<br/>json.tool"]
    end

    PY --> PT --> OK["fa:fa-circle-check mergeable"]:::done

    classDef trigger fill:#0b1f4d,stroke:#5b8def,stroke-width:2px,color:#ffffff
    classDef done fill:#2456c8,stroke:#9cc3ff,stroke-width:2px,color:#ffffff
    classDef step fill:#14347f,stroke:#9cc3ff,stroke-width:2px,color:#ffffff
    class RUFF,MYPY,TEST,DRIFT,RULES,CONF,AMT,JSON step
    style PY fill:#eaf1ff,stroke:#14347f,stroke-width:2px,color:#0b1f4d
    style PT fill:#eaf1ff,stroke:#2456c8,stroke-width:2px,color:#0b1f4d
```

Every action is pinned to a commit SHA and the job runs with `contents: read` only.

## Before you rely on it

> [!WARNING]
> Files under `examples/generated/` are overwritten on every run and CI fails if they drift.
> Change the spec, never the output.

> [!CAUTION]
> Raw `good` and `total` queries must each return one series without labels. A `sum by (...)`
> silently breaks the ratio and the zero-good guard. Wrap them in a plain `sum()`.

> [!IMPORTANT]
> A freshness SLI cannot see a pipeline whose timestamp metric disappears altogether. Pair it
> with an `absent()` alert on the same metric.

> [!NOTE]
> The page goes to the receiver matching the `team` label. A team missing from
> `alertmanager/alertmanager.yml` falls through to the default receiver, so add the route in the
> same pull request.

## Repository map

| Path | What lives there |
| --- | --- |
| `src/slokit/` | Schema (`models.py`), math (`burnrate.py`), rules, dashboards, policies, CLI |
| `tests/` | Burn-rate math, schema errors, PromQL parsing, golden files, CLI |
| `examples/slos/` | Three synthetic services, one per SLI type |
| `examples/generated/` | Committed output, checked for drift in CI |
| `otel/` | Collector config (production shape) and the local overlay |
| `prometheus/` | Local Prometheus config, loads the generated rules |
| `alertmanager/` | Routing tree, inhibition rules, working-hours interval for tickets |
| `grafana/` | Datasource and dashboard provisioning |
| `demo/` | Synthetic workload that emits the three example SLIs |
| `docs/` | Primer, burn-rate math, onboarding, runbook template, ADRs |

## Documentation

| Document | Read it to |
| --- | --- |
| [SLO primer](docs/slo-primer.md) | Agree on SLI, SLO, error budget and burn rate in five minutes |
| [Burn-rate math](docs/burn-rate-math.md) | See why 14.4x, how fast each alert fires and what it costs |
| [Onboard a service](docs/onboarding.md) | Go from no SLO to merged alerts in three steps |
| [Incident runbook template](docs/runbooks/incident-response-template.md) | Respond to a page with a plan |
| [ADR 0001](docs/adr/0001-multi-window-multi-burn-rate-alerts.md) | Why multi-window, multi-burn-rate alerts |
| [ADR 0002](docs/adr/0002-time-weighted-period-sli.md) | Why the period SLI is time-weighted |
| [ADR 0003](docs/adr/0003-generate-rules-from-specs.md) | Why rules are generated and committed |

<div align="center">
<sub>MIT licensed. Built and maintained by Giselle Da Costa.</sub>
</div>
