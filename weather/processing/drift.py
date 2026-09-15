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


def compare_run_series(runs: list[dict]) -> dict:
    """Summarize consecutive comparable revisions without anchoring to an old forecast."""
    if len(runs) < 2:
        return {"status": "NOT_COMPUTABLE", "reason": "NEED_AT_LEAST_TWO_RUNS"}
    pairs = [compare_runs(a, b) for a, b in zip(runs, runs[1:])]
    if any(pair["status"] != "OK" for pair in pairs):
        return {"status": "NOT_COMPARABLE"}
    amplitudes = [p["amplitude_drift"] for p in pairs]
    onsets = [p["onset_drift_hours"] for p in pairs]
    if all(a < 0 or o > 6 for a, o in zip(amplitudes, onsets)):
        trend = "FORECAST_REVERSAL_IMPROVING" if len(pairs) >= 3 else "IMPROVING"
    elif all(a > 0 and o <= 6 for a, o in zip(amplitudes, onsets)):
        trend = "DETERIORATING"
    elif max(amplitudes) - min(amplitudes) > float(runs[-1].get("volatility_tolerance", 0.5)):
        trend = "HIGH_VOLATILITY"
    else:
        trend = "STABLE_OR_MIXED"
    return {"status": "OK", "runs_compared": len(runs), "trend": trend,
            "total_amplitude_drift": round(sum(amplitudes), 3),
            "total_onset_drift_hours": round(sum(onsets), 1), "pairwise": pairs}
