"""Versioned point-to-point forecast drift for canonical Weather Lab snapshots.

This module compares only the same point, valid time and variable across two
canonical snapshots. It deliberately does not classify improving/deteriorating
without configured thresholds; it exposes quantitative revision metrics for
MASTER and later calibration.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

VARIABLES = ("wind", "gust", "wave", "rain")
METHOD = "SAME_POINT_VALID_TIME_DELTA_V1"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _peak(rows: list[dict[str, Any]], variable: str) -> tuple[float, str] | None:
    values = [
        (float(row[variable]), row["time_iso"])
        for row in rows
        if row.get(variable) is not None and row.get("time_iso")
    ]
    if not values:
        return None
    return max(values, key=lambda item: item[0])


def compare_point_snapshots(previous: dict[str, Any] | None, current_points: dict[str, Any],
                            *, cutoff_time: str, horizon_hours: int = 72) -> dict[str, Any]:
    if not previous:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": "NO_PREVIOUS_CANONICAL_SNAPSHOT",
            "method": METHOD,
            "horizon_hours": horizon_hours,
        }

    start = _dt(cutoff_time)
    end = start + timedelta(hours=horizon_hours)
    previous_points = previous.get("points", {})
    result: dict[str, Any] = {
        "status": "NOT_COMPUTABLE",
        "reason": "NO_SHARED_VALID_TIMES",
        "method": METHOD,
        "horizon_hours": horizon_hours,
        "previous_snapshot_id": previous.get("snapshot_id"),
        "points": {},
        "trend_classification": {
            "status": "NOT_COMPUTABLE",
            "reason": "VERSIONED_TREND_THRESHOLDS_NOT_CONFIGURED",
        },
    }
    usable_points = 0

    for point_id, current in current_points.items():
        old = previous_points.get(point_id)
        if not isinstance(old, dict):
            continue
        old_by_time = {row.get("time_iso"): row for row in old.get("hours", []) if row.get("time_iso")}
        current_rows = [
            row for row in current.get("hours", [])
            if row.get("time_iso") and start <= _dt(row["time_iso"]) <= end
        ]
        shared_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for row in current_rows:
            old_row = old_by_time.get(row["time_iso"])
            if old_row is not None:
                shared_rows.append((old_row, row))
        if not shared_rows:
            continue

        variable_summaries: dict[str, Any] = {}
        for variable in VARIABLES:
            deltas: list[float] = []
            for old_row, row in shared_rows:
                if old_row.get(variable) is None or row.get(variable) is None:
                    continue
                deltas.append(float(row[variable]) - float(old_row[variable]))
            if not deltas:
                continue

            old_rows = [pair[0] for pair in shared_rows]
            new_rows = [pair[1] for pair in shared_rows]
            old_peak = _peak(old_rows, variable)
            new_peak = _peak(new_rows, variable)
            peak_drift_hours = None
            peak_amplitude_drift = None
            if old_peak and new_peak:
                peak_amplitude_drift = round(new_peak[0] - old_peak[0], 3)
                peak_drift_hours = round((_dt(new_peak[1]) - _dt(old_peak[1])).total_seconds() / 3600.0, 1)

            variable_summaries[variable] = {
                "sample_count": len(deltas),
                "mean_delta": round(sum(deltas) / len(deltas), 3),
                "mean_absolute_revision": round(sum(abs(value) for value in deltas) / len(deltas), 3),
                "max_absolute_revision": round(max(abs(value) for value in deltas), 3),
                "peak_amplitude_drift": peak_amplitude_drift,
                "peak_drift_hours": peak_drift_hours,
                "previous_peak": None if old_peak is None else {"value": old_peak[0], "valid_time": old_peak[1]},
                "current_peak": None if new_peak is None else {"value": new_peak[0], "valid_time": new_peak[1]},
            }

        if variable_summaries:
            usable_points += 1
            result["points"][point_id] = {
                "shared_valid_times": len(shared_rows),
                "variables": variable_summaries,
            }

    if usable_points:
        result["status"] = "AVAILABLE"
        result.pop("reason", None)
        result["point_count"] = usable_points
    return result
