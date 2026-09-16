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


def _click_text(page: Any, text: str) -> bool:
    for exact in (True, False):
        try:
            locator = page.get_by_text(text, exact=exact).first
            if locator.is_visible(timeout=900):
                locator.click(timeout=1800)
                page.wait_for_timeout(250)
                return True
        except Exception:
            continue
    return False


def _set_currency_vnd(page: Any) -> bool:
    trigger = _first_visible(page, (
        'button[data-testid="header-currency-picker-trigger"]',
        'button[aria-label*="currency" i]',
        '[data-testid="header-currency-picker-trigger"]',
    ))
    if trigger is None:
        try:
            trigger = page.get_by_text("USD", exact=True).first
            if not trigger.is_visible(timeout=900):
                trigger = None
        except Exception:
            trigger = None
    if trigger is None:
        return False
    try:
        current = (trigger.inner_text(timeout=1000) or "").upper()
        if "VND" in current:
            return True
        trigger.click(timeout=2000)
        page.wait_for_timeout(350)
        for locator in (
            page.get_by_text("VND", exact=True).last,
            page.locator('[data-testid="selection-item"]').filter(has_text="VND").last,
        ):
            try:
                if locator.is_visible(timeout=1800):
                    locator.click(timeout=2000)
                    page.wait_for_timeout(600)
                    return "VND" in _normalize_visible_text(page)
            except Exception:
                continue
    except Exception:
        return False
    return False


def _normalize_visible_text(page: Any) -> str:
    try:
        return " ".join(page.locator("body").inner_text(timeout=3000).replace("\xa0", " ").split()).upper()
    except Exception:
        return ""


def _select_destination(page: Any, hotel_name: str) -> bool:
    field = _first_visible(page, (
        'input[name="ss"]',
        'input[placeholder*="Where are you going" i]',
        'input[aria-label*="destination" i]',
        '[data-testid="destination-container"] input',
    ))
    if field is None:
        # Booking sometimes renders a clickable shell first and mounts the input only after click.
        clicked = False
        for selector in ('[data-testid="destination-container"]', '[data-testid="destination-container"] button'):
            try:
                shell = page.locator(selector).first
                if shell.is_visible(timeout=700):
                    shell.click(timeout=1600)
                    page.wait_for_timeout(250)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            clicked = _click_text(page, "Enter destination") or _click_text(page, "Where are you going?")
        if clicked:
            field = _first_visible(page, (
                'input[name="ss"]',
                'input[placeholder*="Where are you going" i]',
                'input[aria-label*="destination" i]',
                'input[role="combobox"]',
            ), timeout=1400)
    if field is None:
        return False
    try:
        field.click(timeout=1500)
        field.fill(hotel_name, timeout=2500)
        page.wait_for_timeout(1200)
        option = _first_visible(page, (
            'li[role="option"]',
            '[data-testid="autocomplete-result"]',
            '[data-testid="autocomplete-results-options"] li',
            '[role="listbox"] [role="option"]',
        ), timeout=1600)
        if option is not None:
            option.click(timeout=2200)
        else:
            field.press("ArrowDown")
            field.press("Enter")
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def _open_calendar(page: Any) -> bool:
    field = _first_visible(page, (
        'button[data-testid="date-display-field-start"]',
        '[data-testid="date-display-field-start"]',
        'button[aria-label*="Check-in" i]',
        '[data-testid="searchbox-dates-container"]',
    ))
    if field is not None:
        try:
            field.click(timeout=2000)
            page.wait_for_timeout(250)
            return True
        except Exception:
            pass
    return _click_text(page, "Select dates")


def _date_cell(page: Any, target: date):
    iso = target.isoformat()
    selectors = (
        f'[data-date="{iso}"]',
        f'span[data-date="{iso}"]',
        f'button[data-date="{iso}"]',
        f'[aria-label*="{target.strftime("%B %d, %Y")}" i]',
        f'[aria-label*="{target.strftime("%A, %B %d")}" i]',
    )
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=700):
                return locator
        except Exception:
            continue
    return None


def _next_month(page: Any) -> bool:
    locator = _first_visible(page, (
        'button[aria-label="Next month"]',
        'button[aria-label*="Next month" i]',
        '[data-testid="calendar-next-button"]',
        'button:has(svg[data-testid="chevron-right"])',
    ))
    if locator is None:
        return False
    try:
        locator.click(timeout=1500)
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def _select_dates(page: Any, checkin: date, checkout: date) -> bool:
    if not _open_calendar(page):
        return False
    for target in (checkin, checkout):
        cell = _date_cell(page, target)
        attempts = 0
        while cell is None and attempts < 10:
            if not _next_month(page):
                break
            attempts += 1
            cell = _date_cell(page, target)
        if cell is None:
            return False
        try:
            cell.click(timeout=2000)
            page.wait_for_timeout(350)
        except Exception:
            return False
    return True


def _submit(page: Any) -> bool:
    button = _first_visible(page, (
        'button[type="submit"]',
        'button:has-text("Search")',
        '[data-testid="searchbox-submit-button"]',
    ))
    if button is None:
        try:
            button = page.get_by_text("Search", exact=True).last
            if not button.is_visible(timeout=800):
                button = None
        except Exception:
            button = None
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
    """Use Booking's visible logged-out search UI when URL query parameters are discarded.

    This returns telemetry only. Any setup failure remains UNKNOWN and must never be
    interpreted as hotel unavailability.
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
