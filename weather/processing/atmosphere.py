"""Atmospheric vector and precipitation normalization."""
from __future__ import annotations

import math
from collections import defaultdict

from weather.processing.units import speed_to_kmh


def wind_from_uv(u_east_mps: float, v_north_mps: float) -> dict:
    speed = math.hypot(float(u_east_mps), float(v_north_mps))
    direction_from = (math.degrees(math.atan2(-float(u_east_mps), -float(v_north_mps))) + 360) % 360
    return {"wind_speed_kmh": speed_to_kmh(speed, "m/s"),
            "wind_direction_from_deg": round(direction_from, 1)}


def derive_wind_records(records: list[dict]) -> list[dict]:
    grouped = defaultdict(dict)
    for record in records:
        key = (record.get("source"), record.get("run_time"), record.get("member"),
               record.get("valid_time"), record.get("point_id"))
        grouped[key][record.get("variable")] = record
    output = []
    for key, variables in grouped.items():
        u = variables.get("10u") or variables.get("u10") or variables.get("10u10")
        v = variables.get("10v") or variables.get("v10") or variables.get("10v10")
        if not u or not v:
            continue
        vector = wind_from_uv(u["value"], v["value"])
        source, run_time, member, valid_time, point_id = key
        output.append({"source": source, "run_time": run_time, "member": member,
                       "valid_time": valid_time, "point_id": point_id, **vector,
                       "qc": "PASS", "input_variables": [u["variable"], v["variable"]]})
    return output
