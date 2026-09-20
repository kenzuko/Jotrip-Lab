"""Build PQ Local Now V2.

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


def _nearest_ensemble_row(ensemble: dict, point_id: str, analysis_time: datetime, max_gap_hours: float = 9.0) -> dict:
    rows = ((ensemble.get("points") or {}).get(point_id) or []) if isinstance(ensemble, dict) else []
    best, best_gap = None, float("inf")
    for row in rows:
        valid = _parse_time(row.get("valid_time"))
        if valid is None:
            continue
        gap = abs((valid - analysis_time).total_seconds()) / 3600.0
        if gap < best_gap:
            best, best_gap = row, gap
    if best is None or best_gap > max_gap_hours:
        return {}
    return {**best, "_gap_hours": best_gap}


def _ensemble_context(ensemble: dict, point_id: str, analysis_time: datetime) -> dict:
    row = _nearest_ensemble_row(ensemble, point_id, analysis_time)
    if not row:
        return {}
    variables = row.get("variables") or {}
    wind = (variables.get("wind") or {}).get("corrected") or (variables.get("wind") or {}).get("raw") or {}
    rain = (variables.get("rain") or {}).get("corrected") or (variables.get("rain") or {}).get("raw") or {}
    return {
        "valid_time": row.get("valid_time"),
        "gap_hours": round(float(row.get("_gap_hours", 0.0)), 2),
        "wind_q50_kmh": _num(wind.get("q50")),
        "wind_q90_kmh": _num(wind.get("q90")),
        "wind_spread_kmh": _num(wind.get("spread")),
        "wind_probability_30": _num(wind.get("exceedance_probability")),
        "rain_q50_mm": _num(rain.get("q50")),
        "rain_q90_mm": _num(rain.get("q90")),
        "rain_spread_mm": _num(rain.get("spread")),
        "rain_probability_5": _num(rain.get("exceedance_probability")),
    }


def _ensemble_gain(model_wind: float | None, context: dict, distance_km: float, age_minutes: Any, skill_multiplier: float = 1.0) -> dict:
    """Adaptive uncertainty term inspired by OI/EnKF background-error weighting.

    The ensemble does not become another observation. It estimates how uncertain
    the model background is, which modulates the observation correction.
    """
    q50 = _num(context.get("wind_q50_kmh"))
    spread = _num(context.get("wind_spread_kmh"))
    if model_wind is None or q50 is None or spread is None:
        return {"available": False, "gain": 1.0}

    # IQR -> approximate sigma under a near-Gaussian distribution. A floor keeps
    # small ensembles/spreads from claiming unrealistic certainty.
    ensemble_sigma = max(1.5, spread / 1.349)
    disagreement = abs(model_wind - q50)
    gap = _num(context.get("gap_hours")) or 0.0
    sigma_b = math.sqrt(ensemble_sigma**2 + (0.50 * disagreement) ** 2 + (0.35 * gap) ** 2)

    age = max(0.0, _num(age_minutes) or 0.0)
    # Representativeness dominates instrument error here because VVPQ is a point
    # anchor being transported spatially across an island/marine domain.
    sigma_o = 1.5 + 0.10 * max(0.0, distance_km) + 0.02 * age
    kalman_like = sigma_b**2 / (sigma_b**2 + sigma_o**2)

    # Preserve the already-tested distance/freshness correction. Ensemble only
    # modulates its strength rather than replacing the local analysis.
    gain = _clamp((0.65 + 0.70 * kalman_like) * _clamp(skill_multiplier, 0.90, 1.10), 0.60, 1.30)
    return {
        "available": True,
        "gain": gain,
        "kalman_like_gain": kalman_like,
        "background_sigma_kmh": sigma_b,
        "observation_repr_sigma_kmh": sigma_o,
        "ensemble_sigma_kmh": ensemble_sigma,
        "model_ensemble_disagreement_kmh": disagreement,
        "source_skill_multiplier": _clamp(skill_multiplier, 0.90, 1.10),
    }


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


def _vvpq_correction(point_id: str, point: dict, model_point: dict, anchor_model: dict, vvpq: dict, nowcast_point: dict | None = None, ensemble_context: dict | None = None, source_skill: dict | None = None) -> dict:
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
    skill_multiplier = _num((((source_skill or {}).get("vvpq") or {}).get("wind") or {}).get("ensemble_gain_multiplier")) or 1.0
    ens_gain = _ensemble_gain(model_wind, ensemble_context or {}, distance, vvpq.get("age_minutes"), skill_multiplier)
    wind_alpha *= float(ens_gain.get("gain", 1.0))
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
            # Scalar residual correction when vector direction is unavailable.
            # This is closer to Optimal Interpolation than a capped speed ratio:
            # preserve the local model structure, then transport only the anchor
            # innovation (ACTUAL - anchor background) with distance/freshness/
            # ensemble-aware gain.
            innovation = obs_wind - anchor_model_wind
            corrected = model_wind + wind_alpha * innovation
            corrected = max(corrected, conv_floor) if conv_floor is not None else corrected
            result["wind_kmh"] = round(max(0.0, corrected), 1)
            result["wind_direction_deg"] = None
            result["wind_reference_direction_deg"] = obs_dir
            if ens_gain.get("available"):
                method = "PQ_LOCAL_NOW_V2_ENSEMBLE_AWARE_RESIDUAL_CONVECTIVE" if conv_floor is not None else "PQ_LOCAL_NOW_V2_ENSEMBLE_AWARE_RESIDUAL"
            else:
                method = "PQ_LOCAL_NOW_V2_SPEED_RESIDUAL_CONVECTIVE" if conv_floor is not None else "PQ_LOCAL_NOW_V2_SPEED_RESIDUAL"
            result["wind_innovation_kmh"] = round(innovation, 2)
        result["wind"] = {
            "data_class": "ESTIMATED_NOW",
            "method": method,
            "baseline_model": model_wind,
            "anchor_observed_kmh": obs_wind,
            "anchor_model_proxy_kmh": anchor_model_wind,
            "model_gust_kmh": model_gust,
            "convective_score": conv_score,
            "convective_floor_kmh": round(conv_floor, 1) if conv_floor is not None else None,
            "ensemble_context": {
                "available": bool(ens_gain.get("available")),
                "valid_time": (ensemble_context or {}).get("valid_time"),
                "gap_hours": (ensemble_context or {}).get("gap_hours"),
                "q50_kmh": (ensemble_context or {}).get("wind_q50_kmh"),
                "q90_kmh": (ensemble_context or {}).get("wind_q90_kmh"),
                "spread_kmh": (ensemble_context or {}).get("wind_spread_kmh"),
                "adaptive_gain": round(float(ens_gain.get("gain", 1.0)), 3),
                "kalman_like_gain": round(float(ens_gain.get("kalman_like_gain", 0.0)), 3) if ens_gain.get("available") else None,
                "background_sigma_kmh": round(float(ens_gain.get("background_sigma_kmh", 0.0)), 2) if ens_gain.get("available") else None,
                "observation_repr_sigma_kmh": round(float(ens_gain.get("observation_repr_sigma_kmh", 0.0)), 2) if ens_gain.get("available") else None,
                "source_skill_multiplier": round(float(ens_gain.get("source_skill_multiplier", 1.0)), 3),
                "source_skill_status": ((((source_skill or {}).get("vvpq") or {}).get("wind") or {}).get("status")),
            },
            "confidence": round(_clamp(0.30 + 0.58 * min(1.0, wind_alpha) - 0.12 * conv_severity, 0.0, 0.90), 2),
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


def _gauge_rate(station: dict) -> tuple[float | None, str | None]:
    """Return a current rain-rate anchor without inventing wet weather.

    A recent zero accumulation is valid dry evidence even when a short increment
    cannot be formed. Positive accumulation without a recent increment does NOT
    prove it is raining now, so it remains unavailable for rate estimation.
    """
    inc = _num(station.get("increment_mm"))
    minutes = _num(station.get("increment_window_minutes"))
    if inc is not None and minutes is not None and minutes > 0 and station.get("increment_qc") == "PASS":
        return inc * 60.0 / minutes, "RECENT_INCREMENT"

    accumulation = _num(station.get("accumulation_mm"))
    age = _num(station.get("age_minutes"))
    if station.get("qc") == "PASS" and accumulation == 0 and age is not None and age <= 20:
        return 0.0, "FRESH_ZERO_ACCUMULATION"
    return None, None


def _rain_imminence(model_rain_3h: float | None, nowcast_point: dict, ensemble_context: dict | None = None) -> dict:
    """Heuristic 0-60 minute convective-rain signal.

    This is deliberately NOT a rain probability and NOT an observation. It is a
    hazard/context layer so a low grid-mean rain rate cannot look falsely calm
    while observed satellite convection is active or rapidly developing.
    """
    conv = _convective_score(nowcast_point)
    cooling = _num(nowcast_point.get("cooling_c_per_20m_proxy"))
    model_mm = max(0.0, _num(model_rain_3h) or 0.0)
    q90 = max(0.0, _num((ensemble_context or {}).get("rain_q90_mm")) or 0.0)
    prob5 = _num((ensemble_context or {}).get("rain_probability_5"))
    motion = nowcast_point.get("cloud_motion") or {}
    motion_status = str(motion.get("status") or "").upper()
    eta_minutes = _num(motion.get("eta_minutes"))
    predicted_impact = bool(motion.get("predicted_impact"))
    public_track_usable = bool(motion.get("public_track_usable"))
    approaching = bool(motion.get("approaching"))

    if conv is None and model_mm <= 0 and q90 <= 0:
        return {
            "score": None,
            "level": "UNAVAILABLE",
            "window_minutes": 60,
            "method": "PQ_RAIN_IMMINENCE_V2_SATELLITE_MOTION_ENSEMBLE_HEURISTIC_NOT_PROBABILITY",
            "not_probability": True,
        }

    conv_component = 0.60 * _clamp(conv or 0.0, 0.0, 100.0)
    model_component = 18.0 * _clamp(model_mm / 6.0, 0.0, 1.0)
    cooling_component = 12.0 * _clamp((-(cooling or 0.0)) / 6.0, 0.0, 1.0)
    ensemble_component = 10.0 * _clamp(q90 / 5.0, 0.0, 1.0)
    motion_component = 0.0
    if motion_status == "NEARBY" or (predicted_impact and eta_minutes == 0):
        motion_component = 15.0
    elif predicted_impact and eta_minutes is not None:
        if eta_minutes <= 60:
            motion_component = 15.0
        elif eta_minutes <= 120:
            motion_component = 8.0
        elif eta_minutes <= 180:
            motion_component = 4.0
    raw = _clamp(
        conv_component + model_component + cooling_component + ensemble_component + motion_component,
        0.0,
        100.0,
    )

    if raw >= 75:
        level = "HIGH"
    elif raw >= 55:
        level = "ELEVATED"
    elif raw >= 35:
        level = "WATCH"
    else:
        level = "LOW"

    # Public impact wording is intentionally qualitative. The model 3h mean is
    # the background intensity; deep satellite convection only expands the
    # local-tail wording, it never invents a numeric peak rate.
    model_hourly = model_mm / 3.0
    if model_hourly >= 7.5:
        impact_label = "Mưa mạnh"
    elif model_hourly >= 2.5:
        impact_label = "Mưa vừa"
    elif model_hourly >= 0.5:
        impact_label = "Mưa nhẹ đến vừa"
    elif model_hourly > 0.05:
        impact_label = "Mưa nhẹ"
    else:
        impact_label = "Nền mô hình ít mưa"
    if predicted_impact and (conv or 0.0) >= 75:
        if model_hourly < 2.5:
            impact_label += ", cục bộ có thể mạnh hơn"
        else:
            impact_label += ", cục bộ có thể mưa mạnh"

    return {
        "score": round(raw, 1),
        "level": level,
        "window_minutes": 60,
        "convective_score": conv,
        "cooling_c_per_20m_proxy": cooling,
        "model_rain_3h_mm": model_rain_3h,
        "ensemble_q90_mm": q90 if q90 > 0 else None,
        "ensemble_probability_5": prob5,
        "cloud_motion": {
            "status": motion.get("status"),
            "source_sector": motion.get("source_sector"),
            "nearest_corridor": motion.get("nearest_corridor"),
            "motion_heading_deg": _num(motion.get("motion_heading_deg")),
            "motion_heading": motion.get("motion_heading"),
            "motion_speed_kmh": _num(motion.get("motion_speed_kmh")),
            "distance_to_target_km": _num(motion.get("distance_to_target_km")),
            "approaching": approaching,
            "predicted_impact": predicted_impact,
            "public_track_usable": public_track_usable,
            "eta_minutes": eta_minutes,
            "arrival_time": motion.get("arrival_time"),
            "exit_time": motion.get("exit_time"),
            "closest_approach_km": _num(motion.get("closest_approach_km")),
            "tracking_confidence": motion.get("tracking_confidence"),
        },
        "rain_impact_label": impact_label,
        "background_model_rate_mm_h": round(model_hourly, 2),
        "impact_basis": "MODEL_3H_BACKGROUND_PLUS_SATELLITE_CONVECTIVE_TAIL",
        "motion_component": round(motion_component, 1),
        "method": "PQ_RAIN_IMMINENCE_V2_SATELLITE_MOTION_ENSEMBLE_HEURISTIC_NOT_PROBABILITY",
        "not_probability": True,
        "note": "Short-range convective context only. It does not replace ACTUAL rain observations or claim a numeric rain probability.",
    }


def _rain_estimate(point_id: str, model_rain_3h: float | None, gauges: dict, nowcast_point: dict, vvpq: dict, ensemble_context: dict | None = None, source_skill: dict | None = None) -> dict:
    p = POINTS[point_id]
    weighted, weight_sum, anchors = 0.0, 0.0, []
    for key, station in gauges.items():
        rate, evidence = _gauge_rate(station)
        lat, lon = _num(station.get("lat")), _num(station.get("lon"))
        if rate is None or lat is None or lon is None:
            continue
        dist = _haversine(p["lat"], p["lon"], lat, lon)
        fresh = _freshness(station.get("age_minutes"), 75.0)
        quality_factor = _num((((source_skill or {}).get("vrain") or {}).get(key) or {}).get("quality_factor")) or 1.0
        w = math.exp(-dist / RAIN_DECAY_KM) * fresh * _clamp(quality_factor, 0.80, 1.05)
        if w <= 0:
            continue
        weighted += w * rate
        weight_sum += w
        anchors.append({
            "station": station.get("station_name"),
            "distance_km": round(dist, 1),
            "rate_mm_h": round(rate, 2),
            "weight": round(w, 3),
            "evidence": evidence,
            "accumulation_mm": _num(station.get("accumulation_mm")),
            "source_quality_factor": round(_clamp(quality_factor, 0.80, 1.05), 3),
        })

    score = _num((nowcast_point.get("convective_signal") or {}).get("score"))
    score = score if score is not None else 35.0
    model_rate = max(0.0, (model_rain_3h or 0.0) / 3.0)
    wx = str(vvpq.get("weather") or "").upper()
    airport_rain = "RA" in wx or "SH" in wx or "TS" in wx
    dist_airport = _haversine(p["lat"], p["lon"], VVPQ["lat"], VVPQ["lon"])
    imminence = _rain_imminence(model_rain_3h, nowcast_point, ensemble_context)

    if weight_sum > 0:
        # If the target itself has a fresh passing gauge, that local observation
        # must dominate the rain analysis. Remote gauges are useful for ungauged
        # points, but must not dilute or inflate a co-located ACTUAL rate.
        colocated = [a for a in anchors if a["distance_km"] <= 1.5 and a["rate_mm_h"] is not None]
        if colocated:
            local_anchor = min(colocated, key=lambda a: a["distance_km"])
            local_rate = max(0.0, float(local_anchor["rate_mm_h"]))
            return {
                "rain_rate_mm_h": round(local_rate, 2),
                "data_class": "ESTIMATED_NOW",
                "method": "PQ_LOCAL_NOW_V3_COLOCATED_GAUGE_ANCHORED",
                "confidence": 0.88,
                "gauge_anchor_count": len(anchors),
                "gauge_anchors": anchors,
                "model_rain_3h_mm": model_rain_3h,
                "model_share": 0.0,
                "gauge_share": 1.0,
                "nearest_gauge_km": round(local_anchor["distance_km"], 1),
                "convective_score": score,
                "imminence": imminence,
                "colocated_actual_station": local_anchor["station"],
                "colocated_actual_rate_mm_h": round(local_rate, 2),
                "ensemble_context": {
                    "valid_time": (ensemble_context or {}).get("valid_time"),
                    "gap_hours": (ensemble_context or {}).get("gap_hours"),
                    "q50_mm": (ensemble_context or {}).get("rain_q50_mm"),
                    "q90_mm": (ensemble_context or {}).get("rain_q90_mm"),
                    "spread_mm": (ensemble_context or {}).get("rain_spread_mm"),
                    "probability_5": (ensemble_context or {}).get("rain_probability_5"),
                    "role": "UNCERTAINTY_CONTEXT_ONLY_LOCAL_ACTUAL_DOMINATES",
                },
                "note": "Fresh co-located VRain observation dominates this point. Remote gauges and model/ensemble remain context only.",
            }

        gauge_rate = weighted / weight_sum
        # Let a fresh co-located gauge dominate current-rain analysis. Model
        # contribution grows gradually only as the nearest gauge gets farther
        # away. This avoids inventing rain at Cửa Cạn/Bãi Thơm when the local
        # public gauge is currently dry.
        conv_factor = _clamp(0.65 + score / 125.0, 0.65, 1.45)
        model_signal = model_rate * conv_factor
        nearest = min(a["distance_km"] for a in anchors)
        # Base model contribution increases with distance from a real gauge.
        base_model_share = _clamp(nearest / 50.0 * 0.25, 0.0, 0.20)
        # A dry gauge several kilometres away is weak evidence for a convective
        # shower at the target point. During strong convection, restore part of
        # the local model/satellite signal instead of letting a remote zero gauge
        # suppress the target to near-zero.
        remote_gauge_uncertainty_share = (
            0.35
            * _clamp((nearest - 2.0) / 15.0, 0.0, 1.0)
            * _clamp((score - 60.0) / 30.0, 0.0, 1.0)
        )
        # A co-located dry gauge is ACTUAL evidence that rain is not reaching
        # the sensor yet, but it does not prove the surrounding/local field is
        # convection-free. When satellite/nowcast convection is strong, retain
        # a limited model contribution in ESTIMATED_NOW. ACTUAL remains separate.
        dry_near_gauge = nearest <= 1.5 and gauge_rate <= 0.01
        convective_model_share = (
            _clamp((score - 65.0) / 20.0 * 0.20, 0.0, 0.20)
            if dry_near_gauge else 0.0
        )
        model_share = max(base_model_share, convective_model_share, remote_gauge_uncertainty_share)
        model_share = _clamp(model_share, 0.0, 0.40)
        gauge_share = 1.0 - model_share
        estimate = gauge_share * gauge_rate + model_share * model_signal
        spatial_support = math.exp(-nearest / 25.0)
        network_support = min(1.0, weight_sum / 1.5)
        convective_penalty = 1.0 - 0.30 * _clamp(score / 100.0, 0.0, 1.0)
        confidence = (0.30 + 0.25 * spatial_support + 0.12 * network_support + 0.05 * min(len(anchors), 3)) * convective_penalty
        ens_spread = _num((ensemble_context or {}).get("rain_spread_mm"))
        if ens_spread is not None:
            confidence *= 1.0 - min(0.15, max(0.0, ens_spread) / 20.0 * 0.15)
        confidence = _clamp(confidence, 0.25, 0.78)
        return {
            "rain_rate_mm_h": round(max(0.0, estimate), 2),
            "data_class": "ESTIMATED_NOW",
            "method": "PQ_LOCAL_NOW_V2_GAUGE_CONVECTIVE_BLEND",
            "confidence": round(confidence, 2),
            "gauge_anchor_count": len(anchors),
            "gauge_anchors": anchors,
            "model_rain_3h_mm": model_rain_3h,
            "model_share": round(model_share, 3),
            "gauge_share": round(gauge_share, 3),
            "nearest_gauge_km": round(nearest, 1),
            "convective_score": score,
            "imminence": imminence,
            "remote_gauge_uncertainty_share": round(remote_gauge_uncertainty_share, 3),
            "ensemble_context": {
                "valid_time": (ensemble_context or {}).get("valid_time"),
                "gap_hours": (ensemble_context or {}).get("gap_hours"),
                "q50_mm": (ensemble_context or {}).get("rain_q50_mm"),
                "q90_mm": (ensemble_context or {}).get("rain_q90_mm"),
                "spread_mm": (ensemble_context or {}).get("rain_spread_mm"),
                "probability_5": (ensemble_context or {}).get("rain_probability_5"),
                "role": "UNCERTAINTY_CONTEXT_NOT_DIRECT_RAIN_OBSERVATION",
            },
            "note": "ACTUAL VRain remains separate from ESTIMATED_NOW. A dry co-located gauge remains strong evidence, while a remote dry gauge is down-weighted during strong convection so localized rain is not forced to near-zero.",
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
        "imminence": imminence,
        "airport_weather_support": airport_rain,
        "ensemble_context": {
            "valid_time": (ensemble_context or {}).get("valid_time"),
            "gap_hours": (ensemble_context or {}).get("gap_hours"),
            "q50_mm": (ensemble_context or {}).get("rain_q50_mm"),
            "q90_mm": (ensemble_context or {}).get("rain_q90_mm"),
            "spread_mm": (ensemble_context or {}).get("rain_spread_mm"),
            "probability_5": (ensemble_context or {}).get("rain_probability_5"),
            "role": "UNCERTAINTY_CONTEXT_NOT_DIRECT_RAIN_OBSERVATION",
        },
        "note": "Low-confidence estimate because no fresh gauge increment is available. Ensemble is context only, not an observation.",
    }


def build(groundtruth: dict, dashboard: dict, nowcast: dict, ensemble: dict | None = None, source_skill: dict | None = None) -> dict:
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
        ens_context = _ensemble_context(ensemble or {}, point_id, generated)
        corrected = _vvpq_correction(
            point_id, meta, model, anchor_model, vvpq,
            nowcast_points.get(point_id, {}), ens_context, source_skill,
        )
        rain = _rain_estimate(
            point_id, model["rain"], gauges, nowcast_points.get(point_id, {}), vvpq, ens_context, source_skill,
        )
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

    # Rạch Giá is a separate coastal reference. Do not transport
    # Phú Quốc VVPQ/VRain corrections across ~120 km of sea. With no connected
    # numeric ACTUAL feed, expose Rạch Giá as MODEL_ONLY + remote-sensing context.
    rg_id = "rach_gia"
    rg = points_model.get(rg_id, {})
    if rg:
        rg_row = _current_model_row(rg, dashboard_time)
        rg_model = {
            "temperature": _model_value(rg, rg_row, "temperature"),
            "wind": _model_value(rg, rg_row, "wind"),
            "gust": _model_value(rg, rg_row, "gust"),
            "rain": _model_value(rg, rg_row, "rain"),
            "wave": _model_value(rg, rg_row, "wave"),
            "wave_max": _model_value(rg, rg_row, "wave_max"),
            "period": _model_value(rg, rg_row, "period"),
            "current": _model_value(rg, rg_row, "current"),
        }
        rg_nowcast = nowcast_points.get(rg_id, {})
        rg_score = _convective_score(rg_nowcast)
        rg_ens = _ensemble_context(ensemble or {}, rg_id, generated)
        rain_rate = max(0.0, (rg_model["rain"] or 0.0) / 3.0)
        output_points[rg_id] = {
            "name": POINT_NAMES.get(rg_id, "Rạch Giá"),
            "lat": CANONICAL_POINTS[rg_id][0],
            "lon": CANONICAL_POINTS[rg_id][1],
            "reference_type": POINT_METADATA[rg_id].get("reference_type"),
            "analysis_time": generated.isoformat(),
            "temperature_c": rg_model["temperature"],
            "temperature": {
                "data_class": "MODEL_ONLY",
                "method": "DIRECT_MODEL_RACH_GIA",
                "confidence": 0.35,
            },
            "wind_kmh": rg_model["wind"],
            "wind_direction_deg": None,
            "wind": {
                "data_class": "MODEL_ONLY",
                "method": "DIRECT_MODEL_RACH_GIA",
                "baseline_model": rg_model["wind"],
                "model_gust_kmh": rg_model["gust"],
                "convective_score": rg_score,
                "ensemble_context": {
                    "valid_time": rg_ens.get("valid_time"),
                    "q50_kmh": rg_ens.get("wind_q50_kmh"),
                    "q90_kmh": rg_ens.get("wind_q90_kmh"),
                    "spread_kmh": rg_ens.get("wind_spread_kmh"),
                },
                "confidence": 0.35,
            },
            "rain": {
                "rain_rate_mm_h": round(rain_rate, 2),
                "data_class": "MODEL_ONLY",
                "method": "DIRECT_MODEL_RACH_GIA",
                "confidence": 0.30,
                "model_rain_3h_mm": rg_model["rain"],
                "convective_score": rg_score,
                "imminence": _rain_imminence(rg_model["rain"], rg_nowcast, rg_ens),
                "ensemble_context": {
                    "valid_time": rg_ens.get("valid_time"),
                    "q50_mm": rg_ens.get("rain_q50_mm"),
                    "q90_mm": rg_ens.get("rain_q90_mm"),
                    "spread_mm": rg_ens.get("rain_spread_mm"),
                    "probability_5": rg_ens.get("rain_probability_5"),
                    "role": "UNCERTAINTY_CONTEXT_NOT_OBSERVATION",
                },
                "note": "Rạch Giá currently uses direct model + Himawari context. Phú Quốc VVPQ/VRain are intentionally not transported here.",
            },
            "wave_hs_m": rg_model["wave"],
            "wave_hmax_m": rg_model["wave_max"],
            "wave_period_s": rg_model["period"],
            "current_kmh": rg_model["current"],
            "marine": {
                "data_class": "MODEL_ONLY",
                "method": "DIRECT_MARINE_MODEL_RACH_GIA",
                "confidence": None,
                "note": "Rạch Giá marine model reference; not in-situ observation.",
            },
            "actual_anchors": {},
        }

    return {
        "schema_version": "1.0",
        "engine": "PQ_LOCAL_NOW_V2",
        "generated_at": generated.isoformat(),
        "data_class": "ESTIMATED_NOW",
        "title": "PQ Local Now",
        "policy": {
            "actual": "VVPQ METAR + VRain gauges only when fresh numeric observations exist.",
            "estimated_now": "Observation-anchored local analysis. Ensemble spread/disagreement modulates background uncertainty; ensemble is not treated as an observation.",
            "marine": "MODEL_ONLY until a usable in-situ marine feed is available.",
            "feedback": "Field feedback calibrates categorical/event errors and later numeric coefficients; it never rewrites raw observations.",
        },
        "points": output_points,
        "source_status": {
            "vvpq": vvpq.get("status"),
            "vrain": groundtruth.get("rainfall", {}).get("status"),
            "himawari": nowcast.get("status") if isinstance(nowcast, dict) else "UNAVAILABLE",
            "ensemble": (ensemble or {}).get("status", "UNAVAILABLE"),
            "source_skill": (source_skill or {}).get("schema_version", "UNAVAILABLE"),
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
    parser.add_argument("--ensemble", type=Path)
    parser.add_argument("--source-skill", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    groundtruth = json.loads(args.groundtruth.read_text(encoding="utf-8"))
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    nowcast = json.loads(args.nowcast.read_text(encoding="utf-8")) if args.nowcast.exists() else {}
    ensemble = json.loads(args.ensemble.read_text(encoding="utf-8")) if args.ensemble and args.ensemble.exists() else {}
    source_skill = json.loads(args.source_skill.read_text(encoding="utf-8")) if args.source_skill and args.source_skill.exists() else {}
    result = build(groundtruth, dashboard, nowcast, ensemble, source_skill)
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
