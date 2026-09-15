"""Member-level ensemble calculations with a strict completeness gate."""
from __future__ import annotations

import math


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(float(v) for v in values)
    if not xs:
        raise ValueError("No members")
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summarize_members(values: list[float], expected_members: int, minimum_ratio: float = 0.75, threshold: float | None = None) -> dict:
    if expected_members <= 0:
        raise ValueError("expected_members must be positive")
    ratio = len(values) / expected_members
    if ratio < minimum_ratio:
        return {"status": "NOT_ELIGIBLE", "member_count": len(values), "expected_members": expected_members, "completion_ratio": round(ratio, 3)}
    status = "ELIGIBLE" if ratio >= 0.90 else "PARTIAL_ENSEMBLE"
    result = {
        "status": status, "member_count": len(values), "expected_members": expected_members,
        "completion_ratio": round(ratio, 3), "q25": round(_quantile(values, .25), 3),
        "q50": round(_quantile(values, .50), 3), "q75": round(_quantile(values, .75), 3),
        "q90": round(_quantile(values, .90), 3), "q95": round(_quantile(values, .95), 3)
    }
    if threshold is not None:
        result["exceedance_probability"] = round(sum(v > threshold for v in values) / len(values), 4)
        result["threshold"] = threshold
    return result
