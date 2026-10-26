# SLO primer

A short, opinionated refresher. It covers what this kit assumes you already agree on.

## The four words

| Term | Meaning | Example |
| --- | --- | --- |
| SLI | A ratio of good events to valid events, measured where the user feels it | Checkout requests that did not return a 5xx, divided by all checkout requests |
| SLO | The target for that ratio over a rolling window | 99.9% over 28 days |
| Error budget | One minus the SLO. The amount of unreliability you are allowed to spend | 0.1% of requests, about 40 minutes of full outage in 28 days |
| Burn rate | How fast the budget is being spent, relative to spending it exactly over the window | 1x lasts 28 days, 14.4x empties it in under two days |

## Rules of thumb

1. Measure at the edge. A load balancer or gateway sees the timeouts your application never logs.
2. Pick the window your planning runs on. 28 days holds the same number of weekends every
   time, 30 days lines up with monthly reporting.
3. Start below what you achieve today. An objective you already miss teaches the team to
   ignore it.
4. Fewer SLOs, read more often. One per user journey is plenty to start with.
5. Latency percentiles become SLOs by flipping them around. "p95 under 400 ms" is the
   same promise as "95% of requests under 400 ms", and only the second one can be summed
   across instances and burned like a budget.

## What an SLO is not

- Not an SLA. An SLA is a contract with penalties and should sit comfortably below the SLO.
- Not a dashboard. If nobody changes what they ship when the budget runs out, it is a chart.
- Not a promise of 100%. Every extra nine costs roughly ten times more, and users cannot
  tell the difference past the reliability of their own network.

## Where to go next

- [Burn-rate math](burn-rate-math.md) for how alerts are derived.
- [Onboarding a service](onboarding.md) to write your first spec.
