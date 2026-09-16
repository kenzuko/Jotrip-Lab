from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.collectors.forward_airlift.processor import summarize
from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = "JoTrip-Lab/1.0 (+public tourism supply research)"


def _fetch_text(url: str, timeout: int = 25) -> tuple[int, str, str]:
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,vi;q=0.8"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return response.status_code, " ".join(soup.stripped_strings), response.url


def _contains_all(text: str, markers: list[str]) -> bool:
    lower = text.casefold()
    return all(marker.casefold() in lower for marker in markers)


def collect(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    cfg = read_json(config_path)
    now = datetime.now(VN)
    evidence: list[dict[str, Any]] = []
    source_states: list[dict[str, Any]] = []

    for source in cfg.get("sources", []):
        state: dict[str, Any] = {
            "source_id": source["source_id"],
            "route": source["route"],
            "market": source["market"],
            "evidence_class": source["evidence_class"],
            "state": "UNKNOWN",
            "url": source["url"],
        }
        try:
            status, text, final_url = _fetch_text(source["url"])
            required_ok = _contains_all(text, source.get("required_markers", []))
            future_ok = any(marker.casefold() in text.casefold() for marker in source.get("future_markers", []))
            verified = required_ok and future_ok
            state.update({
                "http_status": status,
                "final_url": final_url,
                "required_markers_passed": required_ok,
                "future_markers_passed": future_ok,
                "text_length": len(text),
                "state": "VERIFIED" if verified else "UNVERIFIED",
            })
            if verified:
                evidence.append({
                    "route": source["route"],
                    "airline": source["airline"],
                    "service_type": source["service_type"],
                    "start_date": None,
                    "end_date": None,
                    "frequency_weekly": source.get("frequency_weekly"),
                    "market": source["market"],
                    "source": source["url"],
                    "source_id": source["source_id"],
                    "evidence_class": source["evidence_class"],
                    "observed_at": now.isoformat(),
                    "signal": "FORWARD_BOOKABLE_OR_PUBLISHED",
                    "passenger_demand_inference_allowed": False,
                })
        except Exception as exc:
            state.update({"state": "FETCH_FAILED", "error": f"{type(exc).__name__}: {exc}"})
        source_states.append(state)

    direct = [item for item in evidence if item.get("evidence_class") == "DIRECT"]
    summary = summarize(evidence)
    configured_markets = set(cfg.get("required_markets", [])) or {"Vietnam", "Korea", "Russia_CIS", "Taiwan_HK_China", "SEA", "Western"}
    covered_markets = {item["market"] for item in evidence}
    direct_markets = {item["market"] for item in direct}
    coverage = len(covered_markets) / len(configured_markets) if configured_markets else 0.0
    direct_coverage = len(direct_markets) / len(configured_markets) if configured_markets else 0.0
    gate_cfg = cfg.get("score_gate", {})
    min_total = float(gate_cfg.get("minimum_market_coverage", 0.65))
    min_direct = float(gate_cfg.get("minimum_direct_market_coverage", 0.50))
    score_gate_passed = coverage >= min_total and direct_coverage >= min_direct

    latest = {
        "schema_version": "forward-airlift-evidence-1.1",
        "observed_at_vn": now.isoformat(),
        "state": "REPORT_READY" if score_gate_passed else ("PARTIAL_READY" if evidence else "DEGRADED"),
        "market_coverage": round(coverage, 4),
        "direct_market_coverage": round(direct_coverage, 4),
        "score_gate": {"minimum_market_coverage": min_total, "minimum_direct_market_coverage": min_direct},
        "score_gate_passed": score_gate_passed,
        "forward_airlift_signal": summary.get("forward_airlift_signal") if score_gate_passed else None,
        "markets": summary.get("markets", {}),
        "evidence": evidence,
        "sources": source_states,
        "interpretation_rule": "Bookable/published route evidence is supply evidence only; never infer passenger demand or load factor. Proxy coverage cannot unlock a composite score without direct-market coverage.",
    }
    health = {
        "module": "Forward Airlift",
        "state": latest["state"],
        "collector_completed": True,
        "parser_passed": bool(evidence),
        "normalization_passed": bool(evidence),
        "qa_passed": bool(evidence),
        "commit_succeeded": None,
        "market_coverage": round(coverage, 4),
        "direct_market_coverage": round(direct_coverage, 4),
        "direct_source_count": len(direct),
        "score_gate_passed": score_gate_passed,
        "last_successful_run": now.isoformat() if evidence else None,
        "root_cause": None if evidence else "NGUYÊN NHÂN CHƯA XÁC ĐỊNH - chưa xác minh được nguồn forward công khai",
    }
    manifest = {
        "schema_version": "1.0",
        "collector_version": "forward-airlift-evidence-0.2.0",
        "source_config_version": cfg.get("schema_version"),
        "paid_services_used": False,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out / "latest.json", latest)
    write_json_atomic(out / "health.json", health)
    write_json_atomic(out / "manifest.json", manifest)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tourism_v2/forward-airlift-sources.v1.json")
    parser.add_argument("--output", default="out/forward_airlift")
    args = parser.parse_args()
    payload = collect(args.config, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
