from __future__ import annotations

from typing import Any

STAGES = {"awareness", "consideration", "planning", "comparison", "inquiry", "booking", "pre_arrival", "in_destination", "post_trip"}
SIGNAL_TYPES = {"isolated_anecdote", "repeated_narrative", "promotion", "direct_public_statement"}


def validate_evidence(row: dict[str, Any]) -> dict[str, Any]:
    required = ("market", "language", "platform", "stage", "theme", "signal_type", "source_date", "evidence_class")
    missing = [key for key in required if not row.get(key)]
    if missing:
        raise ValueError(f"missing social evidence keys: {', '.join(missing)}")
    if row["stage"] not in STAGES:
        raise ValueError("invalid decision stage")
    if row["signal_type"] not in SIGNAL_TYPES:
        raise ValueError("invalid signal_type")
    if row["evidence_class"] not in {"DIRECT", "PROXY", "LEADING", "INFERENCE", "UNKNOWN"}:
        raise ValueError("invalid evidence_class")
    return row
