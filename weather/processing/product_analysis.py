"""Product-level data completeness and deterministic background windows.

This layer does not issue operational decisions. It reuses versioned product
weights and provisional thresholds already present in Weather Lab. Missing
actual/visibility/convection remains explicit rather than being converted into
weather risk.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from weather.processing.quality import completeness, critical_gaps
from weather.processing.window import detect_windows

CONFIG = Path(__file__).resolve().parents[1] / "config"
FORMULA_ID = "PRODUCT_ANALYSIS_V1"

FIELD_MAP = {
    "wind_kmh": "wind",
    "gust_kmh": "gust",
    "hs_m": "wave",
    "rain_3h_mm": "rain",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def _has_hourly(point: dict[str, Any], field: str) -> bool:
    return any(row.get(field) is not None for row in point.get("hours", []))


def _availability(point: dict[str, Any], marine: dict[str, Any] | None,
                  observations: dict[str, Any] | None, official: dict[str, Any] | None) -> dict[str, float]:
    observations = observations or {}
    official = official or {}
    marine = marine or {}
    return {
        "wind": float(_has_hourly(point, "wind")),
        "gust": float(_has_hourly(point, "gust")),
        "hs": float(_has_hourly(point, "wave") or point.get("wave") is not None),
        "period": float(_has_hourly(point, "period") or point.get("period") is not None),
        "wave_period": float(_has_hourly(point, "period") or point.get("period") is not None),
        "current": float(marine.get("current", {}).get("speed_kmh") is not None or point.get("current") is not None),
        "wave_direction": float(marine.get("wave", {}).get("direction_deg") is not None),
        "rain_timing": float(_has_hourly(point, "rain")),
        "convection": float(bool(observations.get("convective_signal"))),
        "visibility": float(observations.get("visibility_km") is not None),
        "local_truth": float(bool(observations)),
        "restriction": float(official.get("restriction") not in (None, "UNKNOWN")),
        "operating_status": float(official.get("operating_status") not in (None, "UNKNOWN")),
        "tide": float(observations.get("tide") is not None),
        "pop": float(_has_hourly(point, "pop")),
        "heat_uv": float(_has_hourly(point, "uv")),
    }


def _rows(point: dict[str, Any], thresholds: dict[str, Any], cutoff_time: str,
          window_hours: list[int] | None) -> list[dict[str, Any]]:
    cutoff = datetime.fromisoformat(cutoff_time.replace("Z", "+00:00"))
    horizon = cutoff + timedelta(hours=48)
    source = [
        row for row in point.get("hours", [])
        if row.get("time_iso") and cutoff <= datetime.fromisoformat(row["time_iso"].replace("Z", "+00:00")) <= horizon
    ]
    output = []
    for index, row in enumerate(source):
        start = datetime.fromisoformat(row["time_iso"].replace("Z", "+00:00"))
        if window_hours is not None and not (window_hours[0] <= start.hour < window_hours[1]):
            continue
        if index + 1 < len(source):
            end = datetime.fromisoformat(source[index + 1]["time_iso"].replace("Z", "+00:00"))
        else:
            end = start + timedelta(hours=3)
        if window_hours is not None:
            window_end = start.replace(hour=window_hours[1], minute=0, second=0, microsecond=0)
            if window_hours[1] == 24:
                window_end = start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            end = min(end, window_end)
        mapped = {"start_time": start.isoformat(), "end_time": end.isoformat()}
        for threshold_name in thresholds:
            field = FIELD_MAP.get(threshold_name)
            if field:
                mapped[threshold_name] = row.get(field)
        output.append(mapped)
    return output


def build_product_analysis(points: dict[str, Any], marine_details: dict[str, Any], *,
                           cutoff_time: str, observations: dict[str, Any] | None = None,
                           official_status: dict[str, Any] | None = None) -> dict[str, Any]:
    products = _load("products.json")
    thresholds_config = _load("thresholds.json")
    scopes = _load("product_scopes.json")["products"]
    result: dict[str, Any] = {
        "formula_id": FORMULA_ID,
        "threshold_status": thresholds_config.get("status"),
        "products": {},
    }

    for output_id, scope in scopes.items():
        base_id = scope["base_product"]
        product = products[base_id]
        point_id = scope.get("point_id")
        if not point_id or point_id not in points:
            result["products"][output_id] = {
                "status": "NOT_COMPUTABLE",
                "reason": "POINT_OR_ROUTE_SCOPE_NOT_CONFIGURED",
                "base_product": base_id,
                "completeness": None,
                "critical_data_gaps": [],
                "background_windows": [],
            }
            continue

        point = points[point_id]
        availability = _availability(
            point,
            marine_details.get(point_id),
            (observations or {}).get(point_id),
            (official_status or {}).get(output_id) or (official_status or {}).get(base_id),
        )
        score = completeness(product, availability)
        critical = critical_gaps(product, availability)

        raw_thresholds = thresholds_config.get(base_id, {})
        supported_thresholds = {
            key: value for key, value in raw_thresholds.items()
            if key in FIELD_MAP
        }
        rows = _rows(point, supported_thresholds, cutoff_time, scope.get("window_hours"))
        windows = detect_windows(rows, supported_thresholds, list(supported_thresholds)) if rows and supported_thresholds else []

        missing_analysis = sorted(
            key for key, value in availability.items()
            if value <= 0 and key in product and float(product[key].get("weight", 0)) > 0
        )
        result["products"][output_id] = {
            "status": "PARTIAL" if missing_analysis else "AVAILABLE",
            "base_product": base_id,
            "point_id": point_id,
            "analysis_role": scope.get("analysis_role"),
            "completeness": score,
            "availability": availability,
            "critical_data_gaps": critical,
            "analysis_gaps": missing_analysis,
            "background_windows": windows,
            "window_status": "PARTIAL_BACKGROUND_ONLY",
            "window_note": "Deterministic background only. Final operational window still requires Decision Plane gates, actual/local truth and applicable restriction/visibility/convection evidence.",
        }
    return result
