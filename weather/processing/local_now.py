"""Build PQ Local Now V1.

PQ Local Now is an explicitly estimated, observation-anchored local analysis.
It is NOT a station observation. The algorithm keeps model spatial structure,
corrects smooth fields with fresh VVPQ observations, and estimates rain from
VRain gauge increments when available.

Wave/current values remain MODEL_ONLY until a suitable in-situ marine feed is
available.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather.points import POINTS as CANONICAL_POINTS, POINT_NAMES, POINT_METADATA

LOCAL_POINT_IDS = tuple(
    point_id for point_id in CANONICAL_POINTS
    if point_id != "rach_gia"
)
POINTS = {
    point_id: {
        "name": POINT_NAMES[point_id],
        "lat": CANONICAL_POINTS[point_id][0],
        "lon": CANONICAL_POINTS[point_id][1],
        "reference_type": POINT_METADATA[point_id].get("reference_type"),
    }
    for point_id in LOCAL_POINT_IDS
}

VVPQ = {"lat": 10.169, "lon": 103.995}
WIND_DECAY_KM = 38.0
TEMP_DECAY_KM = 45.0
RAIN_DECAY_KM = 28.0


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _uv(speed_kmh: float, direction_from_deg: float) -> tuple[float, float]:
    speed = speed_kmh / 3.6
    rad = math.radians(direction_from_deg)
    return -speed * math.sin(rad), -speed * math.cos(rad)


def _speed_dir(u: float, v: float) -> tuple[float, float]:
    speed_kmh = math.hypot(u, v) * 3.6
    direction = (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0
    return speed_kmh, direction


def _freshness(age_minutes: Any, half_life_minutes: float = 90.0) -> float:
    age = _num(age_minutes)
    if age is None:
        return 0.0
    return math.exp(-max(0.0, age) * math.log(2) / half_life_minutes)


def _current_model_row(point: dict, dashboard_time: datetime | None) -> dict:
    hours = point.get("hours") if isinstance(point.get("hours"), list) else []
    if not hours or dashboard_time is None:
        return {}
    best, best_delta = None, float("inf")
    for row in hours:
        try:
            t = datetime.fromisoformat(str(row.get("time_iso")).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        d = abs((t - dashboard_time).total_seconds())
        if d < best_delta:
            best, best_delta = row, d
    return best or {}


def _model_value(point: dict, row: dict, key: str) -> float | None:
    v = _num(row.get(key))
    if v is not None:
        return v
    return _num(point.get(key))


def _convective_score(nowcast_point: dict) -> float | None:
    direct = _num(nowcast_point.get("convective_score"))
    if direct is not None:
        return direct
    return _num((nowcast_point.get("convective_signal") or {}).get("score"))


def _convective_wind_floor(model_wind: float | None, model_gust: float | None, score: float | None) -> float | None:
    if model_wind is None or model_gust is None or score is None or score < 55:
        return None
    severity = _clamp((score - 55.0) / 35.0, 0.0, 1.0)
    gust_gap = max(0.0, model_gust - model_wind)
    # Conservative outflow proxy: never jump to gust speed. Satellite/nowcast
    # only lifts the local background by up to 30% of the model gust gap.
    return model_wind + 0.30 * severity * gust_gap


def _vvpq_correction(point_id: str, point: dict, model_point: dict, anchor_model: dict, vvpq: dict, nowcast_point: dict | None = None) -> dict:
    p = POINTS[point_id]
    distance = _haversine(p["lat"], p["lon"], VVPQ["lat"], VVPQ["lon"])
    freshness = _freshness(vvpq.get("age_minutes"))
    source_q = 0.96 if vvpq.get("qc") == "PASS" else 0.55

    result = {
        "distance_to_vvpq_km": round(distance, 1),
        "anchor_age_minutes": vvpq.get("age_minutes"),
        "anchor": "VVPQ",
    }

    model_temp = _num(model_point.get("temperature"))
    anchor_model_temp = _num(anchor_model.get("temperature"))
    obs_temp = _num(vvpq.get("temperature_c"))
    temp_alpha = math.exp(-distance / TEMP_DECAY_KM) * freshness * source_q
    if model_temp is not None and anchor_model_temp is not None and obs_temp is not None:
        correction = obs_temp - anchor_model_temp
        result["temperature_c"] = round(model_temp + temp_alpha * correction, 1)
        result["temperature"] = {
            "data_class": "ESTIMATED_NOW",
            "method": "PQ_LOCAL_NOW_V1_MODEL_RESIDUAL",
            "baseline_model": model_temp,
            "anchor_observed": obs_temp,
            "anchor_model_proxy": anchor_model_temp,
            "applied_residual_c": round(temp_alpha * correction, 2),
            "confidence": round(_clamp(0.35 + 0.55 * temp_alpha, 0.0, 0.92), 2),
        }
    else:
        result["temperature_c"] = model_temp
        result["temperature"] = {
            "data_class": "MODEL_ONLY",
            "method": "MODEL_FALLBACK",
            "confidence": 0.35,
        }

    model_wind = _num(model_point.get("wind"))
    model_gust = _num(model_point.get("gust"))
    anchor_model_wind = _num(anchor_model.get("wind"))
    obs_wind = _num(vvpq.get("wind_speed_kmh"))
    obs_dir = _num(vvpq.get("wind_direction_deg"))
    anchor_dir = _num(anchor_model.get("wind_direction_deg"))
    point_dir = _num(model_point.get("wind_direction_deg"))
    wind_alpha = math.exp(-distance / WIND_DECAY_KM) * freshness * source_q
    conv_score = _convective_score(nowcast_point or {})
    conv_floor = _convective_wind_floor(model_wind, model_gust, conv_score)
    conv_severity = _clamp(((conv_score or 0.0) - 55.0) / 35.0, 0.0, 1.0)
    # A calm airport observation can be very local during active convection.
    # Reduce its spatial authority as convective structure strengthens.
    if obs_wind is not None and obs_wind < 2.0 and conv_severity > 0:
        wind_alpha *= 1.0 - 0.70 * conv_severity

    # Direction is not present in the current dashboard point payload. When it is
    # unavailable, scale speed by the observed/model ratio instead of inventing a direction.
    if model_wind is not None and anchor_model_wind not in (None, 0) and obs_wind is not None:
        if obs_dir is not None and anchor_dir is not None and point_dir is not None:
            ou, ov = _uv(obs_wind, obs_dir)
            au, av = _uv(anchor_model_wind, anchor_dir)
            pu, pv = _uv(model_wind, point_dir)
            u, v = pu + wind_alpha * (ou - au), pv + wind_alpha * (ov - av)
            speed, direction = _speed_dir(u, v)
            result["wind_kmh"] = round(max(0.0, speed), 1)
            result["wind_direction_deg"] = round(direction)
            method = "PQ_LOCAL_NOW_V1_UV_RESIDUAL"
        else:
            ratio = _clamp(obs_wind / anchor_model_wind, 0.35, 2.2)
            corrected = model_wind * (1.0 + wind_alpha * (ratio - 1.0))
            corrected = max(corrected, conv_floor) if conv_floor is not None else corrected
            result["wind_kmh"] = round(max(0.0, corrected), 1)
            result["wind_direction_deg"] = None
            result["wind_reference_direction_deg"] = obs_dir
            method = "PQ_LOCAL_NOW_V1_CONVECTIVE_GUARDED_SPEED_RATIO" if conv_floor is not None else "PQ_LOCAL_NOW_V1_SPEED_RATIO"
        result["wind"] = {
            "data_class": "ESTIMATED_NOW",
            "method": method,
            "baseline_model": model_wind,
            "anchor_observed_kmh": obs_wind,
            "anchor_model_proxy_kmh": anchor_model_wind,
            "model_gust_kmh": model_gust,
            "convective_score": conv_score,
            "convective_floor_kmh": round(conv_floor, 1) if conv_floor is not None else None,
            "confidence": round(_clamp(0.30 + 0.58 * wind_alpha - 0.12 * conv_severity, 0.0, 0.90), 2),
        }
    else:
        estimated = conv_floor if conv_floor is not None else model_wind
        result["wind_kmh"] = round(estimated, 1) if estimated is not None else None
        result["wind_direction_deg"] = obs_dir
        if conv_floor is not None:
            result["wind"] = {
                "data_class": "ESTIMATED_NOW",
                "method": "PQ_LOCAL_NOW_V1_CONVECTIVE_BACKGROUND",
                "baseline_model": model_wind,
                "model_gust_kmh": model_gust,
                "convective_score": conv_score,
                "convective_floor_kmh": round(conv_floor, 1),
                "confidence": round(_clamp(0.24 + 0.20 * conv_severity, 0.24, 0.44), 2),
                "note": "Conservative convective background estimate; not an in-situ wind observation.",
            }
        else:
            result["wind"] = {"data_class": "MODEL_ONLY", "method": "MODEL_FALLBACK", "confidence": 0.30}
    return result


def _gauge_rate(station: dict) -> float | None:
    inc = _num(station.get("increment_mm"))
    minutes = _num(station.get("increment_window_minutes"))
    if inc is None or minutes is None or minutes <= 0 or station.get("increment_qc") != "PASS":
        return None
    return inc * 60.0 / minutes


def _rain_estimate(point_id: str, model_rain_3h: float | None, gauges: dict, nowcast_point: dict, vvpq: dict) -> dict:
    p = POINTS[point_id]
    weighted, weight_sum, anchors = 0.0, 0.0, []
    for key, station in gauges.items():
        rate = _gauge_rate(station)
        lat, lon = _num(station.get("lat")), _num(station.get("lon"))
        if rate is None or lat is None or lon is None:
            continue
        dist = _haversine(p["lat"], p["lon"], lat, lon)
        fresh = _freshness(station.get("age_minutes"), 75.0)
        w = math.exp(-dist / RAIN_DECAY_KM) * fresh
        if w <= 0:
            continue
        weighted += w * rate
        weight_sum += w
        anchors.append({"station": station.get("station_name"), "distance_km": round(dist, 1), "rate_mm_h": round(rate, 2), "weight": round(w, 3)})

    score = _num((nowcast_point.get("convective_signal") or {}).get("score"))
    score = score if score is not None else 35.0
    model_rate = max(0.0, (model_rain_3h or 0.0) / 3.0)
    wx = str(vvpq.get("weather") or "").upper()
    airport_rain = "RA" in wx or "SH" in wx or "TS" in wx
    dist_airport = _haversine(p["lat"], p["lon"], VVPQ["lat"], VVPQ["lon"])

    if weight_sum > 0:
        gauge_rate = weighted / weight_sum
        # Preserve observed gauge dominance. Model/satellite contributes only a
        # small stabilizing term in sparse spatial coverage.
        conv_factor = _clamp(0.65 + score / 125.0, 0.65, 1.45)
        model_signal = model_rate * conv_factor
        estimate = 0.80 * gauge_rate + 0.20 * model_signal
        nearest = min(a["distance_km"] for a in anchors)
        spatial_support = math.exp(-nearest / 25.0)
        network_support = min(1.0, weight_sum / 1.5)
        convective_penalty = 1.0 - 0.30 * _clamp(score / 100.0, 0.0, 1.0)
        confidence = (0.30 + 0.25 * spatial_support + 0.12 * network_support + 0.05 * min(len(anchors), 3)) * convective_penalty
        confidence = _clamp(confidence, 0.25, 0.78)
        return {
            "rain_rate_mm_h": round(max(0.0, estimate), 2),
            "data_class": "ESTIMATED_NOW",
            "method": "PQ_LOCAL_NOW_V1_GAUGE_IDW_MODEL_BLEND",
            "confidence": round(confidence, 2),
            "gauge_anchor_count": len(anchors),
            "gauge_anchors": anchors,
            "model_rain_3h_mm": model_rain_3h,
            "convective_score": score,
            "note": "80% spatial gauge-rate estimate + 20% model/satellite stabilizer. Experimental until field feedback/backtest is sufficient.",
        }

    conv_factor = _clamp(0.55 + score / 95.0, 0.55, 1.60)
    if airport_rain:
        conv_factor *= 1.0 + 0.30 * math.exp(-dist_airport / 28.0)
    estimate = model_rate * conv_factor
    return {
        "rain_rate_mm_h": round(max(0.0, estimate), 2),
        "data_class": "ESTIMATED_NOW",
        "method": "PQ_LOCAL_NOW_V1_MODEL_SATELLITE_BLEND",
        "confidence": round(_clamp(0.22 + 0.28 * score / 100.0, 0.18, 0.52), 2),
        "gauge_anchor_count": 0,
        "gauge_anchors": [],
        "model_rain_3h_mm": model_rain_3h,
        "convective_score": score,
        "airport_weather_support": airport_rain,
        "note": "Low-confidence experimental estimate because no fresh gauge increment is available.",
    }


def build(groundtruth: dict, dashboard: dict, nowcast: dict) -> dict:
    generated = _parse_time(groundtruth.get("generated_at")) or datetime.now(timezone.utc)
    dashboard_time = _parse_time(dashboard.get("generated_at"))
    points_model = dashboard.get("points", {})
    anchor_model_point = points_model.get("duong_dong", {})
    anchor_row = _current_model_row(anchor_model_point, dashboard_time)
    anchor_model = {
        "temperature": _model_value(anchor_model_point, anchor_row, "temperature"),
        "wind": _model_value(anchor_model_point, anchor_row, "wind"),
        "wind_direction_deg": None,
    }

    vvpq = groundtruth.get("atmosphere", {}).get("vvpq", {})
    gauges = groundtruth.get("rainfall", {}).get("stations", {})
    nowcast_points = nowcast.get("points", {}) if isinstance(nowcast, dict) else {}

    output_points = {}
    for point_id, meta in POINTS.items():
        mp = points_model.get(point_id, {})
        row = _current_model_row(mp, dashboard_time)
        model = {
            "temperature": _model_value(mp, row, "temperature"),
            "wind": _model_value(mp, row, "wind"),
            "gust": _model_value(mp, row, "gust"),
            "wind_direction_deg": None,
            "rain": _model_value(mp, row, "rain"),
            "wave": _model_value(mp, row, "wave"),
            "wave_max": _model_value(mp, row, "wave_max"),
            "period": _model_value(mp, row, "period"),
            "current": _model_value(mp, row, "current"),
        }
        corrected = _vvpq_correction(point_id, meta, model, anchor_model, vvpq, nowcast_points.get(point_id, {}))
        rain = _rain_estimate(point_id, model["rain"], gauges, nowcast_points.get(point_id, {}), vvpq)
        output_points[point_id] = {
            **meta,
            "analysis_time": generated.isoformat(),
            "temperature_c": corrected.get("temperature_c"),
            "temperature": corrected.get("temperature"),
            "wind_kmh": corrected.get("wind_kmh"),
            "wind_direction_deg": corrected.get("wind_direction_deg"),
            "wind": corrected.get("wind"),
            "rain": rain,
            "wave_hs_m": model["wave"],
            "wave_hmax_m": model["wave_max"],
            "wave_period_s": model["period"],
            "current_kmh": model["current"],
            "marine": {
                "data_class": "MODEL_ONLY",
                "method": "COPERNICUS_ECMWF_MODEL",
                "confidence": None,
                "note": "No usable in-situ marine observation at Phu Quoc. Never label these values actual.",
            },
            "actual_anchors": {
                "vvpq": {
                    "status": vvpq.get("status"),
                    "observed_at": vvpq.get("observed_at"),
                    "distance_km": corrected.get("distance_to_vvpq_km"),
                },
                "rain_gauges": [
                    {
                        "station": s.get("station_name"),
                        "lat": s.get("lat"),
                        "lon": s.get("lon"),
                        "accumulation_mm": s.get("accumulation_mm"),
                        "increment_mm": s.get("increment_mm"),
                        "increment_window_minutes": s.get("increment_window_minutes"),
                    }
                    for s in gauges.values()
                ],
            },
        }

    return {
        "schema_version": "1.0",
        "engine": "PQ_LOCAL_NOW_V1",
        "generated_at": generated.isoformat(),
        "data_class": "ESTIMATED_NOW",
        "title": "PQ Local Now",
        "policy": {
            "actual": "VVPQ METAR + VRain gauges only when fresh numeric observations exist.",
            "estimated_now": "Observation-anchored local correction. Never presented as station actual.",
            "marine": "MODEL_ONLY until a usable in-situ marine feed is available.",
            "feedback": "Field feedback calibrates categorical/event errors and later numeric coefficients; it never rewrites raw observations.",
        },
        "points": output_points,
        "source_status": {
            "vvpq": vvpq.get("status"),
            "vrain": groundtruth.get("rainfall", {}).get("status"),
            "himawari": nowcast.get("status") if isinstance(nowcast, dict) else "UNAVAILABLE",
            "duong_dong_60018": groundtruth.get("station_status", {}).get("60018", {}).get("readiness"),
            "an_thoi_408": groundtruth.get("station_status", {}).get("408", {}).get("readiness"),
        },
    }


def _parse_time(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groundtruth", type=Path, required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--nowcast", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    groundtruth = json.loads(args.groundtruth.read_text(encoding="utf-8"))
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    nowcast = json.loads(args.nowcast.read_text(encoding="utf-8")) if args.nowcast.exists() else {}
    result = build(groundtruth, dashboard, nowcast)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "engine": result["engine"],
        "generated_at": result["generated_at"],
        "points": {
            k: {
                "temperature": v["temperature"].get("data_class"),
                "wind": v["wind"].get("data_class"),
                "rain_method": v["rain"].get("method"),
                "rain_confidence": v["rain"].get("confidence"),
                "marine": v["marine"].get("data_class"),
            } for k, v in result["points"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
