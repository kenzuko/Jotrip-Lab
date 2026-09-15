"""Marine vector and route calculations."""
from __future__ import annotations

import math


def current_from_uv(u_east: float, v_north: float) -> dict:
    speed = math.hypot(u_east, v_north)
    toward = (math.degrees(math.atan2(u_east, v_north)) + 360.0) % 360.0
    return {"speed_mps": round(speed, 4), "direction_toward_deg": round(toward, 2)}


def angular_difference(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def summarize_route(samples: list[dict]) -> dict:
    valid = [s for s in samples if s.get("sea_land_status") == "SEA" and s.get("qc") == "PASS"]
    if not valid:
        return {"status": "NOT_COMPUTABLE", "reason": "NO_VALID_SEA_GRID"}
    hs = sorted(float(s["hs_m"]) for s in valid)
    max_sample = max(valid, key=lambda s: float(s["hs_m"]))
    idx = round((len(hs) - 1) * .9)
    return {
        "status": "OK", "sample_count": len(valid), "route_typical_hs_m": round(hs[len(hs)//2], 3),
        "route_max_hs_m": round(max(hs), 3), "route_upper_p90_hs_m": round(hs[idx], 3),
        "max_gust_mps": round(max(float(s.get("gust_mps", 0)) for s in valid), 3),
        "worst_segment": max_sample["segment_id"], "worst_sample_coordinate": max_sample["sampled_coordinate"]
    }
