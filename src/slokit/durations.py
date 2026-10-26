"""Prometheus-style durations ("5m", "1h", "28d") as plain seconds."""

from __future__ import annotations

import re

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_PATTERN = re.compile(r"^([1-9][0-9]*)([smhdw])$")


def parse_duration(value: str) -> int:
    """Return the number of seconds in a single-unit Prometheus duration.

    >>> parse_duration("6h")
    21600
    """
    match = _PATTERN.match(value)
    if match is None:
        raise ValueError(
            f"invalid duration {value!r}: expected a positive integer followed by one of "
            f"{', '.join(_UNITS)} (for example 5m, 1h, 28d)"
        )
    amount, unit = match.groups()
    return int(amount) * _UNITS[unit]


def hours(value: str) -> float:
    """Return a duration expressed in hours."""
    return parse_duration(value) / 3600
