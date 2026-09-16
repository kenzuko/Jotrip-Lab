from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
USER_AGENT = "JoTrip-Lab/1.0 (+public tourism demand research; no booking automation)"


def _fetch_text(url: str, timeout: int = 25) -> tuple[int, str, str]:
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        },
    )
    status = response.status_code
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = " ".join(soup.stripped_strings)
    return status, text, response.url


def _amount(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None


def parse_korean_air(text: str, route: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # Date-specific public cached fares, e.g. ICN–PQC, Sep 11, 2026 ... From KRW 466,900.
    pattern = re.compile(
        rf"{re.escape(route.split('-')[0])}\s*[–-]\s*{re.escape(route.split('-')[1])}[^:]*?:\s*(?:From\s*)?KRW\s*([0-9][0-9,]*)",
        re.I,
    )
    for match in pattern.finditer(text):
        value = _amount(match.group(1))
        if value is not None:
            out.append({"currency": "KRW", "amount": value, "observation_type": "PUBLIC_CACHED_FARE"})
    # Monthly floor fallback when date rows are not rendered in the server response.
    if not out:
        for match in re.finditer(r"(?:Sep|Oct|Nov|Dec|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug)\s+20\d{2}.{0,80}?KRW\s*([0-9][0-9,]*)", text, re.I):
            value = _amount(match.group(1))
            if value is not None:
                out.append({"currency": "KRW", "amount": value, "observation_type": "PUBLIC_MONTH_FLOOR"})
    return out[:100]


def parse_airasia_move(text: str, route: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # Public deal/fare cards. This is deliberately not treated as a fixed fare basket.
    for match in re.finditer(r"(?:AirAsia|Sun\s+PhuQuoc\s+Airways).{0,220}?MYR\s*([0-9][0-9,.]*)", text, re.I):
        value = _amount(match.group(1))
        if value is not None:
            out.append({"currency": "MYR", "amount": value, "observation_type": "PUBLIC_DEAL_FARE"})
    if not out:
        match = re.search(r"(?:starts?\s+at|from)\s+MYR\s*([0-9][0-9,.]*)", text, re.I)
        if match:
            value = _amount(match.group(1))
            if value is not None:
                out.append({"currency": "MYR", "amount": value, "observation_type": "PUBLIC_PAGE_FLOOR"})
    return out[:100]


def collect(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    cfg = read_json(config_path)
    now = datetime.now(VN)
    sources_out: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for source in cfg.get("sources", []):
        row: dict[str, Any] = {
            "source_id": source["source_id"],
            "route": source["route"],
            "market": source["market"],
            "evidence_class": source["evidence_class"],
            "url": source["url"],
            "state": "UNKNOWN",
            "fixed_basket_compatible": False,
        }
        try:
            status, text, final_url = _fetch_text(source["url"])
            parser = source.get("parser")
            parsed = parse_korean_air(text, source["route"]) if parser == "korean_air" else parse_airasia_move(text, source["route"])
            row.update({
                "http_status": status,
                "final_url": final_url,
                "state": "OK" if parsed else "NO_USABLE_FARE",
                "parsed_count": len(parsed),
                "text_length": len(text),
            })
            for item in parsed:
                observations.append({
                    **item,
                    "source_id": source["source_id"],
                    "route": source["route"],
                    "market": source["market"],
                    "airline": source["airline"],
                    "evidence_class": source["evidence_class"],
                    "product_scope": source["product_scope"],
                    "fixed_basket_compatible": False,
                    "observed_at": now.isoformat(),
                })
        except Exception as exc:
            row.update({"state": "FETCH_FAILED", "error": f"{type(exc).__name__}: {exc}"})
        sources_out.append(row)

    working_sources = sum(1 for item in sources_out if item.get("state") == "OK")
    coverage = working_sources / len(sources_out) if sources_out else 0.0
    latest = {
        "schema_version": "airfare-public-fallback-1.0",
        "mode": "PUBLIC_FARE_FALLBACK",
        "eligible_for_airfare_pressure": False,
        "fixed_basket_compatible": False,
        "observed_at_vn": now.isoformat(),
        "source_coverage": round(coverage, 4),
        "sources": sources_out,
        "observations": observations,
        "interpretation_rule": "Public fare/deal pages are fallback evidence only. They never create Airfare Pressure or fixed-basket trend.",
    }
    state = "PARTIAL_READY" if observations else "DEGRADED"
    health = {
        "module": "Airfare Public Fallback",
        "state": state,
        "collector_completed": True,
        "parser_passed": bool(observations),
        "normalization_passed": bool(observations),
        "qa_passed": bool(observations),
        "commit_succeeded": None,
        "eligible_for_airfare_pressure": False,
        "source_coverage": round(coverage, 4),
        "last_successful_run": now.isoformat() if observations else None,
        "root_cause": None if observations else "NGUYÊN NHÂN CHƯA XÁC ĐỊNH - nguồn công khai không trả giá parse được",
    }
    manifest = {
        "schema_version": "1.0",
        "collector_version": "airfare-public-fallback-0.1.0",
        "source_config_version": cfg.get("schema_version"),
        "paid_services_used": False,
        "writes_production_data": False,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out / "latest.json", latest)
    write_json_atomic(out / "health.json", health)
    write_json_atomic(out / "manifest.json", manifest)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tourism_v2/airfare-sources.v1.json")
    parser.add_argument("--output", default="out/airfare_fallback")
    args = parser.parse_args()
    payload = collect(args.config, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
