"""Source eligibility and data-quality rules."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config"


def _allowlist() -> dict:
    return json.loads((CONFIG / "source_allowlist.json").read_text(encoding="utf-8"))


def source_class(source: str) -> str:
    data = _allowlist()
    for key in ("decision_eligible", "crosscheck_only", "discovery_only"):
        if source in data[key]:
            return key
    return "unlisted"


def numeric_weight(source: str) -> float:
    return 1.0 if source_class(source) == "decision_eligible" else 0.0


def assert_numeric_source(source: str) -> None:
    if numeric_weight(source) == 0:
        raise ValueError(f"NO-NEWS NUMERICS: {source} is not decision eligible")


def completeness(product: dict, availability: dict[str, float]) -> float:
    total = used = 0.0
    for variable, rule in product.items():
        weight = float(rule["weight"])
        total += weight
        used += weight * max(0.0, min(1.0, float(availability.get(variable, 0.0))))
    return round(100.0 * used / total, 1) if total else 100.0


def critical_gaps(product: dict, availability: dict[str, float]) -> list[str]:
    return [name for name, rule in product.items() if rule.get("critical") and availability.get(name, 0) <= 0]
