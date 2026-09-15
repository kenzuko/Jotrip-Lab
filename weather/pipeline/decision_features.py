"""Deterministic composition of calculation-ready evidence into decision features."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from weather.processing.decision import decide_product
from weather.processing.drift import compare_run_series
from weather.processing.operational_probability import operational_window_probability
from weather.processing.rainfall import cumulative_to_increment, rolling_accumulation
from weather.processing.route import summarize_route_timeseries
from weather.processing.window import detect_windows


FORMULA_BUNDLE = "weather-lab-0.2.0"


def build_decision_features(payload: dict) -> dict:
    thresholds = payload["thresholds"]
    required = payload["required_variables"]
    windows = detect_windows(payload.get("time_rows", []), thresholds, required)
    route = summarize_route_timeseries(payload.get("route_samples", []))
    rain = cumulative_to_increment(payload.get("cumulative_rain", []))
    rain_windows = {f"{hours}h": rolling_accumulation(rain, hours) for hours in (3, 6, 24)} if rain else {}
    probability = operational_window_probability(
        payload.get("ensemble_window_records", []), payload["operational_envelope"],
        expected_members=int(payload["expected_members"]),
    )
    drift_runs = payload.get("drift_runs", [])
    drift = compare_run_series(drift_runs) if drift_runs else {"status": "NOT_COMPUTABLE", "reason": "NO_ARCHIVE"}
    decision = decide_product(restriction=payload.get("restriction", "UNKNOWN"), windows=windows,
                              critical_missing=payload.get("critical_missing", []),
                              actual_hazard=bool(payload.get("actual_hazard", False)))
    return {"formula_bundle_version": FORMULA_BUNDLE, "windows": windows, "route": route,
            "rain_increment": rain, "rain_windows": rain_windows,
            "operational_probability": probability, "drift": drift, "decision": decision}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_decision_features(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result["decision"]["decision"], result["operational_probability"]["status"])
