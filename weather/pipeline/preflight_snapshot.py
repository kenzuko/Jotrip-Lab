"""Strict preflight for canonical LAB_SNAPSHOT_V1 before MASTER consumption."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from weather.pipeline.publish_snapshot import validate_snapshot
from weather.processing.snapshot import verify_snapshot

VN = ZoneInfo("Asia/Ho_Chi_Minh")
VALID_CYCLES = {"0600", "1800"}


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def infer_cycle(cutoff_time: str) -> str:
    local = _dt(cutoff_time).astimezone(VN)
    return "0600" if local.hour < 12 else "1800"


def preflight(snapshot: dict, *, max_age_minutes: int, expected_cycle: str | None = None,
              now: datetime | None = None) -> dict:
    if max_age_minutes <= 0:
        raise ValueError("max_age_minutes must be positive")
    if expected_cycle is not None and expected_cycle not in VALID_CYCLES:
        raise ValueError(f"expected_cycle must be one of {sorted(VALID_CYCLES)}")

    failures: list[str] = []
    checks: dict[str, object] = {}
    try:
        validate_snapshot(snapshot)
        checks["schema_contract"] = "PASS"
    except Exception as exc:  # deliberate: preflight must return a machine-readable failure
        failures.append(f"SCHEMA_CONTRACT:{type(exc).__name__}:{exc}")
        checks["schema_contract"] = "FAIL"

    hash_ok = verify_snapshot(snapshot)
    checks["payload_hash"] = "PASS" if hash_ok else "FAIL"
    if not hash_ok:
        failures.append("PAYLOAD_HASH_MISMATCH")

    cutoff = None
    generated = None
    try:
        cutoff = _dt(snapshot["cutoff_time"])
        generated = _dt(snapshot["generated_at"])
        checks["timestamps"] = "PASS"
    except Exception as exc:
        failures.append(f"TIMESTAMP_INVALID:{type(exc).__name__}:{exc}")
        checks["timestamps"] = "FAIL"

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    age_minutes = None
    if generated is not None:
        age_minutes = (clock.astimezone(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() / 60.0
        age_ok = 0 <= age_minutes <= max_age_minutes
        checks["freshness"] = "PASS" if age_ok else "FAIL"
        if not age_ok:
            failures.append(f"STALE_OR_FUTURE_SNAPSHOT:{age_minutes:.1f}m")
    else:
        checks["freshness"] = "FAIL"

    inferred_cycle = infer_cycle(snapshot["cutoff_time"]) if cutoff is not None else None
    if expected_cycle is None:
        checks["cycle"] = "NOT_REQUESTED"
    else:
        cycle_ok = inferred_cycle == expected_cycle
        checks["cycle"] = "PASS" if cycle_ok else "FAIL"
        if not cycle_ok:
            failures.append(f"CYCLE_MISMATCH:expected={expected_cycle}:actual={inferred_cycle}")

    required_points = {"duong_dong", "an_thoi", "ganh_dau"}
    point_ok = required_points.issubset(set(snapshot.get("points", {})))
    checks["production_points"] = "PASS" if point_ok else "FAIL"
    if not point_ok:
        failures.append("PRODUCTION_POINT_COVERAGE_INCOMPLETE")

    ensemble = snapshot.get("ensemble", {})
    p_window = ensemble.get("p_operational_window", {})
    full_matrix = bool(ensemble.get("gefs_atmosphere_member_gate", {}).get("full_matrix_complete")) and bool(
        ensemble.get("gefs_wave_member_gate", {}).get("full_matrix_complete")
    )
    if not full_matrix and p_window.get("status") != "NOT_COMPUTABLE":
        failures.append("ENSEMBLE_COHERENCE_GATE_VIOLATION")
        checks["ensemble_coherence"] = "FAIL"
    else:
        checks["ensemble_coherence"] = "PASS"

    valid = not failures
    source_mode = snapshot.get("data_mode") if snapshot.get("data_mode") in {"A", "B", "C"} else "C"
    recommended_mode = source_mode if valid else "C"
    report_status = "FULL" if valid and recommended_mode in {"A", "B"} else "DEGRADED"

    return {
        "snapshot_valid": valid,
        "snapshot_id": snapshot.get("snapshot_id"),
        "schema_version": snapshot.get("schema_version"),
        "payload_hash": snapshot.get("payload_hash"),
        "cutoff_time": snapshot.get("cutoff_time"),
        "generated_at": snapshot.get("generated_at"),
        "age_minutes": None if age_minutes is None else round(age_minutes, 2),
        "max_age_minutes": max_age_minutes,
        "expected_cycle": expected_cycle,
        "inferred_cycle": inferred_cycle,
        "source_data_mode": source_mode,
        "recommended_mode": recommended_mode,
        "report_status": report_status,
        "checks": checks,
        "failures": failures,
        "critical_data_gaps": snapshot.get("critical_data_gaps", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("weather/snapshots/latest.json"))
    parser.add_argument("--max-age-minutes", type=int, required=True)
    parser.add_argument("--expected-cycle", choices=sorted(VALID_CYCLES))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = preflight(
        _load(args.snapshot),
        max_age_minutes=args.max_age_minutes,
        expected_cycle=args.expected_cycle,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["snapshot_valid"] else 2)


if __name__ == "__main__":
    main()
