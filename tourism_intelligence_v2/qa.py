from __future__ import annotations

from typing import Any, Iterable


def require_keys(payload: dict[str, Any], keys: Iterable[str], context: str = "payload") -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ValueError(f"{context} missing required keys: {', '.join(missing)}")


def coverage(successful: int, eligible: int) -> float | None:
    if eligible <= 0:
        return None
    return successful / eligible


def gate(coverage_value: float | None, threshold: float) -> bool:
    return coverage_value is not None and coverage_value >= threshold
