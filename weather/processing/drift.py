"""Comparable run-to-run forecast drift."""
from __future__ import annotations


COMPARE_KEYS = ("model", "system", "variable", "location_id", "valid_window", "extraction_method")


def compare_runs(previous: dict, current: dict) -> dict:
    if any(previous.get(k) != current.get(k) for k in COMPARE_KEYS):
        return {"status": "NOT_COMPARABLE"}
    amplitude = float(current["value"]) - float(previous["value"])
    onset = float(current.get("onset_hour", 0)) - float(previous.get("onset_hour", 0))
    if abs(amplitude) < float(current.get("stable_tolerance", 0.1)) and abs(onset) < 3:
        trend = "STABLE"
    elif amplitude < 0 or onset > 6:
        trend = "RECEDING"
    else:
        trend = "DETERIORATING"
    return {"status": "OK", "amplitude_drift": round(amplitude, 3), "onset_drift_hours": round(onset, 1), "trend": trend}
