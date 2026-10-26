# Runbook: <service> <slo>

Copy this file per SLO. The alert's `runbook_url` points at the section named after the SLO.

## At a glance

| Field | Value |
| --- | --- |
| Alert | `<Service><Slo>BudgetBurn` |
| Severity | page (14.4x or 6x) or ticket (3x or 1x) |
| Owner | `<team>` |
| Dashboard | `/d/slo-<service>` |
| Dependencies | upstream services, databases, queues |

## First five minutes

1. Acknowledge the page and say so in the incident channel.
2. Open the dashboard. Note the burn rate on the 1h and 6h windows and the budget left.
3. Decide the severity of the incident, not of the alert:

   | Situation | Incident level | Next step |
   | --- | --- | --- |
   | Users cannot complete the journey | SEV1 | Name an incident commander, open a bridge |
   | Degraded for some users, budget burning fast | SEV2 | Commander is the on-call engineer |
   | Slow burn, no visible user impact yet | SEV3 | Handle in working hours, keep the ticket |

4. Check what changed in the last two hours, namely deploys, feature flags, config,
   infrastructure and traffic.

## Mitigate first, diagnose second

| Signal | Likely cause | Mitigation |
| --- | --- | --- |
| Errors started with a deploy | Regression | Roll back, then investigate |
| Errors on one zone or node pool | Infrastructure | Drain or shift traffic away |
| Errors follow traffic growth | Saturation | Scale out, shed low-priority load |
| Errors match a dependency | Upstream outage | Fail over, degrade gracefully, notify its owner |

## Communicate

- Every 30 minutes during a SEV1 or SEV2, post status, impact, next step and next
  update time.
- Tell support what users see, not what is broken inside.

## Close

1. Confirm the short window error ratio is back under the threshold and the alert resolved.
2. Record the budget spent, read from the "Error budget remaining" panel before and after.
3. Schedule a blameless postmortem within five working days for any SEV1 or SEV2, or for
   any incident that spent more than 20% of the budget.

## Postmortem skeleton

| Section | Content |
| --- | --- |
| Summary | Two sentences a non-engineer understands |
| Impact | Users affected, duration, budget spent |
| Timeline | Detection, escalation, mitigation, resolution, in UTC |
| Contributing factors | Technical and organisational, no names |
| What went well | Keep doing it |
| Action items | Owner and due date for each, tracked to completion |
