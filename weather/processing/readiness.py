"""Numerical readiness gates. HTTP reachability is never data eligibility."""
from __future__ import annotations

READINESS = (
    "UNAVAILABLE", "ENDPOINT_REACHABLE", "OBJECT_RETRIEVED", "FIELD_DECODED",
    "POINT_ROUTE_EXTRACTED", "MEMBER_COMPLETE", "DECISION_ELIGIBLE",
)


def readiness_rank(status: str) -> int:
    try:
        return READINESS.index(status)
    except ValueError:
        return -1


def decision_eligible(source: dict, *, ensemble_required: bool = False) -> bool:
    minimum = "MEMBER_COMPLETE" if ensemble_required else "POINT_ROUTE_EXTRACTED"
    return readiness_rank(source.get("readiness", "UNAVAILABLE")) >= readiness_rank(minimum) and source.get("qc") == "PASS"


def derive_data_mode(sources: dict, evidence: dict) -> str:
    atmosphere = any(decision_eligible(v) for k, v in sources.items() if "ECMWF" in k or "GEFS_DIRECT" in k or "ICON" in k)
    marine = any(decision_eligible(v) for k, v in sources.items() if "WAVE" in k or "COPERNICUS" in k)
    ensemble = any(decision_eligible(v, ensemble_required=True) for v in sources.values())
    route = bool(evidence.get("routes"))
    if atmosphere and marine and ensemble and route:
        return "A"
    if atmosphere or marine or evidence.get("official_status") or evidence.get("points"):
        return "B"
    return "C"
