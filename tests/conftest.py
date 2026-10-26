from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "examples" / "slos"
GENERATED = ROOT / "examples" / "generated"

MINIMAL = """\
apiVersion: slokit/v1
service: demo-api
owner: demo-team
alerting:
  page: {team: demo-oncall}
  ticket: {team: demo-team}
  runbook_url: https://runbooks.example.com/demo-api
slos:
  - name: availability
    description: Requests that succeed.
    objective: 99.9
    sli:
      type: availability
      template:
        metric: http_requests_total
        selector: job="demo-api"
        good_filter: code!~"5.."
"""


@pytest.fixture
def minimal_yaml() -> str:
    return MINIMAL
