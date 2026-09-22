"""Forecast verification and observation-trained calibration for JoTrip Weather.

This module closes the loop:
FORECAST (archived before validity) -> ACTUAL -> ERROR -> CALIBRATION.

Safety rules:
- Only ACTUAL VVPQ/VRain observations may train coefficients.
- ESTIMATED_NOW is never a training label.
- Calibration is shrinkage-gated and is not applied until >=30 matched cases
  exist for the relevant target / variable / lead bucket.
- Rain verification requires >=70% temporal coverage of the forecast
  accumulation window.
"""
from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from weather.processing.ensemble_local import (
    DEFAULT_MIN_SAMPLES,
    learn_additive_bias,
    learn_rain_factor,
)

LEAD_BUCKETS = (
    ("D0_24", 0, 24),
    ("D1_48", 25, 48),
    ("D2_72", 49, 72),
    ("D3_5", 73, 120),
    ("D6_10", 121, 240),
)
RAIN_COVERAGE_MIN = 0.70
RAIN_EVENT_THRESHOLD_MM = 0.10
RAIN_MIN_WET_SAMPLES = 10
RAIN_BOUNDARY_TOLERANCE_MINUTES = 45
VVPQ_TOLERANCE_MINUTES = 45
EXPECTED_TARGET_VARIABLES = {
    "vvpq": ("temperature", "wind"),
    "vrain_cua_can": ("rain",),
    "vrain_bai_thom": ("rain",),
    "vrain_an_thoi": ("rain",),
}


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lead_bucket(lead_hours: Any) -> str | None:
    lead = _num(lead_hours)
    if lead is None:
        return None
    for name, lo, hi in LEAD_BUCKETS:
        if lo <= lead <= hi:
            return name
    return None


def _json_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*.json"):
        if p.name in {"latest.json", "health.json", "local-now.json"}:
            continue
        if "analysis" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def _load(path: Path) -> dict | None:
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _groundtruth_payloads(root: Path, current: Path | None = None) -> list[dict]:
    payloads: list[dict] = []
    seen: set[str] = set()
    for path in _json_files(root):
        p = _load(path)
        if not p:
            continue
        key = str(p.get("generated_at") or path)
        if key not in seen:
            seen.add(key)
            payloads.append(p)
    if current and current.exists():
        p = _load(current)
        if p:
            key = str(p.get("generated_at") or current)
            if key not in seen:
                payloads.append(p)
    return payloads


def build_actual_index(payloads: list[dict]) -> dict:
    vvpq: dict[str, dict] = {}
    rain: dict[str, dict[str, dict]] = {
        "vrain_cua_can": {},
        "vrain_bai_thom": {},
        "vrain_an_thoi": {},
    }
    station_map = {
        "cua_can": "vrain_cua_can",
        "bai_thom": "vrain_bai_thom",
        "an_thoi": "vrain_an_thoi",
    }

    for p in payloads:
        obs = (p.get("atmosphere") or {}).get("vvpq") or {}
        t = _dt(obs.get("observed_at"))
        if (
            t
            and obs.get("data_class") == "ACTUAL"
            and obs.get("qc") == "PASS"
        ):
            vvpq[t.isoformat()] = {
                "time": t,
                "temperature": _num(obs.get("temperature_c")),
                "wind": _num(obs.get("wind_speed_kmh")),
            }

        stations = (p.get("rainfall") or {}).get("stations") or {}
        for key, s in stations.items():
            target = station_map.get(key)
            if not target:
                continue
            end = _dt(s.get("period_end") or s.get("observed_at"))
            if not end or s.get("data_class") != "ACTUAL" or s.get("qc") != "PASS":
                continue
            unique = end.isoformat()
            rain[target][unique] = {
                "end": end,
                "increment_mm": _num(s.get("increment_mm")),
                "window_minutes": _num(s.get("increment_window_minutes")),
                "increment_qc": s.get("increment_qc"),
                "accumulation_mm": _num(s.get("accumulation_mm")),
                "period_start": _dt(s.get("period_start")),
            }

    vvpq_rows = sorted(vvpq.values(), key=lambda x: x["time"])
    rain_rows = {
        key: sorted(rows.values(), key=lambda x: x["end"])
        for key, rows in rain.items()
    }
    return {"vvpq": vvpq_rows, "rain": rain_rows}


def _nearest_vvpq(rows: list[dict], valid: datetime) -> dict | None:
    if not rows:
        return None
    times = [r["time"] for r in rows]
    i = bisect_left(times, valid)
    candidates = rows[max(0, i - 2): min(len(rows), i + 2)]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: abs((r["time"] - valid).total_seconds()))
    delta = abs((best["time"] - valid).total_seconds()) / 60.0
    return best if delta <= VVPQ_TOLERANCE_MINUTES else None


def _rain_actual(rows: list[dict], start: datetime, end: datetime) -> tuple[float | None, float]:
    """Return ACTUAL rain accumulation and temporal coverage for a forecast window.

    Preferred path sums short, QC-passed gauge increments. If collector cadence has
    gaps, fall back to differencing the gauge's cumulative counter at the window
    boundaries. The fallback is only accepted when both boundary observations are
    close enough, belong to the same accumulation period, and the counter did not
    reset. This keeps sparse GitHub scheduling from discarding otherwise valid
    physical gauge evidence without inventing rainfall between observations.
    """
    if end <= start:
        return None, 0.0

    expected = (end - start).total_seconds() / 60.0
    total = 0.0
    coverage_minutes = 0.0
    used = 0
    for r in rows:
        if not (start < r["end"] <= end):
            continue
        if r.get("increment_qc") != "PASS":
            continue
        inc = _num(r.get("increment_mm"))
        window = _num(r.get("window_minutes"))
        if inc is None or window is None or window <= 0:
            continue
        total += max(0.0, inc)
        coverage_minutes += window
        used += 1

    coverage = min(1.0, coverage_minutes / expected) if expected > 0 else 0.0
    if used > 0 and coverage >= RAIN_COVERAGE_MIN:
        return total, coverage

    # Cadence-gap fallback: derive an accumulation from the station's cumulative
    # counter. Do not bridge a source reset or an accumulation-period boundary.
    cumulative = [
        r for r in rows
        if _num(r.get("accumulation_mm")) is not None
        and isinstance(r.get("end"), datetime)
        and isinstance(r.get("period_start"), datetime)
    ]
    if not cumulative:
        return None, coverage

    def nearest_boundary(target: datetime) -> tuple[dict | None, float]:
        best = min(cumulative, key=lambda r: abs((r["end"] - target).total_seconds()))
        delta_min = abs((best["end"] - target).total_seconds()) / 60.0
        return (best, delta_min) if delta_min <= RAIN_BOUNDARY_TOLERANCE_MINUTES else (None, delta_min)

    left, left_gap = nearest_boundary(start)
    right, right_gap = nearest_boundary(end)
    if not left or not right or right["end"] <= left["end"]:
        return None, coverage
    if left.get("period_start") != right.get("period_start"):
        return None, coverage

    a0 = _num(left.get("accumulation_mm"))
    a1 = _num(right.get("accumulation_mm"))
    if a0 is None or a1 is None or a1 < a0 - 0.05:
        return None, coverage

    boundary_coverage = max(0.0, min(1.0, 1.0 - (left_gap + right_gap) / expected)) if expected > 0 else 0.0
    if boundary_coverage < RAIN_COVERAGE_MIN:
        return None, max(coverage, boundary_coverage)
    return max(0.0, a1 - a0), boundary_coverage


def _forecast_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.json") if p.name not in {"latest.json", "health.json"})


def build_cases(forecast_root: Path, actual_index: dict) -> list[dict]:
    cases: list[dict] = []
    for path in _forecast_files(forecast_root):
        f = _load(path)
        if not f:
            continue
        run = _dt(f.get("run_time"))
        points = f.get("verification_points") or f.get("points") or {}
        if not run or not isinstance(points, dict):
            continue
        for target, rows in points.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                valid = _dt(row.get("valid_time"))
                lead = _num(row.get("lead_hours"))
                bucket = lead_bucket(lead)
                if not valid or lead is None or not bucket:
                    continue

                if target == "vvpq":
                    actual = _nearest_vvpq(actual_index.get("vvpq") or [], valid)
                    if not actual:
                        continue
                    for variable, key in (("temperature", "temperature_q50_c"), ("wind", "wind_q50_kmh")):
                        obs = _num(actual.get(variable))
                        fcst = _num(row.get(key))
                        if obs is None or fcst is None:
                            continue
                        cases.append({
                            "target": target,
                            "variable": variable,
                            "lead_bucket": bucket,
                            "lead_hours": lead,
                            "run_time": run.isoformat(),
                            "valid_time": valid.isoformat(),
                            "forecast": fcst,
                            "observed": obs,
                            "observation_class": "ACTUAL",
                            "error": obs - fcst,
                            "source_file": str(path),
                        })

                elif target.startswith("vrain_"):
                    fcst = _num(row.get("rain_q50_mm"))
                    if fcst is None:
                        continue
                    period_start_lead = _num(row.get("rain_period_start_lead"))
                    if period_start_lead is None:
                        period_start_lead = max(0.0, lead - 6.0)
                    start = run + timedelta(hours=period_start_lead)
                    obs, coverage = _rain_actual((actual_index.get("rain") or {}).get(target, []), start, valid)
                    if obs is None:
                        continue
                    cases.append({
                        "target": target,
                        "variable": "rain",
                        "lead_bucket": bucket,
                        "lead_hours": lead,
                        "run_time": run.isoformat(),
                        "valid_time": valid.isoformat(),
                        "forecast": fcst,
                        "observed": obs,
                        "observation_class": "ACTUAL",
                        "error": obs - fcst,
                        "coverage": round(coverage, 4),
                        "window_start": start.isoformat(),
                        "source_file": str(path),
                    })
    return cases


def _rain_event_metrics(cases: list[dict], threshold_mm: float = RAIN_EVENT_THRESHOLD_MM) -> dict:
    """Contingency-table verification for measurable-rain occurrence.

    This is deliberately separate from amount calibration: a forecast must learn
    whether rain happened, not look good merely because most verification windows
    were dry.
    """
    hit = miss = false_alarm = correct_dry = 0
    actual_wet = forecast_wet = 0
    for c in cases:
        if str(c.get("observation_class", "")).upper() != "ACTUAL":
            continue
        obs = _num(c.get("observed"))
        fcst = _num(c.get("forecast"))
        if obs is None or fcst is None or obs < 0 or fcst < 0:
            continue
        o_wet = obs >= threshold_mm
        f_wet = fcst >= threshold_mm
        actual_wet += int(o_wet)
        forecast_wet += int(f_wet)
        if o_wet and f_wet:
            hit += 1
        elif o_wet:
            miss += 1
        elif f_wet:
            false_alarm += 1
        else:
            correct_dry += 1

    total = hit + miss + false_alarm + correct_dry
    pod = hit / (hit + miss) if hit + miss else None
    far = false_alarm / (hit + false_alarm) if hit + false_alarm else None
    csi = hit / (hit + miss + false_alarm) if hit + miss + false_alarm else None
    return {
        "threshold_mm": threshold_mm,
        "sample_count": total,
        "actual_wet_cases": actual_wet,
        "forecast_wet_cases": forecast_wet,
        "hit": hit,
        "miss": miss,
        "false_alarm": false_alarm,
        "correct_dry": correct_dry,
        "probability_of_detection": round(pod, 4) if pod is not None else None,
        "false_alarm_ratio": round(far, 4) if far is not None else None,
        "critical_success_index": round(csi, 4) if csi is not None else None,
    }


def _metrics(cases: list[dict]) -> dict:
    errors = [_num(c.get("error")) for c in cases]
    errors = [x for x in errors if x is not None]
    if not errors:
        return {
            "sample_count": 0,
            "mae": None,
            "rmse": None,
            "mean_error": None,
            "median_error": None,
        }
    return {
        "sample_count": len(errors),
        "mae": round(mean(abs(x) for x in errors), 4),
        "rmse": round(math.sqrt(mean(x * x for x in errors)), 4),
        "mean_error": round(mean(errors), 4),
        "median_error": round(median(errors), 4),
    }


def build_calibration(cases: list[dict], min_samples: int = DEFAULT_MIN_SAMPLES) -> dict:
    targets: dict[str, dict] = {}
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for c in cases:
        key = (str(c["target"]), str(c["variable"]), str(c["lead_bucket"]))
        grouped.setdefault(key, []).append(c)

    for target, variables in EXPECTED_TARGET_VARIABLES.items():
        for variable in variables:
            for bucket, _, _ in LEAD_BUCKETS:
                grouped.setdefault((target, variable, bucket), [])

    ready = 0
    total = 0
    for (target, variable, bucket), rows in sorted(grouped.items()):
        if variable == "rain":
            cal = learn_rain_factor(rows, min_samples=min_samples)
            events = _rain_event_metrics(rows)
            cal["event_verification"] = events
            # Thirty mostly-dry windows are not enough evidence to learn rainfall
            # amount. Require a minimum number of physically observed wet cases
            # before a rain factor can affect production.
            if cal.get("status") == "READY" and events["actual_wet_cases"] < RAIN_MIN_WET_SAMPLES:
                cal["status"] = "LEARNING"
                cal["applied_factor"] = 1.0
                cal["readiness_reason"] = "INSUFFICIENT_ACTUAL_WET_CASES"
            elif cal.get("status") == "READY":
                cal["readiness_reason"] = "MATCHED_AND_WET_SAMPLE_THRESHOLDS_MET"
            else:
                cal["readiness_reason"] = "INSUFFICIENT_MATCHED_CASES"
        else:
            cal = learn_additive_bias(rows, min_samples=min_samples)
        total += 1
        if cal.get("status") == "READY":
            ready += 1
        cal["metrics"] = _metrics(rows)
        cal["lead_bucket"] = bucket
        targets.setdefault(target, {}).setdefault(variable, {})[bucket] = cal

    return {
        "schema_version": "1.0",
        "engine": "PQ_ENSEMBLE_LOCAL_V1",
        "generated_at": _iso_now(),
        "minimum_samples": min_samples,
        "ready_groups": ready,
        "total_groups": total,
        "status": "READY" if total and ready == total else ("PARTIAL" if ready else "LEARNING"),
        "targets": targets,
        "training_policy": {
            "allowed_observation_class": "ACTUAL",
            "estimated_now_allowed": False,
            "rain_min_temporal_coverage": RAIN_COVERAGE_MIN,
            "rain_event_threshold_mm": RAIN_EVENT_THRESHOLD_MM,
            "rain_min_actual_wet_samples": RAIN_MIN_WET_SAMPLES,
            "rain_boundary_tolerance_minutes": RAIN_BOUNDARY_TOLERANCE_MINUTES,
            "vvpq_match_tolerance_minutes": VVPQ_TOLERANCE_MINUTES,
        },
    }


def _latest_actual_summary(actual_index: dict) -> dict:
    vvpq_rows = actual_index.get("vvpq") or []
    rain_rows = actual_index.get("rain") or {}
    out = {"vvpq": None, "rain": {}}
    if vvpq_rows:
        r = vvpq_rows[-1]
        out["vvpq"] = {
            "observed_at": r["time"].isoformat(),
            "temperature_c": r.get("temperature"),
            "wind_kmh": r.get("wind"),
        }
    for target, rows in rain_rows.items():
        if not rows:
            continue
        r = rows[-1]
        out["rain"][target] = {
            "observed_at": r["end"].isoformat(),
            "increment_mm": r.get("increment_mm"),
            "window_minutes": r.get("window_minutes"),
            "increment_qc": r.get("increment_qc"),
            "accumulation_mm": r.get("accumulation_mm"),
        }
    return out


def build_analytics(cases: list[dict], calibration: dict, actual_index: dict, forecast_files: int, groundtruth_files: int) -> dict:
    groups = []
    for target, variables in (calibration.get("targets") or {}).items():
        for variable, buckets in variables.items():
            for bucket, cal in buckets.items():
                m = cal.get("metrics") or {}
                group = {
                    "target": target,
                    "variable": variable,
                    "lead_bucket": bucket,
                    "sample_count": cal.get("sample_count", 0),
                    "status": cal.get("status"),
                    "mae": m.get("mae"),
                    "rmse": m.get("rmse"),
                    "mean_error": m.get("mean_error"),
                    "median_error": m.get("median_error"),
                    "applied_bias": cal.get("applied_bias"),
                    "applied_factor": cal.get("applied_factor"),
                    "shrinkage": cal.get("shrinkage"),
                    "readiness_reason": cal.get("readiness_reason"),
                }
                if variable == "rain":
                    group["event_verification"] = cal.get("event_verification")
                groups.append(group)

    recent = sorted(cases, key=lambda c: c.get("valid_time") or "", reverse=True)[:120]
    return {
        "schema_version": "1.0",
        "product": "JOTRIP_WEATHER_ANALYTICS",
        "generated_at": _iso_now(),
        "learning_status": calibration.get("status"),
        "minimum_samples": calibration.get("minimum_samples"),
        "ready_groups": calibration.get("ready_groups"),
        "total_groups": calibration.get("total_groups"),
        "matched_cases": len(cases),
        "forecast_archive_files": forecast_files,
        "groundtruth_archive_files": groundtruth_files,
        "groups": groups,
        "latest_actual": _latest_actual_summary(actual_index),
        "recent_cases": recent,
        "policy": {
            "training_labels": "ACTUAL only",
            "estimated_now_is_training_label": False,
            "activation_rule": "A coefficient affects production only after its group reaches the minimum matched sample count.",
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--forecast-root", type=Path, required=True)
    p.add_argument("--groundtruth-root", type=Path, required=True)
    p.add_argument("--current-groundtruth", type=Path)
    p.add_argument("--output-calibration", type=Path, required=True)
    p.add_argument("--output-analytics", type=Path, required=True)
    p.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    a = p.parse_args()

    payloads = _groundtruth_payloads(a.groundtruth_root, a.current_groundtruth)
    actual_index = build_actual_index(payloads)
    cases = build_cases(a.forecast_root, actual_index)
    calibration = build_calibration(cases, min_samples=a.min_samples)
    analytics = build_analytics(
        cases,
        calibration,
        actual_index,
        forecast_files=len(_forecast_files(a.forecast_root)),
        groundtruth_files=len(payloads),
    )

    a.output_calibration.parent.mkdir(parents=True, exist_ok=True)
    a.output_analytics.parent.mkdir(parents=True, exist_ok=True)
    a.output_calibration.write_text(json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    a.output_analytics.write_text(json.dumps(analytics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "matched_cases": len(cases),
        "learning_status": calibration.get("status"),
        "ready_groups": calibration.get("ready_groups"),
        "total_groups": calibration.get("total_groups"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
