"""Stable production contract for Weather V2 canonical data consumers."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather.processing.snapshot import verify_snapshot

CONTRACT_VERSION = "weather-production-contract-1.0"
PRODUCTION_REFERENCE = "weather.openphuquoc.com"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def infer_report_cycle(cutoff_time: str) -> str:
    local = datetime.fromisoformat(cutoff_time.replace("Z", "+00:00"))
    return "0600" if local.hour < 12 else "1800"


def build_manifest(snapshot: dict[str, Any], pointer: dict[str, Any]) -> dict[str, Any]:
    if not verify_snapshot(snapshot):
        raise ValueError("snapshot payload hash verification failed")
    for field in ("snapshot_id", "payload_hash", "cutoff_time", "schema_version"):
        if pointer.get(field) != snapshot.get(field):
            raise ValueError(f"pointer/snapshot mismatch: {field}")
    archive_path = pointer["path"]
    mandatory = ["duong_dong", "an_thoi", "ganh_dau"]
    authority = snapshot.get("point_authority", {})
    verified = sorted(authority)
    comparison = [point_id for point_id in verified if point_id not in mandatory]
    return {
        "contract_version": CONTRACT_VERSION,
        "production_reference": PRODUCTION_REFERENCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_cycle": infer_report_cycle(snapshot["cutoff_time"]),
        "snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "schema_version": snapshot["schema_version"],
            "cutoff_time": snapshot["cutoff_time"],
            "generated_at": snapshot["generated_at"],
            "payload_hash": snapshot["payload_hash"],
            "data_mode": snapshot["data_mode"],
            "formula_bundle_version": snapshot["formula_bundle_version"],
            "git_commit_sha": snapshot["git_commit_sha"],
            "latest_path": "weather/snapshots/latest.json",
            "archive_path": archive_path,
            "latest_url": "/weather/snapshots/latest.json",
            "archive_url": "/" + archive_path,
        },
        "source_cycles": snapshot.get("audit", {}).get("source_cycles", {}),
        "required_production_points": mandatory,
        "verified_points": verified,
        "comparison_points": comparison,
        "point_authority": authority,
        "analysis_status": snapshot.get("analysis_status", {}),
    }


def freeze_report_input(snapshot: dict[str, Any], *, root: Path, cycle: str | None = None) -> Path:
    if not verify_snapshot(snapshot):
        raise ValueError("snapshot payload hash verification failed")
    cutoff = datetime.fromisoformat(snapshot["cutoff_time"].replace("Z", "+00:00"))
    selected_cycle = cycle or infer_report_cycle(snapshot["cutoff_time"])
    if selected_cycle not in {"0600", "1800"}:
        raise ValueError("cycle must be 0600 or 1800")
    target = root / cutoff.strftime("%Y/%m/%d") / selected_cycle / "LAB_SNAPSHOT_V1.json"
    if target.exists():
        existing = _load(target)
        if existing.get("payload_hash") != snapshot.get("payload_hash"):
            raise ValueError(f"immutable report input collision at {target}")
        return target
    _write(target, snapshot)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("weather/snapshots/latest.json"))
    parser.add_argument("--pointer", type=Path, default=Path("weather/snapshots/latest-pointer.json"))
    parser.add_argument("--output", type=Path, default=Path("weather/production-manifest.json"))
    parser.add_argument("--freeze-root", type=Path)
    parser.add_argument("--cycle", choices=["0600", "1800"])
    args = parser.parse_args()

    snapshot = _load(args.snapshot)
    pointer = _load(args.pointer)
    manifest = build_manifest(snapshot, pointer)
    _write(args.output, manifest)

    frozen = None
    if args.freeze_root:
        frozen = freeze_report_input(snapshot, root=args.freeze_root, cycle=args.cycle)

    print(json.dumps({
        "contract_version": manifest["contract_version"],
        "snapshot_id": snapshot["snapshot_id"],
        "manifest": args.output.as_posix(),
        "frozen_report_input": None if frozen is None else frozen.as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
