"""MASTER-side loader for canonical LAB_SNAPSHOT_V1.

The loader never substitutes dashboard-data.json, web forecasts, or stale numerics.
It either returns the exact validated canonical snapshot or no numerical layer.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from weather.pipeline.preflight_snapshot import preflight


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_validated_snapshot(path: Path, *, max_age_minutes: int,
                            expected_cycle: str | None = None,
                            now: datetime | None = None) -> tuple[dict | None, dict]:
    snapshot = _load(path)
    result = preflight(
        snapshot,
        max_age_minutes=max_age_minutes,
        expected_cycle=expected_cycle,
        now=now,
    )
    if not result["snapshot_valid"]:
        return None, result
    return snapshot, result


def consumer_status(path: Path, *, max_age_minutes: int,
                    expected_cycle: str | None = None,
                    now: datetime | None = None) -> dict:
    snapshot, result = load_validated_snapshot(
        path,
        max_age_minutes=max_age_minutes,
        expected_cycle=expected_cycle,
        now=now,
    )
    if snapshot is None:
        return {
            "consumer_status": "LAB_DATA_PLANE_DEGRADED",
            "recommended_mode": "C",
            "report_status": "DEGRADED",
            "numerical_model_layer": "UNAVAILABLE",
            "snapshot_id": result.get("snapshot_id"),
            "failures": result.get("failures", []),
            "preflight": result,
        }
    return {
        "consumer_status": "READY",
        "recommended_mode": result["recommended_mode"],
        "report_status": result["report_status"],
        "numerical_model_layer": "AVAILABLE",
        "snapshot_id": snapshot["snapshot_id"],
        "payload_hash": snapshot["payload_hash"],
        "cutoff_time": snapshot["cutoff_time"],
        "preflight": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("weather/snapshots/latest.json"))
    parser.add_argument("--max-age-minutes", type=int, required=True)
    parser.add_argument("--expected-cycle", choices=["0600", "1800"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = consumer_status(
        args.snapshot,
        max_age_minutes=args.max_age_minutes,
        expected_cycle=args.expected_cycle,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["consumer_status"] == "READY" else 2)


if __name__ == "__main__":
    main()
