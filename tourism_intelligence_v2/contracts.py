from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .storage import write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
HEALTH_STATES = {
    "OK", "REPORT_READY", "DEGRADED", "STALE", "FAILED", "NOT_YET_ROLLED_OVER",
    "BLOCKED", "PARSE_ERROR", "QA_FAILED", "COMMIT_FAILED", "UNKNOWN", "NOT_AUTOMATED",
}


def now_vn() -> datetime:
    return datetime.now(timezone.utc).astimezone(VN)


def iso_vn(dt: datetime | None = None) -> str:
    value = dt or now_vn()
    if value.tzinfo is None:
        value = value.replace(tzinfo=VN)
    return value.astimezone(VN).isoformat()


def build_health(
    module: str,
    state: str,
    *,
    scheduler_triggered: bool = False,
    collector_completed: bool = False,
    parser_passed: bool = False,
    normalization_passed: bool = False,
    qa_passed: bool = False,
    commit_succeeded: bool | None = None,
    retry_count: int = 0,
    fallback_used: bool = False,
    last_successful_run: str | None = None,
    failed_stage: str | None = None,
    root_cause: str | None = None,
) -> dict[str, Any]:
    if state not in HEALTH_STATES:
        raise ValueError(f"Unsupported health state: {state}")
    return {
        "module": module,
        "state": state,
        "scheduler_triggered": scheduler_triggered,
        "job_started": True,
        "collector_completed": collector_completed,
        "parser_passed": parser_passed,
        "normalization_passed": normalization_passed,
        "qa_passed": qa_passed,
        "commit_succeeded": commit_succeeded,
        "collected_at_vn": iso_vn(),
        "retry_count": retry_count,
        "last_successful_run": last_successful_run,
        "fallback_used": fallback_used,
        "failed_stage": failed_stage,
        "root_cause": root_cause or (None if state in {"OK", "REPORT_READY"} else "NGUYÊN NHÂN CHƯA XÁC ĐỊNH"),
    }


def write_bundle(root: str | Path, latest: dict, health: dict, manifest: dict) -> None:
    base = Path(root)
    write_json_atomic(base / "latest.json", latest)
    write_json_atomic(base / "health.json", health)
    write_json_atomic(base / "manifest.json", manifest)
