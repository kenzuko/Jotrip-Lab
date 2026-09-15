"""Product-specific operational weather-window detection."""
from __future__ import annotations


def _band(row: dict, thresholds: dict) -> tuple[str, list[str]]:
    avoid, watch = [], []
    for variable, limits in thresholds.items():
        value = row.get(variable)
        if value is None:
            continue
        if float(value) >= float(limits["avoid"]):
            avoid.append(variable)
        elif float(value) >= float(limits["watch"]):
            watch.append(variable)
    if avoid:
        return "AVOID", avoid
    if watch:
        return "MARGINAL", watch
    return "BEST", []


def detect_windows(rows: list[dict], thresholds: dict, required: list[str]) -> list[dict]:
    classified = []
    for row in sorted(rows, key=lambda r: r["start_time"]):
        missing = [v for v in required if row.get(v) is None]
        if missing:
            classified.append({**row, "window_class": "UNRESOLVED", "missing": missing})
            continue
        band, drivers = _band(row, thresholds)
        classified.append({**row, "window_class": band, "drivers": drivers})
    merged = []
    for row in classified:
        if (merged and row["window_class"] == merged[-1]["window_class"]
                and row["start_time"] == merged[-1]["end_time"]):
            merged[-1]["end_time"] = row["end_time"]
            merged[-1]["drivers"] = sorted(set(merged[-1].get("drivers", []) + row.get("drivers", [])))
        else:
            merged.append(dict(row))
    return merged
