from __future__ import annotations

from datetime import date
from typing import Any


def _first_visible(page: Any, selectors: tuple[str, ...], timeout: int = 800):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=timeout):
                return locator
        except Exception:
            continue
    return None


def _set_currency_vnd(page: Any) -> bool:
    trigger = _first_visible(page, (
        'button[data-testid="header-currency-picker-trigger"]',
        'button[aria-label*="currency" i]',
    ))
    if trigger is None:
        return False
    try:
        current = (trigger.inner_text(timeout=1000) or "").upper()
        if "VND" in current:
            return True
        trigger.click(timeout=2000)
        option = page.get_by_text("VND", exact=True).last
        if option.is_visible(timeout=2500):
            option.click(timeout=2000)
            page.wait_for_timeout(600)
            trigger2 = _first_visible(page, ('button[data-testid="header-currency-picker-trigger"]', 'button[aria-label*="currency" i]'))
            return bool(trigger2 and "VND" in (trigger2.inner_text(timeout=1000) or "").upper())
    except Exception:
        return False
    return False


def _select_destination(page: Any, hotel_name: str) -> bool:
    field = _first_visible(page, ('input[name="ss"]', 'input[placeholder*="Where are you going" i]', 'input[aria-label*="destination" i]'))
    if field is None:
        return False
    try:
        field.click(timeout=1500)
        field.fill(hotel_name, timeout=2500)
        page.wait_for_timeout(1200)
        option = _first_visible(page, ('li[role="option"]', '[data-testid="autocomplete-result"]', '[data-testid="autocomplete-results-options"] li'), timeout=1200)
        if option is not None:
            option.click(timeout=2000)
        else:
            field.press("ArrowDown")
            field.press("Enter")
        return True
    except Exception:
        return False


def _open_calendar(page: Any) -> bool:
    field = _first_visible(page, (
        'button[data-testid="date-display-field-start"]',
        '[data-testid="date-display-field-start"]',
        'button[aria-label*="Check-in" i]',
    ))
    if field is None:
        try:
            page.get_by_text("Select dates", exact=False).first.click(timeout=1500)
            return True
        except Exception:
            return False
    try:
        field.click(timeout=2000)
        return True
    except Exception:
        return False


def _date_cell(page: Any, target: date):
    iso = target.isoformat()
    for selector in (f'[data-date="{iso}"]', f'span[data-date="{iso}"]', f'button[data-date="{iso}"]'):
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=600):
                return locator
        except Exception:
            continue
    return None


def _next_month(page: Any) -> bool:
    locator = _first_visible(page, (
        'button[aria-label="Next month"]',
        'button[aria-label*="Next month" i]',
        '[data-testid="calendar-next-button"]',
    ))
    if locator is None:
        return False
    try:
        locator.click(timeout=1500)
        page.wait_for_timeout(250)
        return True
    except Exception:
        return False


def _select_dates(page: Any, checkin: date, checkout: date) -> bool:
    if not _open_calendar(page):
        return False
    for target in (checkin, checkout):
        cell = _date_cell(page, target)
        attempts = 0
        while cell is None and attempts < 8:
            if not _next_month(page):
                break
            attempts += 1
            cell = _date_cell(page, target)
        if cell is None:
            return False
        try:
            cell.click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:
            return False
    return True


def _submit(page: Any) -> bool:
    button = _first_visible(page, ('button[type="submit"]', 'button:has-text("Search")'))
    if button is None:
        return False
    try:
        button.click(timeout=2500)
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        return True
    except Exception:
        return False


def configure_search_ui(page: Any, hotel_name: str, checkin: date, checkout: date) -> dict[str, Any]:
    """Use Booking's visible logged-out search UI when query parameters are discarded.

    Returns telemetry only. Failure never implies hotel unavailability.
    """
    result = {
        "destination_set": False,
        "dates_set": False,
        "currency_vnd_set": False,
        "submitted": False,
    }
    result["currency_vnd_set"] = _set_currency_vnd(page)
    result["destination_set"] = _select_destination(page, hotel_name)
    result["dates_set"] = _select_dates(page, checkin, checkout)
    if result["destination_set"] and result["dates_set"]:
        result["submitted"] = _submit(page)
    return result
