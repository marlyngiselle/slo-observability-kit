# ADR 0002: Period SLI from recorded 5m ratios

| Status | Accepted |
| --- | --- |

## Context

Dashboards need the SLI over the whole SLO window (28 or 30 days). Computing it directly,
for example `rate(http_server_requests_total[28d])`, scans a month of raw samples on every
refresh and gets slower as traffic grows.

## Decision

The period ratio is the average of the recorded 5 minute error ratio over the window.

```promql
sum_over_time(slo:sli_error:ratio_rate5m{service="checkout-api",slo="availability"}[28d])
/
count_over_time(slo:sli_error:ratio_rate5m{service="checkout-api",slo="availability"}[28d])
```

## Consequences

- One sample per evaluation interval instead of every raw sample. Fast at any traffic.
- The result is time-weighted, not request-weighted. A bad night with little traffic
  counts as much as a bad afternoon at peak. For user-facing SLOs that is usually a
  conservative error, and it is the one we choose.
- Alerts never depend on it. They use the short recorded windows only.
- Gaps in the 5m series (Prometheus restarts) drop out of both sums and do not count as good.
