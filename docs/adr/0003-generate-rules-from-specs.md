# ADR 0003: Generate rules from specs and commit the output

| Status | Accepted |
| --- | --- |

## Context

Hand-written burn-rate rules are long, repetitive and easy to get subtly wrong, such as a
window copied from another SLO, a threshold computed for a different objective or a missing
label that sends a page to the wrong team.

## Decision

- Teams write a short YAML spec per service. A validated schema rejects unknown keys and
  objectives the policy cannot serve.
- `slokit generate` produces recording rules, alerts, a Grafana dashboard and an
  error-budget policy, deterministically.
- Generated files are committed. CI regenerates them and fails on any difference, then
  validates them with `promtool` and `amtool`.

## Consequences

- Reviewers see the exact PromQL that will run, in the same pull request as the spec.
- Changing the policy is one code change and one regeneration, applied to every service
  at once and visible as a diff.
- Generated files must not be edited by hand. Each one says so in its header.
- The generator is now a dependency. It is small, typed and tested against golden files.
