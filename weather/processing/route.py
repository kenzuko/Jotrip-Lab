"""Resolution-aware route exposure calculations."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from weather.processing.marine import angular_difference


def summarize_route_timeseries(samples: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        if sample.get("qc") == "PASS" and sample.get("sea_land_status") == "SEA":
            grouped[sample["valid_time"]].append(sample)
    output = []
    for valid_time, rows in sorted(grouped.items()):
        hs = [float(r["hs_m"]) for r in rows]
        gust = [float(r["gust_kmh"]) for r in rows]
        worst = max(rows, key=lambda r: float(r["hs_m"]))
        angles = [angular_difference(float(r["wave_direction_deg"]), float(r["heading_deg"])) for r in rows]
        output.append({"valid_time": valid_time, "status": "OK", "sample_count": len(rows),
                       "route_typical_hs_m": round(median(hs), 3), "route_max_hs_m": round(max(hs), 3),
                       "route_max_gust_kmh": round(max(gust), 2), "worst_segment": worst["segment_id"],
                       "minimum_wave_heading_angle_deg": round(min(angles), 1),
                       "exposure_duration_minutes": round(sum(float(r.get("duration_minutes", 0)) for r in rows), 1)})
    return output
