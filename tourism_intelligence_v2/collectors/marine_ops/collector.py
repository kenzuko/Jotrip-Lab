from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.contracts import build_health, iso_vn, write_bundle
from tourism_intelligence_v2.storage import write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
PORT_CLEARANCE_URL = "https://hanghai.moc.gov.vn/giay-phep-roi-cang"
THANH_THOI_URL = "https://thanhthoi.vn/"
FAST_PATTERNS = ("SUPERDONG", "PHU QUOC EXPRESS", "PHÚ QUỐC EXPRESS")
FERRY_PATTERNS = ("THRIVING", "BINH AN", "BÌNH AN")
KGG_PORT_PATTERNS = ("KGIANG", "RACH GIA", "RẠCH GIÁ", "HA TIEN", "HÀ TIÊN", "BAI VONG", "BÃI VÒNG", "THACH THOI", "THẠNH THỚI")
DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")


def _norm(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def classify_vessel(name: str) -> str | None:
    upper = _norm(name).upper()
    if any(pattern in upper for pattern in FAST_PATTERNS):
        return "fast_boat"
    if any(pattern in upper for pattern in FERRY_PATTERNS):
        return "ferry"
    return None


def parse_port_clearance_html(html: str, target_date: str) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for row in soup.find_all("tr"):
        cells = [_norm(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if len(cells) < 7:
            continue
        match = next((DATE_RE.search(cell) for cell in cells if DATE_RE.search(cell)), None)
        if not match or match.group(1) != target_date:
            continue
        permit = cells[1] if len(cells) > 1 else ""
        ship = cells[2] if len(cells) > 2 else ""
        imo = cells[3] if len(cells) > 3 else ""
        call_sign = cells[4] if len(cells) > 4 else ""
        issued = next((cell for cell in cells if DATE_RE.search(cell)), "")
        port = cells[6] if len(cells) > 6 else ""
        if "/KGG" not in permit.upper() and not any(token in port.upper() for token in KGG_PORT_PATTERNS):
            continue
        category = classify_vessel(ship)
        if not category:
            continue
        out.append({
            "category": category,
            "source": "PORT_CLEARANCE_KGG",
            "source_tier": "PERMIT_PORT",
            "evidence_class": "DIRECT",
            "permit_number": permit,
            "vessel_name": ship,
            "imo": imo,
            "call_sign": call_sign,
            "issued_at_text": issued,
            "departure_port": port,
        })
    return out


def parse_thanh_thoi_html(html: str, target_date: str) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = _norm(soup.get_text(" ", strip=True))
    d, m, y = target_date.split("/")
    if f"Ngày: {int(d)}/{int(m)}/{y}" not in text and f"Ngày: {d}/{m}/{y}" not in text:
        return []
    if "Đã xuất bến" not in text:
        return []
    vessels = sorted(set(re.findall(r"Thriving\s+\d+", text, flags=re.I)))
    return [{
        "category": "ferry",
        "source": "THANH_THOI_OPERATOR",
        "source_tier": "OPERATOR",
        "evidence_class": "DIRECT",
        "vessel_name": vessel,
        "status": "Đã xuất bến",
    } for vessel in vessels]


def _fetch(url: str, timeout: int = 25) -> str:
    import requests

    response = requests.get(url, timeout=timeout, headers={"User-Agent": "JoTrip-Lab/1.0 (+public tourism operations research)"})
    response.raise_for_status()
    return response.text


def _category_state(category: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [item for item in evidence if item.get("category") == category]
    if rows:
        source_tiers = sorted(set(item.get("source_tier", "UNKNOWN") for item in rows))
        return {
            "state": "DIRECT_CONFIRMED",
            "evidence_count": len(rows),
            "source_tiers": source_tiers,
            "confidence_cap": 100,
            "evidence": rows,
        }
    if category == "cano":
        return {"state": "FIELD_REQUIRED", "evidence_count": 0, "source_tiers": [], "confidence_cap": 59, "evidence": []}
    return {"state": "UNKNOWN", "evidence_count": 0, "source_tiers": [], "confidence_cap": 59, "evidence": []}


def collect(target_date: str | None = None, output_dir: str | Path = "out/marine_ops") -> dict[str, Any]:
    now = datetime.now(VN)
    target = target_date or now.strftime("%d/%m/%Y")
    errors: list[dict[str, str]] = []
    evidence: list[dict[str, Any]] = []
    permit_ok = operator_ok = False

    try:
        html = _fetch(PORT_CLEARANCE_URL)
        evidence.extend(parse_port_clearance_html(html, target))
        permit_ok = True
    except Exception as exc:  # operational telemetry, not a market conclusion
        errors.append({"source": "PORT_CLEARANCE_KGG", "error": f"{type(exc).__name__}: {exc}"})

    try:
        html = _fetch(THANH_THOI_URL)
        evidence.extend(parse_thanh_thoi_html(html, target))
        operator_ok = True
    except Exception as exc:
        errors.append({"source": "THANH_THOI_OPERATOR", "error": f"{type(exc).__name__}: {exc}"})

    latest = {
        "schema_version": "marine-ops-1.0",
        "source_date": target,
        "collected_at_vn": iso_vn(now),
        "market_condition_not_data_system_condition": True,
        "categories": {
            "fast_boat": _category_state("fast_boat", evidence),
            "ferry": _category_state("ferry", evidence),
            "cano": _category_state("cano", evidence),
        },
        "errors": errors,
        "rules": {
            "no_cross_category_inference": True,
            "permit_or_departure_slip_is_direct": True,
            "one_normal_fast_boat_can_confirm_category_absent_specific_exception": True,
            "one_normal_ferry_can_confirm_category_absent_specific_exception": True,
            "cano_independent": True,
        },
    }
    parser_passed = permit_ok or operator_ok
    state = "REPORT_READY" if parser_passed else "FAILED"
    health = build_health(
        "Marine Operations",
        state,
        scheduler_triggered=True,
        collector_completed=parser_passed,
        parser_passed=parser_passed,
        normalization_passed=parser_passed,
        qa_passed=parser_passed,
        last_successful_run=iso_vn(now) if parser_passed else None,
        fallback_used=not permit_ok and operator_ok,
        failed_stage=None if parser_passed else "COLLECT",
    )
    health["sources"] = {
        "PORT_CLEARANCE_KGG": "OK" if permit_ok else "FAILED",
        "THANH_THOI_OPERATOR": "OK" if operator_ok else "FAILED",
    }
    manifest = {
        "schema_version": "1.0",
        "module_schema_version": "marine-ops-1.0",
        "collector_version": "marine-ops-web-0.1.1",
        "normalization_version": "marine-ops-rules-0.1.0",
        "source_registry_version": "1.0",
        "paid_services_used": False,
    }
    write_bundle(output_dir, latest, health, manifest)
    stamp = now.strftime("%H%M")
    date_dir = now.strftime("%Y-%m-%d") if not target_date else datetime.strptime(target, "%d/%m/%Y").strftime("%Y-%m-%d")
    write_json_atomic(Path(output_dir) / date_dir / f"{stamp}.json", latest)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="DD/MM/YYYY; defaults to current Asia/Ho_Chi_Minh date")
    parser.add_argument("--output", default="out/marine_ops")
    args = parser.parse_args()
    result = collect(args.date, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
