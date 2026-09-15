"""Publish canonical LAB_SNAPSHOT_V1 beside the existing Weather Lab dashboard payload.

This module is intentionally additive: it never rewrites dashboard-data.json. It
turns the same CI-verified source artifacts used by the dashboard into a sealed,
immutable Decision Plane input and a stable latest.json consumer path.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather.processing.snapshot import seal_snapshot, verify_snapshot

SCHEMA_VERSION = "1.0"
FORMULA_BUNDLE_VERSION = "weather-lab-0.2.0"
REQUIRED_POINTS = {"duong_dong", "an_thoi", "ganh_dau"}


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.getenv("GITHUB_SHA", "UNKNOWN")


def _source_state(name: str, readiness: str, qc: str, **extra: Any) -> dict[str, Any]:
    return {"source": name, "readiness": readiness, "qc": qc, **extra}


def _direct_status(ecmwf: dict, gefs: dict, icon: dict, copernicus: dict) -> dict[str, dict[str, Any]]:
    atmosphere = gefs.get("atmosphere", {})
    wave = gefs.get("wave", {})
    return {
        "ECMWF_DIRECT": _source_state(
            "ECMWF",
            ecmwf.get("readiness", "UNAVAILABLE"),
            "PASS" if ecmwf.get("readiness") == "POINT_ROUTE_EXTRACTED" else "PARTIAL",
            run_time=ecmwf.get("run_time"),
            medium_run_time=ecmwf.get("medium_run_time"),
            horizon_hours=ecmwf.get("horizon_hours"),
            record_count=ecmwf.get("record_count"),
        ),
        "NOAA_GEFS_DIRECT": _source_state(
            "GEFS",
            atmosphere.get("readiness", "UNAVAILABLE"),
            "PASS" if atmosphere.get("readiness") == "MEMBER_COMPLETE" else "PARTIAL",
            run_time=atmosphere.get("run_time"),
            scope="LEAD_3H_MEMBER_GATE_ONLY",
            full_matrix_complete=False,
            expected_members=atmosphere.get("summary", {}).get("expected_members"),
            completed_members=atmosphere.get("summary", {}).get("member_count"),
            completion_ratio=atmosphere.get("summary", {}).get("completion_ratio"),
        ),
        "NOAA_GEFS_WAVE_DIRECT": _source_state(
            "GEFS_WAVE",
            wave.get("readiness", "UNAVAILABLE"),
            "PASS" if wave.get("readiness") == "MEMBER_COMPLETE" else "PARTIAL",
            run_time=wave.get("run_time"),
            scope="LEAD_3H_MEMBER_GATE_ONLY",
            full_matrix_complete=False,
            expected_members=wave.get("summary", {}).get("expected_members"),
            completed_members=wave.get("summary", {}).get("member_count"),
            completion_ratio=wave.get("summary", {}).get("completion_ratio"),
        ),
        "DWD_ICON_DIRECT": _source_state(
            "ICON",
            "POINT_ROUTE_EXTRACTED" if icon.get("status") == "POINT_NUMERIC_READY" else "UNAVAILABLE",
            "PASS" if icon.get("status") == "POINT_NUMERIC_READY" else "PARTIAL",
            raw_status=icon.get("status"),
            field_url=icon.get("field_url"),
        ),
        "COPERNICUS_MARINE_DIRECT": _source_state(
            "COPERNICUS_MARINE",
            "POINT_ROUTE_EXTRACTED" if copernicus.get("status") == "POINT_NUMERIC_READY" else "UNAVAILABLE",
            "PASS" if copernicus.get("status") == "POINT_NUMERIC_READY" else "PARTIAL",
            raw_status=copernicus.get("status"),
            wave_variables=copernicus.get("wave", {}).get("available_variables", []),
            current_variables=copernicus.get("current", {}).get("available_variables", []),
        ),
    }


def _ensemble_payload(gefs: dict) -> dict[str, Any]:
    atmosphere = gefs.get("atmosphere", {})
    wave = gefs.get("wave", {})
    return {
        "gefs_atmosphere_member_gate": {
            "readiness": atmosphere.get("readiness", "UNAVAILABLE"),
            "scope": "LEAD_3H_ONLY",
            "full_matrix_complete": False,
            "run_time": atmosphere.get("run_time"),
            "expected_members": atmosphere.get("summary", {}).get("expected_members"),
            "completed_members": atmosphere.get("summary", {}).get("member_count"),
            "completion_ratio": atmosphere.get("summary", {}).get("completion_ratio"),
            "quantiles": {key: atmosphere.get("summary", {}).get(key) for key in ("q25", "q50", "q75", "q90", "q95") if key in atmosphere.get("summary", {})},
        },
        "gefs_wave_member_gate": {
            "readiness": wave.get("readiness", "UNAVAILABLE"),
            "scope": "LEAD_3H_ONLY",
            "full_matrix_complete": False,
            "run_time": wave.get("run_time"),
            "expected_members": wave.get("summary", {}).get("expected_members"),
            "completed_members": wave.get("summary", {}).get("member_count"),
            "completion_ratio": wave.get("summary", {}).get("completion_ratio"),
            "quantiles": {key: wave.get("summary", {}).get(key) for key in ("q25", "q50", "q75", "q90", "q95") if key in wave.get("summary", {})},
        },
        "p_operational_window": {"status": "NOT_COMPUTABLE", "reason": "FULL_COHERENT_MEMBER_MATRIX_NOT_YET_VERIFIED"},
    }


def build_canonical_snapshot(dashboard: dict, ecmwf: dict, gefs: dict, icon: dict, copernicus: dict) -> dict[str, Any]:
    cutoff = _dt(dashboard["generated_at"])
    generated = datetime.now(timezone.utc)
    points = dashboard.get("points", {})
    missing_points = sorted(REQUIRED_POINTS - set(points))
    if missing_points:
        raise ValueError(f"dashboard missing required production points: {missing_points}")
    if dashboard.get("report_status") != "LIVE":
        raise ValueError(f"dashboard is not LIVE: {dashboard.get('report_status')}")
    if dashboard.get("data_mode") not in {"A", "B", "C"}:
        raise ValueError(f"invalid data_mode: {dashboard.get('data_mode')}")

    git_sha = _git_sha()
    payload: dict[str, Any] = {
        "snapshot_id": "PQWX_CANONICAL_" + cutoff.strftime("%Y%m%d_%H%M%S%z") + "_V1",
        "schema_version": SCHEMA_VERSION,
        "cutoff_time": cutoff.isoformat(),
        "generated_at": generated.isoformat(),
        "data_mode": dashboard["data_mode"],
        "direct_ingest_status": _direct_status(ecmwf, gefs, icon, copernicus),
        "git_commit_sha": git_sha,
        "formula_bundle_version": FORMULA_BUNDLE_VERSION,
        "critical_data_gaps": [],
        "points": points,
        "routes": {},
        "ensemble": _ensemble_payload(gefs),
        "observations": {},
        "official_status": {},
        "drift": {},
        "data_gaps": dashboard.get("gaps", []),
        "unit_policy": {
            "operational_speed": "km/h",
            "raw_units_preserved": True,
            "mps_to_kmh": 3.6,
            "kt_to_kmh": 1.852,
            "wave_height": "m",
            "period": "s",
            "rain": "mm",
            "direction": "degree",
        },
        "audit": {
            "git_commit_sha": git_sha,
            "formula_bundle_version": FORMULA_BUNDLE_VERSION,
            "dashboard_snapshot_id": dashboard.get("snapshot_id"),
            "dashboard_generated_at": dashboard.get("generated_at"),
            "source_cycles": dashboard.get("source_cycles", {}),
            "source_artifacts": {
                "ecmwf": "ecmwf-live-d10-points",
                "gefs": "noaa-live-member-smoke",
                "icon": "icon-live-point-smoke",
                "copernicus": "copernicus-live-phu-quoc-subset",
            },
            "hash_algorithm": "SHA-256",
        },
    }
    return seal_snapshot(payload)


def validate_snapshot(snapshot: dict[str, Any], dashboard: dict | None = None) -> None:
    required = {
        "snapshot_id", "schema_version", "cutoff_time", "generated_at", "payload_hash",
        "data_mode", "direct_ingest_status", "git_commit_sha", "formula_bundle_version",
        "critical_data_gaps", "points", "routes", "ensemble", "data_gaps", "unit_policy", "audit",
    }
    missing = sorted(required - set(snapshot))
    if missing:
        raise ValueError(f"snapshot missing required fields: {missing}")
    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schema_version: {snapshot['schema_version']}")
    if snapshot["data_mode"] not in {"A", "B", "C"}:
        raise ValueError(f"invalid data_mode: {snapshot['data_mode']}")
    if not verify_snapshot(snapshot):
        raise ValueError("payload_hash verification failed")
    missing_points = sorted(REQUIRED_POINTS - set(snapshot.get("points", {})))
    if missing_points:
        raise ValueError(f"snapshot missing production points: {missing_points}")
    if dashboard is not None:
        if snapshot["audit"].get("dashboard_snapshot_id") != dashboard.get("snapshot_id"):
            raise ValueError("snapshot/dashboard lineage mismatch")
        if snapshot["data_mode"] != dashboard.get("data_mode"):
            raise ValueError("snapshot/dashboard data_mode mismatch")


def publish(snapshot: dict[str, Any], root: Path) -> tuple[Path, Path, Path]:
    cutoff = _dt(snapshot["cutoff_time"])
    archive = root / cutoff.strftime("%Y/%m/%d/%H%M%S") / "LAB_SNAPSHOT_V1.json"
    latest = root / "latest.json"
    pointer = root / "latest-pointer.json"
    if archive.exists():
        existing = _load(archive)
        if existing.get("payload_hash") != snapshot.get("payload_hash"):
            raise ValueError(f"immutable archive collision at {archive}")
    else:
        _write(archive, snapshot)
    _write(latest, snapshot)
    _write(pointer, {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot["snapshot_id"],
        "cutoff_time": snapshot["cutoff_time"],
        "generated_at": snapshot["generated_at"],
        "payload_hash": snapshot["payload_hash"],
        "data_mode": snapshot["data_mode"],
        "path": archive.as_posix(),
        "git_commit_sha": snapshot["git_commit_sha"],
        "formula_bundle_version": snapshot["formula_bundle_version"],
    })
    return archive, latest, pointer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--ecmwf", type=Path, required=True)
    parser.add_argument("--gefs", type=Path, required=True)
    parser.add_argument("--icon", type=Path, required=True)
    parser.add_argument("--copernicus", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("weather/snapshots"))
    args = parser.parse_args()

    dashboard = _load(args.dashboard)
    snapshot = build_canonical_snapshot(
        dashboard,
        _load(args.ecmwf),
        _load(args.gefs),
        _load(args.icon),
        _load(args.copernicus),
    )
    validate_snapshot(snapshot, dashboard)
    archive, latest, pointer = publish(snapshot, args.root)
    print(json.dumps({
        "snapshot_id": snapshot["snapshot_id"],
        "data_mode": snapshot["data_mode"],
        "payload_hash": snapshot["payload_hash"],
        "archive": archive.as_posix(),
        "latest": latest.as_posix(),
        "pointer": pointer.as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
