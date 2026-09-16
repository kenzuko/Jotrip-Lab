from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.registry import freshness, load_registry
from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
CORE_MODULES = {"weather_marine", "aviation", "marine_ops", "hotel_forward", "airfare"}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=VN)
    except ValueError:
        return None


def _source_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["source_id"]: item for item in registry.get("sources", [])}


def _health_source(
    source_id: str,
    module: str,
    observed_at: str | None,
    state: str,
    registry: dict[str, dict[str, Any]],
    now: datetime,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = registry[source_id]
    parsed = _parse_time(observed_at)
    age = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60.0 if parsed else None
    fresh = freshness(age, cfg.get("ttl_minutes")) if age is not None else {
        "score": None,
        "state": "UNKNOWN_AGE",
        "age_minutes": None,
        "ttl_minutes": cfg.get("ttl_minutes"),
    }
    payload = {
        "source_id": source_id,
        "module": module,
        "evidence_class": cfg.get("evidence_class"),
        "criticality": cfg.get("criticality"),
        "state": state,
        "observed_at": observed_at,
        "freshness": fresh,
        "paid": bool(cfg.get("paid")),
    }
    if extra:
        payload.update(extra)
    return payload


def build(
    source_registry_path: str | Path,
    module_registry_path: str | Path,
    weather_snapshot_path: str | Path | None,
    sun_health_path: str | Path | None,
    marine_health_path: str | Path | None,
    airfare_fallback_health_path: str | Path | None = None,
    forward_airlift_health_path: str | Path | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).astimezone(VN)
    source_registry = load_registry(source_registry_path)
    registry = _source_index(source_registry)
    modules_cfg = read_json(module_registry_path)
    module_state_map = {item["module_id"]: item for item in modules_cfg.get("modules", [])}
    sources: list[dict[str, Any]] = []
    modules: dict[str, dict[str, Any]] = {}

    # Weather canonical snapshot: read-only consumer.
    if weather_snapshot_path and Path(weather_snapshot_path).exists():
        wx = read_json(weather_snapshot_path)
        wx_time = wx.get("cutoff_time") or wx.get("generated_at")
        wx_direct = wx.get("direct_ingest_status", {})
        direct_pass = sum(1 for item in wx_direct.values() if item.get("qc") == "PASS")
        sources.append(_health_source(
            "WEATHER_LAB_CANONICAL",
            "weather_marine",
            wx_time,
            "OK",
            registry,
            now,
            {
                "data_mode": wx.get("data_mode"),
                "direct_ingest_pass_count": direct_pass,
                "critical_data_gaps": wx.get("critical_data_gaps", []),
            },
        ))
        modules["weather_marine"] = {
            "state": "OK" if not wx.get("critical_data_gaps") else "DEGRADED",
            "direct_evidence": True,
            "qa_passed": True,
            "observed_at": wx_time,
        }
    else:
        modules["weather_marine"] = {"state": "UNKNOWN", "direct_evidence": False, "qa_passed": False}

    # Sun Airport health: read-only consumer.
    if sun_health_path and Path(sun_health_path).exists():
        sun = read_json(sun_health_path)
        sun_time = sun.get("collected_at_vn") or sun.get("last_successful_run")
        sun_state = sun.get("state", "UNKNOWN")
        sources.append(_health_source(
            "SUN_AIRPORT_D0",
            "aviation",
            sun_time,
            sun_state,
            registry,
            now,
            {"source_date": sun.get("source_date")},
        ))
        modules["aviation"] = {
            "state": "OK" if sun_state == "REPORT_READY" and sun.get("qa_passed") else sun_state,
            "direct_evidence": sun_state == "REPORT_READY",
            "qa_passed": bool(sun.get("qa_passed")),
            "observed_at": sun_time,
        }
    else:
        modules["aviation"] = {"state": "UNKNOWN", "direct_evidence": False, "qa_passed": False}

    # Marine Ops health: one module can expose multiple direct sources.
    if marine_health_path and Path(marine_health_path).exists():
        marine = read_json(marine_health_path)
        marine_time = marine.get("collected_at_vn") or marine.get("last_successful_run")
        source_states = marine.get("sources", {})
        sources.append(_health_source(
            "MARINE_PERMIT_KGG",
            "marine_ops",
            marine_time,
            source_states.get("PORT_CLEARANCE_KGG", "UNKNOWN"),
            registry,
            now,
        ))
        sources.append(_health_source(
            "THANH_THOI_OPERATOR",
            "marine_ops",
            marine_time,
            source_states.get("THANH_THOI_OPERATOR", "UNKNOWN"),
            registry,
            now,
        ))
        ready = marine.get("state") == "REPORT_READY" and marine.get("qa_passed")
        modules["marine_ops"] = {
            "state": "OK" if ready else marine.get("state", "UNKNOWN"),
            "direct_evidence": ready,
            "qa_passed": bool(marine.get("qa_passed")),
            "observed_at": marine_time,
        }
    else:
        modules["marine_ops"] = {"state": "UNKNOWN", "direct_evidence": False, "qa_passed": False}

    # Public airfare fallback is useful evidence but NEVER satisfies the fixed-basket core gate.
    if airfare_fallback_health_path and Path(airfare_fallback_health_path).exists():
        fare = read_json(airfare_fallback_health_path)
        fare_time = fare.get("last_successful_run") or fare.get("collected_at_vn")
        fare_state = fare.get("state", "UNKNOWN")
        sources.append(_health_source(
            "AIRFARE_PUBLIC_FALLBACK",
            "airfare",
            fare_time,
            fare_state,
            registry,
            now,
            {
                "source_coverage": fare.get("source_coverage"),
                "fixed_basket_compatible": False,
                "airfare_pressure_eligible": False,
            },
        ))
        fallback_ready = fare_state == "PARTIAL_READY" and bool(fare.get("qa_passed"))
        modules["airfare"] = {
            "state": "FALLBACK_READY" if fallback_ready else fare_state,
            "automation_state": module_state_map.get("airfare", {}).get("automation_state", "FALLBACK_LIVE"),
            "direct_evidence": False,
            "qa_passed": bool(fare.get("qa_passed")),
            "fixed_basket_ready": False,
            "airfare_pressure_eligible": False,
            "source_coverage": fare.get("source_coverage"),
            "observed_at": fare_time,
        }

    # Forward Airlift is non-core but can surface partial supply evidence without unlocking a score.
    if forward_airlift_health_path and Path(forward_airlift_health_path).exists():
        airlift = read_json(forward_airlift_health_path)
        airlift_time = airlift.get("last_successful_run") or airlift.get("collected_at_vn")
        airlift_state = airlift.get("state", "UNKNOWN")
        sources.append(_health_source(
            "FORWARD_AIRLIFT_EVIDENCE",
            "forward_airlift",
            airlift_time,
            airlift_state,
            registry,
            now,
            {
                "market_coverage": airlift.get("market_coverage"),
                "direct_market_coverage": airlift.get("direct_market_coverage"),
                "score_gate_passed": bool(airlift.get("score_gate_passed")),
            },
        ))
        modules["forward_airlift"] = {
            "state": airlift_state,
            "automation_state": module_state_map.get("forward_airlift", {}).get("automation_state", "PARTIAL_LIVE"),
            "direct_evidence": bool(airlift.get("direct_source_count", 0)),
            "qa_passed": bool(airlift.get("qa_passed")),
            "market_coverage": airlift.get("market_coverage"),
            "direct_market_coverage": airlift.get("direct_market_coverage"),
            "forward_airlift_signal_eligible": bool(airlift.get("score_gate_passed")),
            "observed_at": airlift_time,
        }

    # Remaining declared modules use their explicit automation states. These are data-system states,
    # not market conclusions.
    aliases = {
        "hotel_forward": "hotel_forward",
        "airfare": "airfare",
        "forward_airlift": "forward_airlift",
        "social_intent": "social_intent",
        "jotrip_internal": "jotrip_internal",
    }
    for module_id, target in aliases.items():
        cfg = module_state_map.get(module_id, {})
        automation = cfg.get("automation_state", "UNKNOWN")
        if target in modules:
            continue
        if automation in {"PROCESSOR_ONLY", "SCHEMA_ONLY"}:
            state = "NOT_AUTOMATED"
        elif automation == "FALLBACK_LIVE":
            state = "FALLBACK_UNAVAILABLE"
        elif automation == "PARTIAL_LIVE":
            state = "NO_CURRENT_SNAPSHOT"
        else:
            state = automation
        modules[target] = {
            "state": state,
            "automation_state": automation,
            "direct_evidence": False,
            "qa_passed": False,
        }
        if target == "airfare":
            modules[target]["fixed_basket_ready"] = False
            modules[target]["airfare_pressure_eligible"] = False
        if target == "forward_airlift":
            modules[target]["forward_airlift_signal_eligible"] = False

    fresh_scores = [item["freshness"]["score"] for item in sources if item["freshness"].get("score") is not None]
    source_freshness_score = round(100 * sum(fresh_scores) / len(fresh_scores), 1) if fresh_scores else None
    stale_sources = [item["source_id"] for item in sources if item["freshness"].get("state") == "STALE"]
    failed_sources = [
        item["source_id"]
        for item in sources
        if item.get("state") in {"FAILED", "BLOCKED", "PARSE_ERROR", "QA_FAILED", "COMMIT_FAILED", "DEGRADED"}
    ]

    tracked = list(CORE_MODULES)
    ready_core = [name for name in tracked if modules.get(name, {}).get("state") == "OK"]
    completeness = round(100 * len(ready_core) / len(tracked), 1) if tracked else None
    direct_core = [name for name in tracked if modules.get(name, {}).get("direct_evidence")]
    direct_coverage = round(100 * len(direct_core) / len(tracked), 1) if tracked else None

    missing_core = [name for name in tracked if modules.get(name, {}).get("state") != "OK"]
    run_status = "FULL"
    if missing_core:
        run_status = "DEGRADED"
    if len(ready_core) < 2:
        run_status = "PARTIAL"

    return {
        "schema_version": "tourism-readiness-1.1",
        "generated_at_vn": now.isoformat(),
        "market_condition_not_data_system_condition": True,
        "overall_completeness_percent": completeness,
        "source_freshness_score": source_freshness_score,
        "direct_evidence_coverage_percent": direct_coverage,
        "pipeline_health_score": None,
        "pipeline_health_note": "Không xuất điểm tổng cho đến khi dữ liệu thực thi/QA/dự phòng phủ đủ các module lõi.",
        "failed_sources": failed_sources,
        "stale_sources": stale_sources,
        "unresolved_conflicts": [],
        "run_status": run_status,
        "missing_core_modules": missing_core,
        "modules": modules,
        "sources": sources,
        "language_policy": "Ưu tiên tiếng Việt; chỉ giữ mã kỹ thuật, tên riêng, URL và trích dẫn nguyên văn khi cần.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-registry", default="config/tourism_v2/source-registry.v1.json")
    parser.add_argument("--module-registry", default="config/tourism_v2/module-registry.v1.json")
    parser.add_argument("--weather", default=None)
    parser.add_argument("--sun", default=None)
    parser.add_argument("--marine", default=None)
    parser.add_argument("--airfare-fallback", default=None)
    parser.add_argument("--forward-airlift", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = build(
        args.source_registry,
        args.module_registry,
        args.weather,
        args.sun,
        args.marine,
        args.airfare_fallback,
        args.forward_airlift,
    )
    write_json_atomic(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
