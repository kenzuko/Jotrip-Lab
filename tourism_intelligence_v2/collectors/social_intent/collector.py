from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = "JoTrip-Lab/1.0 public tourism research contact: github.com/kenzuko/Jotrip-Lab"


def _fetch_reddit(url: str, timeout: int = 25) -> tuple[int, dict[str, Any], str]:
    import requests

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    response.raise_for_status()
    return response.status_code, response.json(), response.url


def _extract_posts(payload: dict[str, Any], source: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
    for child in children:
        data = child.get("data", {}) if isinstance(child, dict) else {}
        title = str(data.get("title") or "").strip()
        selftext = str(data.get("selftext") or "").strip()
        permalink = data.get("permalink")
        if not title and not selftext:
            continue
        posts.append({
            "source_id": source["source_id"],
            "platform": source["platform"],
            "market": source["market"],
            "language": source["language"],
            "query": source["query"],
            "evidence_class": source["evidence_class"],
            "post_id": data.get("id"),
            "title": title,
            "text_excerpt": selftext[:1000],
            "subreddit": data.get("subreddit"),
            "score": data.get("score"),
            "num_comments": data.get("num_comments"),
            "created_utc": data.get("created_utc"),
            "url": f"https://www.reddit.com{permalink}" if permalink else data.get("url"),
            "observed_at": observed_at,
            "theme": None,
            "decision_stage": None,
            "booking_demand_inference_allowed": False,
        })
    return posts


def collect(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    cfg = read_json(config_path)
    now = datetime.now(VN)
    observed_at = now.isoformat()
    evidence: list[dict[str, Any]] = []
    source_states: list[dict[str, Any]] = []

    for source in cfg.get("sources", []):
        state: dict[str, Any] = {
            "source_id": source["source_id"],
            "platform": source["platform"],
            "market": source["market"],
            "language": source["language"],
            "state": "UNKNOWN",
        }
        try:
            status, payload, final_url = _fetch_reddit(source["url"])
            posts = _extract_posts(payload, source, observed_at)
            evidence.extend(posts)
            state.update({
                "http_status": status,
                "final_url": final_url,
                "state": "OK" if posts else "NO_MATCHING_POSTS",
                "post_count": len(posts),
            })
        except Exception as exc:
            state.update({"state": "FETCH_FAILED", "post_count": 0, "error": f"{type(exc).__name__}: {exc}"})
        source_states.append(state)

    configured_markets = {item.get("market") for item in cfg.get("sources", []) if item.get("market")}
    working_markets = {item.get("market") for item in source_states if item.get("state") == "OK"}
    coverage = len(working_markets) / len(configured_markets) if configured_markets else 0.0

    latest = {
        "schema_version": "social-intent-evidence-1.0",
        "observed_at_vn": observed_at,
        "state": "PARTIAL_READY" if evidence else "DEGRADED",
        "market_coverage": round(coverage, 4),
        "evidence_count": len(evidence),
        "sources": source_states,
        "evidence": evidence,
        "interpretation_rule": "Posts are leading qualitative evidence only. Counts do not equal bookings or destination demand.",
    }
    health = {
        "module": "Social Intent",
        "state": latest["state"],
        "collector_completed": True,
        "parser_passed": bool(evidence),
        "normalization_passed": bool(evidence),
        "qa_passed": bool(evidence),
        "commit_succeeded": None,
        "market_coverage": round(coverage, 4),
        "evidence_count": len(evidence),
        "last_successful_run": observed_at if evidence else None,
        "root_cause": None if evidence else "NGUYÊN NHÂN CHƯA XÁC ĐỊNH - Reddit public endpoint không trả bằng chứng dùng được",
    }
    manifest = {
        "schema_version": "1.0",
        "collector_version": "social-intent-reddit-0.1.0",
        "source_config_version": cfg.get("schema_version"),
        "paid_services_used": False,
        "theme_coding_automated": False,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out / "latest.json", latest)
    write_json_atomic(out / "health.json", health)
    write_json_atomic(out / "manifest.json", manifest)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tourism_v2/social-intent-sources.v1.json")
    parser.add_argument("--output", default="out/social_intent")
    args = parser.parse_args()
    payload = collect(args.config, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
