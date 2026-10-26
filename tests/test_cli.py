from __future__ import annotations

from pathlib import Path

import pytest

from slokit.cli import main
from tests.conftest import GENERATED, SPECS


def test_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(SPECS)]) == 0
    assert capsys.readouterr().out.count("ok  ") == 3


def test_generate_then_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", str(SPECS), "-o", str(tmp_path)]) == 0
    assert "recording_rules=42 alert_rules=6" in capsys.readouterr().out
    assert main(["generate", str(SPECS), "-o", str(tmp_path), "--check"]) == 0


def test_check_fails_on_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["generate", str(SPECS), "-o", str(tmp_path)])
    (tmp_path / "policies" / "search.md").write_text("edited by hand\n")
    assert main(["generate", str(SPECS), "-o", str(tmp_path), "--check"]) == 1
    assert "stale" in capsys.readouterr().err


def test_committed_examples_are_up_to_date() -> None:
    assert main(["generate", str(SPECS), "-o", str(GENERATED), "--check"]) == 0


def test_invalid_spec_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "bad.yaml").write_text("apiVersion: slokit/v1\nservice: x\n")
    assert main(["validate", str(tmp_path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_burn_rates_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["burn-rates", "--objective", "99.9", "--window", "30d"]) == 0
    out = capsys.readouterr().out
    assert "1.44%" in out and "2%" in out and "50h" in out


def test_burn_rates_rejects_garbage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["burn-rates", "--objective", "high"]) == 2
