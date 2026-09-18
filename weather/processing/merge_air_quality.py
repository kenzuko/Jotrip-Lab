"""Merge IQAir realtime AQI with CAMS PM/model reference.

Priority policy:
1) IQAir Community realtime US AQI when available.
2) CAMS model-derived particulate AQI fallback.
PM2.5/PM10 remain CAMS unless a future observed pollutant feed is explicitly added.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from weather.points import POINTS


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _category(aqi):
    try:
        aqi = int(round(float(aqi)))
    except (TypeError, ValueError):
        return None
    if aqi <= 50:
        return "GOOD"
    if aqi <= 100:
        return "MODERATE"
    if aqi <= 150:
        return "UNHEALTHY_FOR_SENSITIVE_GROUPS"
    if aqi <= 200:
        return "UNHEALTHY"
    if aqi <= 300:
        return "VERY_UNHEALTHY"
    return "HAZARDOUS"


def merge(cams: dict, iqair: dict) -> dict:
    cpoints = cams.get("points") if isinstance(cams.get("points"), dict) else {}
    ipoints = iqair.get("points") if isinstance(iqair.get("points"), dict) else {}
    points = {}
    primary_times = []
    iqair_ready = 0

    for point_id in POINTS:
        cp = cpoints.get(point_id) if isinstance(cpoints.get(point_id), dict) else {}
        ip = ipoints.get(point_id) if isinstance(ipoints.get(point_id), dict) else {}
        observed_aqi = ip.get("aqi_us")
        model_aqi = cp.get("aqi_us")
        use_iqair = observed_aqi is not None
        primary_aqi = observed_aqi if use_iqair else model_aqi
        primary_time = ip.get("sampled_time") if use_iqair else cp.get("sampled_time")
        if primary_time:
            primary_times.append(str(primary_time))
        if use_iqair:
            iqair_ready += 1
        divergence = None
        try:
            if observed_aqi is not None and model_aqi is not None:
                divergence = round(float(observed_aqi) - float(model_aqi), 1)
        except (TypeError, ValueError):
            divergence = None
        points[point_id] = {
            "aqi_us": primary_aqi,
            "category": ip.get("category") if use_iqair else (cp.get("category") or _category(primary_aqi)),
            "dominant_pollutant": ip.get("dominant_pollutant") if use_iqair else cp.get("dominant_pollutant"),
            "sampled_time": primary_time,
            "aqi_source": "IQAIR_COMMUNITY_REALTIME" if use_iqair else "CAMS_GLOBAL_ANALYSIS",
            "source_type": "REALTIME_CITY_PLATFORM" if use_iqair else "MODEL",
            "source_city": ip.get("city") if use_iqair else None,
            "source_state": ip.get("state") if use_iqair else None,
            "source_country": ip.get("country") if use_iqair else None,
            "pm25_ugm3": cp.get("pm25_ugm3"),
            "pm10_ugm3": cp.get("pm10_ugm3"),
            "pm_source": "CAMS_GLOBAL_ANALYSIS" if cp else None,
            "model_aqi_us": model_aqi,
            "model_category": cp.get("category") or _category(model_aqi),
            "model_sampled_time": cp.get("sampled_time"),
            "iqair_aqi_us": observed_aqi,
            "iqair_sampled_time": ip.get("sampled_time"),
            "iqair_city": ip.get("city"),
            "source_divergence_aqi": divergence,
            "grid_lat": cp.get("grid_lat"),
            "grid_lon": cp.get("grid_lon"),
        }

    ready = sum(1 for point in points.values() if point.get("aqi_us") is not None)
    status = "POINT_NUMERIC_READY" if ready == len(POINTS) else ("PARTIAL" if ready else "UNAVAILABLE")
    source = "IQAIR_REALTIME_PRIMARY_CAMS_REFERENCE" if iqair_ready else "CAMS_GLOBAL_ANALYSIS"
    return {
        "status": status,
        "source": source,
        "source_policy": "IQAIR_REALTIME_PRIMARY_CAMS_FALLBACK_REFERENCE",
        "source_type": "HYBRID_REALTIME_MODEL" if iqair_ready else "MODEL",
        "sampled_time": max(primary_times) if primary_times else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grid_resolution": cams.get("grid_resolution", "0.4deg"),
        "aqi_standard": "US AQI. IQAir realtime city-level AQI is primary when configured; CAMS particulate-derived AQI is fallback/reference.",
        "pm_note": "PM2.5/PM10 shown here are CAMS model concentrations unless a future observed pollutant feed is explicitly connected.",
        "iqair_status": iqair.get("status", "UNAVAILABLE"),
        "cams_status": cams.get("status", "UNAVAILABLE"),
        "points": points,
        "detail": f"AQI ready {ready}/{len(POINTS)}; IQAir primary at {iqair_ready}/{len(POINTS)} points; CAMS retained as fallback/model reference.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cams", type=Path, required=True)
    parser.add_argument("--iqair", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = merge(_read(args.cams), _read(args.iqair))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
