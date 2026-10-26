# ADR 0001: Multi-window, multi-burn-rate alerts

| Status | Accepted |
| --- | --- |

## Context

Teams alerted on raw error rate with a static threshold. A low threshold paged on brief
blips that cost almost no budget. A high one stayed silent through slow degradations that
quietly spent the whole month's budget.

## Decision

Every SLO gets two alerts generated from the same policy, following the SRE workbook.

- A page when 14.4x is sustained over 1h and 5m, or 6x over 6h and 30m.
- A ticket when 3x is sustained over 1d and 2h, or 1x over 3d and 6h.

Each condition requires both windows above the threshold. Severity is a label, and
Alertmanager decides who is interrupted.

## Consequences

- Pages map to budget actually at risk, so a page always deserves a human.
- Seven recording rules per SLO keep alert evaluation cheap, at the cost of more series.
- The burn rates assume a 30 day window. For 28 day SLOs they spend slightly more budget
  before firing (2.14% instead of 2% for the fastest page), which we accept for one shared
  policy.
- Objectives below 93.06% cannot use this policy, and slokit rejects them.
