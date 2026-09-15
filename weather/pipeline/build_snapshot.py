"""Build an immutable Lab Snapshot from normalized evidence or a test fixture."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from weather.collectors.catalog import default_manifests
from weather.collectors.probe import probe_sources
from weather.processing.snapshot import seal_snapshot
from weather.processing.readiness import derive_data_mode


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.getenv("GITHUB_SHA", "UNKNOWN")


def determine_mode(health: dict, evidence: dict) -> str:
    return derive_data_mode(health, evidence)


def build_snapshot(evidence: dict, cutoff: datetime, health: dict | None = None) -> dict:
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    now = datetime.now(timezone.utc)
    health = health if health is not None else probe_sources()
    data_mode = determine_mode(health, evidence)
    snapshot_id = "PQWX_" + cutoff.astimezone(timezone.utc).strftime("%Y%m%d_%H%MZ_V1")
    gaps = list(evidence.get("data_gaps", []))
    for source, state in health.items():
        if state.get("readiness") not in {"POINT_ROUTE_EXTRACTED", "MEMBER_COMPLETE", "DECISION_ELIGIBLE"}:
            gaps.append({"source": source, "status": state.get("status"), "impact": "SOURCE_NOT_DIRECT_INGEST_ELIGIBLE"})
    payload = {
        "snapshot_id": snapshot_id, "schema_version": "1.0", "cutoff_time": cutoff.isoformat(),
        "generated_at": now.isoformat(), "data_mode": data_mode, "direct_ingest_status": health,
        "points": evidence.get("points", {}), "routes": evidence.get("routes", {}),
        "ensemble": evidence.get("ensemble", {}), "observations": evidence.get("observations", {}),
        "official_status": evidence.get("official_status", {}), "drift": evidence.get("drift", {}),
        "data_gaps": gaps,
        "audit": {"git_commit_sha": git_sha(), "formula_bundle_version": "weather-lab-0.1.0", "hash_algorithm": "SHA-256", "request_manifests": default_manifests(now)},
    }
    return seal_snapshot(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--offline", action="store_true", help="Skip network probes and declare source health explicitly degraded")
    args = parser.parse_args()
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
    health = ({key: {"status": "NOT_TESTED_OFFLINE"} for key in ("ECMWF_DIRECT", "NOAA_GEFS_DIRECT", "NOAA_GEFS_WAVE_DIRECT", "DWD_ICON_DIRECT", "COPERNICUS_MARINE_DIRECT")} if args.offline else None)
    snapshot = build_snapshot(evidence, cutoff, health)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(snapshot["snapshot_id"], snapshot["data_mode"], snapshot["payload_hash"])


if __name__ == "__main__":
    main()
