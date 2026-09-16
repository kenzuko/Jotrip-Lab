from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.contracts import build_health, iso_vn, write_bundle
from tourism_intelligence_v2.storage import read_json, write_json_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
BOOKING_ORIGIN = "https://www.booking.com"
BLOCK_PATTERNS = ("verify you are human", "captcha", "access denied", "unusual traffic", "robot")
UNAVAILABLE_PATTERNS = (
    "not available on our site for your dates",
    "not available for your dates",
    "no availability",
    "sold out",
    "hết phòng",
    "không còn phòng",
    "không có phòng trống",
)


def _normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _normalize_text(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", decomposed.lower()).strip()


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _fold(left), _fold(right)).ratio()


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


def _build_search_url(hotel_name: str, checkin: date, checkout: date, contract: dict[str, Any]) -> str:
    params = {
        "ss": hotel_name,
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "group_adults": int(contract.get("adults", 2)),
        "group_children": int(contract.get("children", 0)),
        "no_rooms": int(contract.get("rooms", 1)),
        "selected_currency": contract.get("currency", "VND"),
        "lang": "en-us",
    }
    return f"{BOOKING_ORIGIN}/searchresults.html?{urlencode(params)}"


def _click_consent(page: Any) -> None:
    for selector in ('button:has-text("Accept")', 'button:has-text("Accept all")', 'button:has-text("I agree")'):
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=700):
                locator.click(timeout=1500)
                return
        except Exception:
            continue


def _date_context_verified(page_url: str, body: str, checkin: date, checkout: date) -> bool:
    if checkin.isoformat() in page_url and checkout.isoformat() in page_url:
        return True
    lower = body.lower()
    check_tokens = {
        checkin.strftime("%b %d").lower(),
        checkin.strftime("%B %d").lower(),
        checkin.strftime("%a, %b %d").lower(),
    }
    out_tokens = {
        checkout.strftime("%b %d").lower(),
        checkout.strftime("%B %d").lower(),
        checkout.strftime("%a, %b %d").lower(),
    }
    return any(token in lower for token in check_tokens) and any(token in lower for token in out_tokens)


def _best_card(page: Any, target_name: str) -> tuple[Any | None, str | None, float]:
    try:
        cards = page.locator('[data-testid="property-card"]')
        count = min(cards.count(), 80)
    except Exception:
        return None, None, 0.0
    best_card = None
    best_title = None
    best_score = 0.0
    for index in range(count):
        card = cards.nth(index)
        title = ""
        try:
            title = _normalize_text(card.locator('[data-testid="title"]').first.inner_text(timeout=1000))
        except Exception:
            try:
                title = _normalize_text(card.inner_text(timeout=1000).split("\n", 1)[0])
            except Exception:
                continue
        score = _similarity(target_name, title)
        if score > best_score:
            best_card, best_title, best_score = card, title, score
    return best_card, best_title, best_score


def _collect_one(page: Any, hotel: dict[str, Any], checkin: date, checkout: date, contract: dict[str, Any], diagnostics_dir: Path) -> dict[str, Any]:
    url = _build_search_url(hotel["hotel_name"], checkin, checkout, contract)
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
    body = ""
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
        observation["date_context_verified"] = _date_context_verified(page.url, body, checkin, checkout)

        if any(pattern in lower for pattern in BLOCK_PATTERNS):
            observation["availability_state"] = "BLOCKED"
            observation["error"] = "Booking page presented anti-bot/access challenge"
        elif not observation["date_context_verified"]:
            observation["availability_state"] = "DATE_CONTEXT_UNVERIFIED"
            observation["error"] = "Requested stay dates could not be verified on the rendered search page"
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
                explicit_unavailable = any(pattern in card_lower for pattern in UNAVAILABLE_PATTERNS)
                if values:
                    observation["availability_state"] = "AVAILABLE"
                    observation["available"] = True
                    observation["rate_all_in_vnd"] = min(values)
                    observation["price_candidates_vnd"] = sorted(set(values))[:20]
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_VND_PRICE"
                elif explicit_unavailable:
                    observation["availability_state"] = "EXPLICITLY_UNAVAILABLE"
                    observation["available"] = False
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_EXPLICIT_UNAVAILABLE"
                else:
                    observation["availability_state"] = "MATCHED_CARD_NO_RELIABLE_RATE"
                    observation["rate_observation_method"] = "MATCHED_PROPERTY_CARD_PARSE_INCOMPLETE"
                observation["breakfast_text_visible"] = "breakfast" in card_lower
                observation["free_cancellation_text_visible"] = "free cancellation" in card_lower
                observation["taxes_and_fees_text_visible"] = "taxes and fees" in card_lower
                try:
                    href = card.locator('a[data-testid="title-link"]').first.get_attribute("href")
                    observation["matched_property_url"] = href
                except Exception:
                    pass

        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", hotel["hotel_id"])
        (diagnostics_dir / f"{safe_name}.txt").write_text(body[:150_000], encoding="utf-8")
        page.screenshot(path=str(diagnostics_dir / f"{safe_name}.png"), full_page=False)
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
    fetch_errors = [row for row in observations if row["availability_state"] == "FETCH_ERROR"]
    coverage = len(reliable) / len(hotels) if hotels else 0.0
    latest = {
        "schema_version": "hotel-forward-shadow-0.2",
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
        "interpretation_rule": "TARGET_NOT_RETURNED, date failure or parse failure is never treated as sold out. Only matched-card explicit unavailability may set available=false.",
    }
    if hotels and len(blocked) == len(hotels):
        state = "BLOCKED"
    elif coverage >= 0.65:
        state = "OK"
    elif observations:
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
        "module_schema_version": "hotel-forward-shadow-0.2",
        "collector_version": "booking-playwright-shadow-0.2.0",
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
