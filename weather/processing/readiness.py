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
    required_points = set(evidence.get("required_points", ("duong_dong", "an_thoi", "ganh_dau")))
    point_coverage = set(evidence.get("point_coverage", []))
    point_ready = required_points.issubset(point_coverage) if required_points else bool(point_coverage)
    spatial_mode = evidence.get("spatial_mode", "POINT_REGIONAL")
    spatial_ready = point_ready if spatial_mode == "POINT_REGIONAL" else any(
        bool(value.get("production_eligible")) and value.get("qc") == "PASS"
        for value in evidence.get("routes", {}).values()
    )
    if atmosphere and marine and ensemble and spatial_ready:
        return "A"
    if atmosphere or marine or evidence.get("official_status") or evidence.get("points"):
        return "B"
    return "C"
