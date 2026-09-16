from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1"}


def load_registry(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_registry(payload)
    return payload


def validate_registry(payload: dict[str, Any]) -> None:
    version = payload.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported source registry schema_version: {version}")
    seen: set[str] = set()
    for source in payload.get("sources", []):
        source_id = source.get("source_id")
        if not source_id or source_id in seen:
            raise ValueError(f"invalid or duplicate source_id: {source_id}")
        seen.add(source_id)
        ttl = source.get("ttl_minutes")
        if ttl is not None and (not isinstance(ttl, (int, float)) or ttl <= 0):
            raise ValueError(f"invalid ttl_minutes for {source_id}")
        if source.get("evidence_class") not in {"DIRECT", "PROXY", "LEADING", "INFERENCE", "UNKNOWN"}:
            raise ValueError(f"invalid evidence_class for {source_id}")


def freshness(age_minutes: float, ttl_minutes: float | None) -> dict[str, Any]:
    if ttl_minutes is None:
        return {"score": None, "state": "UNKNOWN_TTL", "age_minutes": age_minutes}
    score = math.exp(-max(0.0, age_minutes) / ttl_minutes)
    state = "FRESH" if age_minutes <= ttl_minutes else "STALE"
    return {"score": round(score, 4), "state": state, "age_minutes": round(age_minutes, 1), "ttl_minutes": ttl_minutes}


def age_minutes(observed_at: str, now: datetime) -> float:
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("observed_at must include timezone")
    return (now.astimezone(observed.tzinfo) - observed).total_seconds() / 60.0
