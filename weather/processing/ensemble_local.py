"""Observation-trained local correction for ensemble forecasts.

Public name: PQ Ensemble Local
Internal version: PQ_ENSEMBLE_LOCAL_V1

Rules:
- Never learn from estimated observations.
- Require a minimum matched sample count before applying correction.
- Correct each ensemble member, then recompute quantiles/probabilities.
- Smooth variables use additive bias. Wind should be learned on U/V when available.
- Precipitation uses a multiplicative log-ratio factor.
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable

ENGINE = "PQ_ENSEMBLE_LOCAL_V1"
DEFAULT_MIN_SAMPLES = 30
DEFAULT_SHRINK_K = 30.0
EPS_RAIN_MM = 0.1


def _finite(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def shrinkage(n: int, k: float = DEFAULT_SHRINK_K) -> float:
    if n <= 0:
        return 0.0
    return float(n) / (float(n) + max(1e-9, float(k)))


def learn_additive_bias(cases: Iterable[dict], *, min_samples: int = DEFAULT_MIN_SAMPLES,
                        shrink_k: float = DEFAULT_SHRINK_K) -> dict:
    errors: list[float] = []
    for case in cases:
        if str(case.get("observation_class", "ACTUAL")).upper() != "ACTUAL":
            continue
        obs = _finite(case.get("observed"))
        fcst = _finite(case.get("forecast"))
        if obs is None or fcst is None:
            continue
        errors.append(obs - fcst)
    n = len(errors)
    raw = median(errors) if errors else 0.0
    lam = shrinkage(n, shrink_k)
    status = "READY" if n >= min_samples else "LEARNING"
    return {
        "engine": ENGINE,
        "status": status,
        "sample_count": n,
        "minimum_samples": min_samples,
        "shrinkage": round(lam, 4),
        "raw_median_bias": round(raw, 6),
        "applied_bias": round(raw * lam, 6) if status == "READY" else 0.0,
        "method": "SHRUNK_MEDIAN_ADDITIVE_BIAS",
    }


def learn_rain_factor(cases: Iterable[dict], *, min_samples: int = DEFAULT_MIN_SAMPLES,
                      shrink_k: float = DEFAULT_SHRINK_K, eps_mm: float = EPS_RAIN_MM) -> dict:
    logs: list[float] = []
    for case in cases:
        if str(case.get("observation_class", "ACTUAL")).upper() != "ACTUAL":
            continue
        obs = _finite(case.get("observed"))
        fcst = _finite(case.get("forecast"))
        if obs is None or fcst is None or obs < 0 or fcst < 0:
            continue
        logs.append(math.log((obs + eps_mm) / (fcst + eps_mm)))
    n = len(logs)
    raw_log = median(logs) if logs else 0.0
    lam = shrinkage(n, shrink_k)
    status = "READY" if n >= min_samples else "LEARNING"
    factor = math.exp(lam * raw_log) if status == "READY" else 1.0
    return {
        "engine": ENGINE,
        "status": status,
        "sample_count": n,
        "minimum_samples": min_samples,
        "shrinkage": round(lam, 4),
        "raw_median_log_ratio": round(raw_log, 6),
        "applied_factor": round(factor, 6),
        "method": "SHRUNK_MEDIAN_LOG_RATIO",
        "epsilon_mm": eps_mm,
    }


def apply_member_correction(values: Iterable[Any], calibration: dict, *, variable: str) -> list[float]:
    out: list[float] = []
    rain = variable.lower() in {"rain", "precipitation", "tp", "rain_mm"}
    ready = calibration.get("status") == "READY"
    for value in values:
        x = _finite(value)
        if x is None:
            continue
        if not ready:
            y = x
        elif rain:
            y = max(0.0, x * float(calibration.get("applied_factor", 1.0)))
        else:
            y = x + float(calibration.get("applied_bias", 0.0))
        out.append(float(y))
    return out


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = max(0.0, min(1.0, q)) * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def summarize_members(values: Iterable[Any], *, threshold: float | None = None) -> dict:
    xs = [x for v in values if (x := _finite(v)) is not None]
    if not xs:
        return {"member_count": 0, "q50": None, "q90": None, "q95": None, "spread": None,
                "exceedance_probability": None}
    q25, q50, q75 = quantile(xs, .25), quantile(xs, .50), quantile(xs, .75)
    probability = None
    if threshold is not None:
        probability = sum(x >= threshold for x in xs) / len(xs)
    return {
        "member_count": len(xs),
        "q50": round(q50, 6),
        "q90": round(quantile(xs, .90), 6),
        "q95": round(quantile(xs, .95), 6),
        "spread": round(q75 - q25, 6),
        "exceedance_threshold": threshold,
        "exceedance_probability": round(probability, 4) if probability is not None else None,
    }


def correct_distribution(values: Iterable[Any], calibration: dict, *, variable: str,
                         threshold: float | None = None) -> dict:
    raw = [x for v in values if (x := _finite(v)) is not None]
    corrected = apply_member_correction(raw, calibration, variable=variable)
    return {
        "engine": ENGINE,
        "status": "CALIBRATED" if calibration.get("status") == "READY" else "LEARNING",
        "variable": variable,
        "calibration": calibration,
        "raw": summarize_members(raw, threshold=threshold),
        "corrected": summarize_members(corrected, threshold=threshold),
        "member_values_corrected": corrected,
        "rule": "Correct individual members first, then recompute distribution statistics.",
    }
