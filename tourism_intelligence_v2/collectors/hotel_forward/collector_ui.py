from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tourism_intelligence_v2.collectors.hotel_forward.booking_ui import configure_search_ui
from tourism_intelligence_v2.collectors.hotel_forward.collector import (
    BOOKING_ORIGIN,
    BLOCK_PATTERNS,
    UNAVAILABLE_PATTERNS,
    _best_card,
    _click_consent,
    _date_context_verified,
    _normalize_text,
    _parse_vnd,
)
from tourism_intelligence_v2.contracts import VN, build_health, iso_vn, write_bundle
from tourism_intelligence_v2.storage import read_json, write_json_atomic


def _collect_one(page: Any, hotel: dict[str, Any], checkin, checkout, contract: dict[str, Any], diagnostics_dir: Path) -> dict[str, Any]:
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
        "source_url": BOOKING_ORIGIN,
        "observed_at": iso_vn(started),
        "availability_state": "UNKNOWN",
        "available": None,
        "rate_all_in_vnd": None,
        "rate_observation_method": None,
        "date_context_verified": False,
        "evidence_class": "DIRECT",
        "search_setup_method": "VISIBLE_LOGGED_OUT_UI",
    }
    body = ""
    try:
        response = page.goto(f"{BOOKING_ORIGIN}/searchresults.html", wait_until="domcontentloaded", timeout=45_000)
        _click_consent(page)
        telemetry = configure_search_ui(page, hotel["hotel_name"], checkin, checkout)
        observation["ui_setup"] = telemetry
        body = _normalize_text(page.locator("body").inner_text(timeout=10_000))
        lower = body.lower()
        observation["http_status"] = response.status if response else None
        observation["final_url"] = page.url
        observation["page_title"] = page.title()
        observation["date_context_verified"] = _date_context_verified(page.url, body, checkin, checkout)

        if any(pattern in lower for pattern in BLOCK_PATTERNS):
            observation["availability_state"] = "BLOCKED"
            observation["error"] = "Booking page presented anti-bot/access challenge"
        elif not telemetry.get("submitted"):
            observation["availability_state"] = "SEARCH_UI_SETUP_FAILED"
            observation["error"] = "Could not set destination and dates through visible Booking search controls"
        elif not observation["date_context_verified"]:
            observation["availability_state"] = "DATE_CONTEXT_UNVERIFIED"
            observation["error"] = "UI submitted but requested stay dates could not be verified"
        else:
            card, matched_title, match_score = _best_card(page, hotel["hotel_name"])
            observation["matched_title"] = matched_title
            observation["title_match_score"] = round(match_score, 4)
            if card is None or match_score < 0.62:
                observation["availability_state"] = "TARGET_NOT_RETURNED"
                observation["rate_observation_method"] = "NO_MATCHING_PROPERTY_CARD"
            else:
                card_text = _normalize_text(card.inner_text(timeout=3000))
                card_lower = card_text.lower()
                values = _parse_vnd(card_text)
                if values:
                    observation["availability_state"] = "AVAILABLE"
                    observation["available"] = True
                    observation["rate_all_in_vnd"] = min(values)
                    observation["price_candidates_vnd"] = sorted(set(values))[:20]
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_VND_PRICE"
                elif any(pattern in card_lower for pattern in UNAVAILABLE_PATTERNS):
                    observation["availability_state"] = "EXPLICITLY_UNAVAILABLE"
                    observation["available"] = False
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_EXPLICIT_UNAVAILABLE"
                else:
                    observation["availability_state"] = "MATCHED_CARD_NO_RELIABLE_RATE"
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_PARSE_INCOMPLETE"
                observation["breakfast_text_visible"] = "breakfast" in card_lower
                observation["free_cancellation_text_visible"] = "free cancellation" in card_lower
                observation["taxes_and_fees_text_visible"] = "taxes and fees" in card_lower

        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", hotel["hotel_id"])
        (diagnostics_dir / f"{safe}.txt").write_text(body[:150_000], encoding="utf-8")
        page.screenshot(path=str(diagnostics_dir / f"{safe}.png"), full_page=False)
    except Exception as exc:
        observation["availability_state"] = "FETCH_ERROR"
        observation["error"] = f"{type(exc).__name__}: {exc}"
    return observation


def collect(config_path: str | Path, output_dir: str | Path, horizon_days: int, hotel_limit: int | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    config = read_json(config_path)
    contract = config["search_contract"]
    today = datetime.now(VN).date()
    checkin = today + timedelta(days=horizon_days)
    checkout = checkin + timedelta(days=int(contract.get("length_of_stay_nights", 2)))
    hotels = [item for item in config.get("hotels", []) if item.get("currently_open")]
    if hotel_limit is not None:
        hotels = hotels[:hotel_limit]
    output = Path(output_dir)
    diagnostics = output / "diagnostics" / checkin.isoformat()
    observations: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(locale="en-US", timezone_id="Asia/Ho_Chi_Minh", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        for hotel in hotels:
            observations.append(_collect_one(page, hotel, checkin, checkout, contract, diagnostics))
        context.close()
        browser.close()

    reliable = [row for row in observations if row["availability_state"] in {"AVAILABLE", "EXPLICITLY_UNAVAILABLE"}]
    blocked = [row for row in observations if row["availability_state"] == "BLOCKED"]
    coverage = len(reliable) / len(hotels) if hotels else 0.0
    latest = {
        "schema_version": "hotel-forward-shadow-0.3",
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
        "observations": observations,
        "interpretation_rule": "UI/search/date failures and TARGET_NOT_RETURNED never mean sold out. Only explicit matched-card unavailability may set available=false.",
    }
    state = "BLOCKED" if hotels and len(blocked) == len(hotels) else ("OK" if coverage >= 0.65 else "DEGRADED")
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
    )
    health["mode"] = "SHADOW"
    health["eligible_for_master"] = False
    health["coverage"] = coverage
    manifest = {
        "schema_version": "1.0",
        "module_schema_version": "hotel-forward-shadow-0.3",
        "collector_version": "booking-visible-ui-shadow-0.3.0",
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
