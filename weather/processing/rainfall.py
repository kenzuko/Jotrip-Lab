"""Rainfall increments, rolling accumulations and ensemble probabilities."""
from __future__ import annotations

from collections import defaultdict


def cumulative_to_increment(records: list[dict], *, tolerance_mm: float = 0.05) -> list[dict]:
    """Convert cumulative precipitation to increments without inventing finer steps."""
    ordered = sorted(records, key=lambda r: r["valid_time"])
    result, previous = [], None
    for record in ordered:
        current = float(record["value_mm"])
        if previous is None:
            increment, qc = max(0.0, current), "PASS"
        else:
            delta = current - previous
            increment = max(0.0, delta)
            qc = "PASS" if delta >= -tolerance_mm else "ACCUMULATION_RESET"
        result.append({**record, "rain_increment_mm": round(increment, 3), "qc": qc})
        previous = current
    return result


def rolling_accumulation(records: list[dict], hours: int) -> list[dict]:
    if hours <= 0:
        raise ValueError("hours must be positive")
    ordered = sorted(records, key=lambda r: r["lead_hours"])
    output = []
    for record in ordered:
        end = float(record["lead_hours"])
        values = [float(r["rain_increment_mm"]) for r in ordered
                  if end - hours < float(r["lead_hours"]) <= end]
        output.append({"valid_time": record["valid_time"], "lead_hours": end,
                       f"rain_{hours}h_mm": round(sum(values), 3)})
    return output


def ensemble_rain_probability(records: list[dict], threshold_mm: float, expected_members: int,
                              minimum_ratio: float = 0.75) -> dict:
    members = defaultdict(float)
    for record in records:
        members[str(record["member"])] += float(record["rain_increment_mm"])
    ratio = len(members) / expected_members
    if ratio < minimum_ratio:
        return {"status": "NOT_ELIGIBLE", "member_count": len(members),
                "expected_members": expected_members, "completion_ratio": round(ratio, 3)}
    return {"status": "ELIGIBLE" if ratio >= 0.9 else "PARTIAL_ENSEMBLE",
            "member_count": len(members), "expected_members": expected_members,
            "completion_ratio": round(ratio, 3), "threshold_mm": threshold_mm,
            "probability": round(sum(v >= threshold_mm for v in members.values()) / len(members), 4)}
