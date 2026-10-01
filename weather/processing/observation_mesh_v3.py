"""Weather Engine V3 shadow Observation Mesh.

This module is deliberately side-effect free. It does not replace Weather V2,
does not fetch external sources, and does not change production decisions.

Responsibilities:
- preserve source/evidence class boundaries
- enforce rights/lifecycle gates
- normalize observation receipts
- prevent null -> zero coercion
- group aliases/backends so URL count never becomes evidence count
- expose a shadow summary that can later feed Local Now / Nowcast after promotion
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

REGISTRY_PATH = Path("weather/config/observation_sources_v3.json")

EVIDENCE_CLASSES = {
    "GROUND_OBSERVED",
    "MARINE_GROUND_OBSERVED",
    "REMOTE_OBSERVED",
    "REMOTE_RENDERED_OBSERVED",
    "DERIVED_OBSERVATION",
    "OFFICIAL_FORECAST",
    "OFFICIAL_ALERT",
    "MODEL_FORECAST",
    "HISTORICAL_VALIDATION",
}
RIGHTS_STATES = {"CLEARED", "CONDITIONAL", "UNRESOLVED", "REJECTED"}
LIFECYCLE_STATES = {"DISCOVERED", "PROBE", "ARCHIVE_ONLY", "SHADOW", "ACTIVE", "HOLD", "RETIRED"}

PRODUCTION_ELIGIBLE_RIGHTS = {"CLEARED"}
PRODUCTION_ELIGIBLE_LIFECYCLE = {"ACTIVE"}

CURRENT_OBSERVATION_CLASSES = {
    "GROUND_OBSERVED",
    "MARINE_GROUND_OBSERVED",
    "REMOTE_OBSERVED",
    "REMOTE_RENDERED_OBSERVED",
}


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    evidence_class: str
    rights_state: str
    lifecycle: str
    independence_group: str
    production_dependency: bool


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "weather-observation-source-registry-v3":
        raise ValueError("unexpected V3 observation source registry schema")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("observation source registry is empty")
    ids: set[str] = set()
    for source in sources:
        source_id = str(source.get("id") or "")
        if not source_id or source_id in ids:
            raise ValueError(f"duplicate or missing source id: {source_id!r}")
        ids.add(source_id)
        if source.get("evidence_class") not in EVIDENCE_CLASSES:
            raise ValueError(f"invalid evidence class for {source_id}")
        if source.get("rights_state") not in RIGHTS_STATES:
            raise ValueError(f"invalid rights state for {source_id}")
        if source.get("lifecycle") not in LIFECYCLE_STATES:
            raise ValueError(f"invalid lifecycle for {source_id}")
        if not source.get("independence_group"):
            raise ValueError(f"missing independence group for {source_id}")
    return payload


def source_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in registry.get("sources") or []}


def policy_for(source_id: str, registry: dict[str, Any]) -> SourcePolicy:
    row = source_index(registry).get(source_id)
    if not row:
        raise KeyError(f"unknown observation source: {source_id}")
    return SourcePolicy(
        source_id=source_id,
        evidence_class=str(row["evidence_class"]),
        rights_state=str(row["rights_state"]),
        lifecycle=str(row["lifecycle"]),
        independence_group=str(row["independence_group"]),
        production_dependency=bool(row.get("production_dependency", False)),
    )


def production_eligible(source_id: str, registry: dict[str, Any]) -> bool:
    p = policy_for(source_id, registry)
    return (
        p.rights_state in PRODUCTION_ELIGIBLE_RIGHTS
        and p.lifecycle in PRODUCTION_ELIGIBLE_LIFECYCLE
    )


def normalize_receipt(receipt: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    """Normalize one evidence receipt without inventing values.

    A receipt may be numeric, raster-derived or rendered-observation-derived.
    Missing values remain None. The registry controls evidence class and
    independence group, never the incoming payload.
    """
    source_id = str(receipt.get("source_id") or "")
    policy = policy_for(source_id, registry)

    observed_at = _iso(receipt.get("observed_at"))
    received_at = _iso(receipt.get("received_at"))
    value = receipt.get("value")
    if isinstance(value, (int, float, str)) and receipt.get("numeric") is True:
        value = _finite_or_none(value)

    normalized = {
        "source_id": source_id,
        "source_class": policy.evidence_class,
        "independence_group": policy.independence_group,
        "rights_state": policy.rights_state,
        "lifecycle": policy.lifecycle,
        "production_eligible": production_eligible(source_id, registry),
        "observed_at": observed_at,
        "received_at": received_at,
        "station_id": receipt.get("station_id"),
        "physical_site_id": receipt.get("physical_site_id"),
        "lat": _finite_or_none(receipt.get("lat")),
        "lon": _finite_or_none(receipt.get("lon")),
        "variable": receipt.get("variable"),
        "value": value,
        "unit": receipt.get("unit"),
        "qc_status": receipt.get("qc_status") or "UNKNOWN",
        "freshness": receipt.get("freshness") or "UNKNOWN",
        "coverage_quality": receipt.get("coverage_quality") or "UNKNOWN",
        "confidence": _finite_or_none(receipt.get("confidence")),
        "raw_ref": receipt.get("raw_ref"),
        "raw_hash": receipt.get("raw_hash"),
        "interpreter_version": receipt.get("interpreter_version"),
        "notes": receipt.get("notes"),
    }

    # Never treat missing observation time as current merely because it was fetched now.
    if normalized["observed_at"] is None:
        normalized["freshness"] = "UNKNOWN"

    # Rendered observations stay explicitly derived from a public render.
    if policy.evidence_class == "REMOTE_RENDERED_OBSERVED":
        normalized["rendered_interpretation"] = True

    return normalized


def collapse_independence(receipts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        group = str(receipt.get("independence_group") or "UNKNOWN")
        groups.setdefault(group, []).append(receipt)
    return groups


def shadow_summary(receipts: Iterable[dict[str, Any]], registry: dict[str, Any]) -> dict[str, Any]:
    normalized = [normalize_receipt(r, registry) for r in receipts]
    groups = collapse_independence(normalized)

    by_class: dict[str, int] = {}
    for row in normalized:
        by_class[row["source_class"]] = by_class.get(row["source_class"], 0) + 1

    return {
        "schema_version": "weather-observation-mesh-shadow-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SHADOW_ONLY",
        "production_authority": "WEATHER_V2_UNCHANGED",
        "receipt_count": len(normalized),
        "independent_group_count": len(groups),
        "counts_by_class": by_class,
        "independence_groups": {
            group: sorted({str(r["source_id"]) for r in rows})
            for group, rows in sorted(groups.items())
        },
        "receipts": normalized,
        "policy": {
            "null_is_never_zero": True,
            "same_independence_group_does_not_double_vote": True,
            "unresolved_rights_do_not_promote_to_production": True,
            "rendered_observation_is_not_ground_measurement": True,
        },
    }
