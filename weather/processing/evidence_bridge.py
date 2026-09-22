"""Bridge Weather V2 production evidence into canonical LAB snapshots.

The bridge preserves semantic classes:
- ACTUAL: machine-readable in-situ observations only.
- ESTIMATED_NOW: observation-anchored local analysis, never relabelled ACTUAL.
- OBSERVED_SATELLITE: Himawari convective context, never relabelled lightning.
- ENSEMBLE: GEFS member matrix summaries, separate from the +3h gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _same_authority(point: dict[str, Any], authority: dict[str, Any]) -> bool:
    try:
        return float(point["lat"]) == float(authority["lat"]) and float(point["lon"]) == float(authority["lon"])
    except (KeyError, TypeError, ValueError):
        return False


def _compact_actual(current_bundle: dict[str, Any]) -> dict[str, Any]:
    gt = current_bundle.get("groundtruth") or {}
    atmosphere = gt.get("atmosphere") or {}
    rainfall = gt.get("rainfall") or {}
    vvpq = atmosphere.get("vvpq") or {}
    stations = rainfall.get("stations") or {}
    return {
        "status": gt.get("status", "UNAVAILABLE"),
        "generated_at": gt.get("generated_at"),
        "policy": gt.get("actual_policy"),
        "vvpq": vvpq if vvpq.get("data_class") == "ACTUAL" else {},
        "rainfall": {
            "status": rainfall.get("status"),
            "source": rainfall.get("source"),
            "stations": {
                key: value for key, value in stations.items()
                if value.get("data_class") == "ACTUAL"
            },
        },
    }


def _compact_local_now(current_bundle: dict[str, Any], point_authority: dict[str, Any]) -> dict[str, Any]:
    local = current_bundle.get("local_now") or {}
    points: dict[str, Any] = {}
    for point_id in sorted(point_authority):
        point = (local.get("points") or {}).get(point_id)
        authority = point_authority.get(point_id) or {}
        if not isinstance(point, dict):
            points[point_id] = {"status": "NOT_AVAILABLE"}
            continue
        if not _same_authority(point, authority):
            points[point_id] = {
                "status": "NOT_COMPARABLE",
                "reason": "POINT_AUTHORITY_CHANGED_OR_UNAVAILABLE",
                "source_lat": point.get("lat"),
                "source_lon": point.get("lon"),
                "authority_lat": authority.get("lat"),
                "authority_lon": authority.get("lon"),
            }
            continue
        points[point_id] = {
            "status": "AVAILABLE",
            "data_class": local.get("data_class", "ESTIMATED_NOW"),
            "analysis_time": point.get("analysis_time"),
            "temperature_c": point.get("temperature_c"),
            "wind_kmh": point.get("wind_kmh"),
            "wind": point.get("wind"),
            "rain": point.get("rain"),
            "wave_hs_m": point.get("wave_hs_m"),
            "wave_hmax_m": point.get("wave_hmax_m"),
            "wave_period_s": point.get("wave_period_s"),
            "current_kmh": point.get("current_kmh"),
            "marine": point.get("marine"),
            "actual_anchors": point.get("actual_anchors"),
        }
    return {
        "engine": local.get("engine"),
        "generated_at": local.get("generated_at"),
        "data_class": local.get("data_class", "ESTIMATED_NOW"),
        "points": points,
    }


def _compact_nowcast(nowcast: dict[str, Any], point_authority: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": nowcast.get("status", "UNAVAILABLE"),
        "source": nowcast.get("source"),
        "sampled_time": nowcast.get("sampled_time"),
        "generated_at": nowcast.get("generated_at"),
        "data_class": "OBSERVED_SATELLITE",
        "lightning_observed": nowcast.get("lightning_observed"),
        "points": {
            point_id: (nowcast.get("points") or {}).get(point_id)
            for point_id in sorted(point_authority)
            if point_id in (nowcast.get("points") or {})
        },
    }


def _distribution(dist: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "q25", "q50", "q75", "q90", "q95", "spread",
        "exceedance_probability", "exceedance_threshold",
        "completion_ratio", "member_count",
    )
    return {key: dist.get(key) for key in keep if key in dist}


def _compact_local_ensemble(local_ensemble: dict[str, Any], cutoff_time: str,
                            point_authority: dict[str, Any]) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(cutoff_time.replace("Z", "+00:00"))
    end = cutoff + timedelta(hours=72)
    points: dict[str, Any] = {}
    for point_id in sorted(point_authority):
        rows = []
        for row in (local_ensemble.get("points") or {}).get(point_id, []):
            valid = row.get("valid_time")
            if not valid:
                continue
            dt = datetime.fromisoformat(valid.replace("Z", "+00:00"))
            if not (cutoff <= dt <= end):
                continue
            variables = {}
            for variable, payload in (row.get("variables") or {}).items():
                variables[variable] = {
                    "status": payload.get("status"),
                    "raw": _distribution(payload.get("raw") or {}),
                    "corrected": _distribution(payload.get("corrected") or {}),
                    "local_exposure": payload.get("local_exposure") if variable == "wind" else None,
                }
            rows.append({
                "lead_hours": row.get("lead_hours"),
                "valid_time": valid,
                "member_count": row.get("member_count"),
                "expected_members": row.get("expected_members"),
                "variables": variables,
            })
        points[point_id] = rows

    completion = local_ensemble.get("completion_ratio")
    try:
        eligible = float(completion) >= 0.75
    except (TypeError, ValueError):
        eligible = False

    return {
        "status": local_ensemble.get("status", "UNAVAILABLE"),
        "readiness": local_ensemble.get("readiness"),
        "source": local_ensemble.get("source"),
        "model": local_ensemble.get("model"),
        "run_time": local_ensemble.get("run_time"),
        "generated_at": local_ensemble.get("generated_at"),
        "horizon_hours": local_ensemble.get("horizon_hours"),
        "requested_horizon_hours": local_ensemble.get("requested_horizon_hours"),
        "completion_ratio": completion,
        "coherence_gate_75pct": "PASS" if eligible else "FAIL",
        "calibration_engine": local_ensemble.get("calibration_engine"),
        "calibration_status": local_ensemble.get("calibration_status"),
        "points_d0_d3": points,
        "note": "Atmospheric local GEFS matrix. This does not by itself unlock P_operational_window because coherent marine ensemble coverage is also required.",
    }


def build_evidence_bridge(*, current_bundle: dict[str, Any] | None,
                          nowcast: dict[str, Any] | None,
                          local_ensemble: dict[str, Any] | None,
                          point_authority: dict[str, Any],
                          cutoff_time: str) -> dict[str, Any]:
    current_bundle = current_bundle or {}
    nowcast = nowcast or {}
    local_ensemble = local_ensemble or {}
    return {
        "actual": _compact_actual(current_bundle),
        "local_now": _compact_local_now(current_bundle, point_authority),
        "nowcast": _compact_nowcast(nowcast, point_authority),
        "ensemble_local": _compact_local_ensemble(local_ensemble, cutoff_time, point_authority),
    }
