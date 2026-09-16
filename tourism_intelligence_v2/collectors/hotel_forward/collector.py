from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.contracts import build_health, iso_vn, write_bundle
from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
BOOKING_ORIGIN = "https://www.booking.com"
BLOCK_PATTERNS = (
    "verify you are human",
    "captcha",
    "access denied",
    "unusual traffic",
    "robot",
)
UNAVAILABLE_PATTERNS = (
    "not available on our site for your dates",
    "no availability",
    "sold out",
    "not available for your dates",
    "hết phòng",
    "không còn phòng",
    "không có phòng trống",
)
PRICE_SELECTORS = (
    '[data-testid="price-and-discounted-price"]',
    '.hprt-price-price-standard',
    '.prco-valign-middle-helper',
    '.bui-price-display__value',
)
ROOM_TABLE_SELECTORS = ('#hprt-table', '.hprt-table', '[data-testid="availability-table"]')


def _normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _parse_vnd(text: str) -> list[int]:
    values: list[int] = []
    for match in re.finditer(r"(?:VND|₫)\s*([0-9][0-9.,\s]{3,})", text, flags=re.I):
        digits = re.sub(r"\D", "", match.group(1))
        if not digits:
            continue
        value = int(digits)
        if 100_000 <= value <= 2_000_000_000:
            values.append(value)
    return values


def _build_url(path: str, checkin: date, checkout: date, contract: dict[str, Any]) -> str:
    params = {
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "group_adults": int(contract.get("adults", 2)),
        "group_children": int(contract.get("children", 0)),
        "no_rooms": int(contract.get("rooms", 1)),
        "selected_currency": contract.get("currency", "VND"),
        "lang": "en-us",
    }
    return f"{BOOKING_ORIGIN}{path}?{urlencode(params)}"


def _click_consent(page: Any) -> None:
    candidates = (
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
    )
    for selector in candidates:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=800):
                locator.click(timeout=1500)
                return
        except Exception:
            continue


def _collect_one(page: Any, hotel: dict[str, Any], checkin: date, checkout: date, contract: dict[str, Any], diagnostics_dir: Path) -> dict[str, Any]:
    url = _build_url(hotel["booking_path"], checkin, checkout, contract)
    started = datetime.now(VN)
    observation: dict[str, Any] = {
        "hotel_id": hotel["hotel_id"],
        "hotel_name": hotel["hotel_name"],
        "zone": hotel.get("zone"),
        "segment": hotel.get("segment"),
        "strategic": bool(hotel.get("strategic")),
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "lead_time_days": (checkin - started.date()).days,
        "rooms": contract.get("rooms"),
        "adults": contract.get("adults"),
        "currency_requested": contract.get("currency", "VND"),
        "member_state": contract.get("member_state"),
        "source": "Booking.com",
        "source_url": url,
        "observed_at": iso_vn(started),
        "availability_state": "UNKNOWN",
        "available": None,
        "rate_all_in_vnd": None,
        "rate_observation_method": None,
        "date_context_verified": False,
        "evidence_class": "DIRECT",
    }
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        _click_consent(page)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        body = _normalize_text(page.locator("body").inner_text(timeout=10_000))
        lower = body.lower()
        observation["http_status"] = response.status if response else None
        observation["final_url"] = page.url
        observation["page_title"] = page.title()
        observation["date_context_verified"] = checkin.isoformat() in page.url and checkout.isoformat() in page.url

        if any(pattern in lower for pattern in BLOCK_PATTERNS):
            observation["availability_state"] = "BLOCKED"
            observation["error"] = "Booking page presented anti-bot/access challenge"
        elif not observation["date_context_verified"]:
            observation["availability_state"] = "DATE_CONTEXT_UNVERIFIED"
            observation["error"] = "Requested check-in/check-out were not preserved in final URL"
        else:
            price_texts: list[str] = []
            for selector in PRICE_SELECTORS:
                try:
                    locator = page.locator(selector)
                    count = min(locator.count(), 80)
                    for index in range(count):
                        try:
                            text = _normalize_text(locator.nth(index).inner_text(timeout=800))
                            if text:
                                price_texts.append(text)
                        except Exception:
                            continue
                except Exception:
                    continue
            values: list[int] = []
            for text in price_texts:
                values.extend(_parse_vnd(text))

            room_table_visible = False
            for selector in ROOM_TABLE_SELECTORS:
                try:
                    if page.locator(selector).first.is_visible(timeout=600):
                        room_table_visible = True
                        break
                except Exception:
                    continue

            if values:
                observation["availability_state"] = "AVAILABLE"
                observation["available"] = True
                observation["rate_all_in_vnd"] = min(values)
                observation["rate_observation_method"] = "VISIBLE_BOOKING_PRICE_ELEMENT"
                observation["price_candidates_vnd"] = sorted(set(values))[:20]
            elif any(pattern in lower for pattern in UNAVAILABLE_PATTERNS):
                observation["availability_state"] = "EXPLICITLY_UNAVAILABLE"
                observation["available"] = False
                observation["rate_observation_method"] = "EXPLICIT_UNAVAILABLE_TEXT"
            elif room_table_visible:
                observation["availability_state"] = "ROOM_TABLE_WITHOUT_VND_PRICE"
                observation["rate_observation_method"] = "PARSE_INCOMPLETE"
            else:
                observation["availability_state"] = "UNKNOWN_PARSE"
                observation["rate_observation_method"] = "NO_RELIABLE_AVAILABILITY_SIGNAL"

            observation["breakfast_text_visible"] = "breakfast" in lower
            observation["free_cancellation_text_visible"] = "free cancellation" in lower
            observation["taxes_and_fees_text_visible"] = "taxes and fees" in lower

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", hotel["hotel_id"])
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / f"{safe_name}.txt").write_text(body[:150_000], encoding="utf-8")
        page.screenshot(path=str(diagnostics_dir / f"{safe_name}.png"), full_page=False)
    except Exception as exc:
        observation["availability_state"] = "FETCH_ERROR"
        observation["error"] = f"{type(exc).__name__}: {exc}"
    return observation


def collect(
    config_path: str | Path,
    output_dir: str | Path,
    horizon_days: int,
    hotel_limit: int | None = None,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    config = read_json(config_path)
    contract = config["search_contract"]
    today = datetime.now(VN).date()
    checkin = today + timedelta(days=horizon_days)
    checkout = checkin + timedelta(days=int(contract.get("length_of_stay_nights", 2)))
    hotels = [item for item in config.get("hotels", []) if item.get("currently_open") and item.get("booking_path")]
    if hotel_limit is not None:
        hotels = hotels[:hotel_limit]

    output = Path(output_dir)
    diagnostics = output / "diagnostics" / checkin.isoformat()
    observations: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            locale="en-US",
            timezone_id="Asia/Ho_Chi_Minh",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        for hotel in hotels:
            observations.append(_collect_one(page, hotel, checkin, checkout, contract, diagnostics))
        context.close()
        browser.close()

    reliable = [row for row in observations if row["availability_state"] in {"AVAILABLE", "EXPLICITLY_UNAVAILABLE"}]
    blocked = [row for row in observations if row["availability_state"] == "BLOCKED"]
    fetch_errors = [row for row in observations if row["availability_state"] == "FETCH_ERROR"]
    coverage = len(reliable) / len(hotels) if hotels else 0.0
    latest = {
        "schema_version": "hotel-forward-shadow-0.1",
        "mode": "SHADOW",
        "eligible_for_master": False,
        "basket_version": config.get("basket_version"),
        "scan_time": iso_vn(),
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "horizon_days": horizon_days,
        "eligible_hotels": len(hotels),
        "reliable_observations": len(reliable),
        "coverage": coverage,
        "blocked_count": len(blocked),
        "fetch_error_count": len(fetch_errors),
        "observations": observations,
        "interpretation_rule": "TARGET_NOT_RETURNED or parse failure is never treated as sold out. Only explicit unavailability text may set available=false.",
    }
    if hotels and len(blocked) == len(hotels):
        state = "BLOCKED"
    elif coverage >= 0.65:
        state = "OK"
    elif reliable or (len(observations) - len(fetch_errors) - len(blocked)) > 0:
        state = "DEGRADED"
    else:
        state = "FAILED"
    health = build_health(
        "Hotel Forward Shadow",
        state,
        scheduler_triggered=True,
        collector_completed=bool(observations),
        parser_passed=bool(reliable),
        normalization_passed=bool(reliable),
        qa_passed=coverage >= 0.65,
        commit_succeeded=None,
        last_successful_run=iso_vn() if coverage >= 0.65 else None,
        failed_stage=None if state in {"OK", "DEGRADED"} else "COLLECT_OR_PARSE",
    )
    health["mode"] = "SHADOW"
    health["eligible_for_master"] = False
    health["coverage"] = coverage
    manifest = {
        "schema_version": "1.0",
        "module_schema_version": "hotel-forward-shadow-0.1",
        "collector_version": "booking-playwright-shadow-0.1.0",
        "basket_version": config.get("basket_version"),
        "source_registry_version": "1.0",
        "paid_services_used": False,
    }
    write_bundle(output, latest, health, manifest)
    write_json_atomic(output / "runs" / checkin.isoformat() / f"h{horizon_days}.json", latest)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/tourism_v2/hotel-basket.v1.json")
    parser.add_argument("--output", default="out/hotel_forward_shadow")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--hotel-limit", type=int, default=None)
    args = parser.parse_args()
    payload = collect(args.config, args.output, args.horizon, args.hotel_limit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
