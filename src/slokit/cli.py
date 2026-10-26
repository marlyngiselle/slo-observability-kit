"""Command line entry point: slokit validate | generate | burn-rates."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from slokit import __version__
from slokit.burnrate import DEFAULT_POLICY, fmt
from slokit.generate import diff, render, write
from slokit.models import SpecError, load_all


def _cmd_validate(args: argparse.Namespace) -> int:
    specs = load_all(args.paths)
    for path, spec in specs:
        names = ", ".join(s.name for s in spec.slos)
        print(f"ok  {path}  service={spec.service}  slos={names}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    output = render(load_all(args.paths))
    if args.check:
        stale = diff(output, args.out)
        for rel in stale:
            print(f"stale  {args.out / rel}", file=sys.stderr)
        if stale:
            print("run 'slokit generate' and commit the result", file=sys.stderr)
            return 1
        print(f"up to date  {len(output.files)} files in {args.out}")
        return 0
    write(output, args.out)
    print(
        f"wrote {len(output.files)} files to {args.out}  "
        f"slos={output.slos} recording_rules={output.recording_rules} "
        f"alert_rules={output.alert_rules} dashboards={output.dashboards}"
    )
    return 0


def _cmd_burn_rates(args: argparse.Namespace) -> int:
    try:
        objective = Decimal(args.objective)
    except InvalidOperation:
        print(f"error: objective {args.objective!r} is not a number", file=sys.stderr)
        return 2
    budget = 1 - objective / 100
    print(f"objective {fmt(objective)}%  window {args.window}  error budget {fmt(budget * 100)}%")
    print(
        f"{'severity':<8} {'burn':>6} {'windows':>9} {'error ratio >':>14} "
        f"{'budget spent':>13} {'exhausted in':>13}"
    )
    for w in DEFAULT_POLICY:
        spent = (w.budget_consumed(args.window) * 100).quantize(Decimal("0.01"))
        hours = w.time_to_exhaustion_hours(args.window).quantize(Decimal("0.1"))
        print(
            f"{w.severity.value:<8} {fmt(w.burn_rate) + 'x':>6} "
            f"{w.long_window + '/' + w.short_window:>9} "
            f"{fmt(w.threshold(budget) * 100) + '%':>14} {fmt(spent) + '%':>13} "
            f"{fmt(hours) + 'h':>13}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slokit",
        description="Generate SLO recording rules, burn-rate alerts, dashboards and policies.",
    )
    parser.add_argument("--version", action="version", version=f"slokit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check SLO spec files and report every problem")
    validate.add_argument("paths", nargs="+", type=Path, help="spec files or directories")
    validate.set_defaults(func=_cmd_validate)

    generate = sub.add_parser("generate", help="write rules, dashboards and policies")
    generate.add_argument("paths", nargs="+", type=Path, help="spec files or directories")
    generate.add_argument("-o", "--out", type=Path, default=Path("generated"), help="output dir")
    generate.add_argument(
        "--check", action="store_true", help="fail if the output dir is not up to date"
    )
    generate.set_defaults(func=_cmd_generate)

    burn = sub.add_parser("burn-rates", help="print the alert thresholds for an objective")
    burn.add_argument("--objective", required=True, help="percent, for example 99.9")
    burn.add_argument("--window", choices=["28d", "30d"], default="28d")
    burn.set_defaults(func=_cmd_burn_rates)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
