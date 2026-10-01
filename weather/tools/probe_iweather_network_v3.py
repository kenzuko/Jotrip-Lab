"""One-shot public browser-network metadata probe for iWeather V3 research.

This intentionally behaves like an ordinary unauthenticated browser:
- no credentials or cookies are injected
- no login is attempted
- no response bodies or radar images are saved
- no discovered endpoint is called manually
- only requests naturally made while rendering the public dashboard are observed

The output contains request/response metadata only, with sensitive-looking query
values redacted.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

URL = "https://iweather.gov.vn/dashboard/?areaRadar=COM&lightning=true&productRadar=CMAX"
OUT = Path("weather/research/v3-iweather-network-probe.json")
SENSITIVE = {"token", "access_token", "apikey", "api_key", "key", "signature", "sig", "session", "jwt", "auth"}


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        query = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            query.append((key, "[REDACTED]" if key.lower() in SENSITIVE else val))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    except Exception:
        return value.split("#", 1)[0]


def find_browser() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def main() -> None:
    browser_path = find_browser()
    payload = {
        "schema_version": "weather-v3-iweather-network-probe-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "UNAUTHENTICATED_PUBLIC_BROWSER_METADATA_ONLY",
        "target": URL,
        "browser_path": browser_path,
        "rules": {
            "no_auth_bypass": True,
            "no_login": True,
            "no_response_body_archive": True,
            "no_image_archive": True,
            "natural_browser_requests_only": True,
        },
        "status": "INITIALIZING",
        "frames": [],
        "responses": [],
        "errors": [],
    }

    if not browser_path:
        payload["status"] = "NO_SYSTEM_BROWSER"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(payload["status"])
        return

    seen: dict[tuple[str, str, int | None], dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=browser_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            locale="vi-VN",
            user_agent="Mozilla/5.0 (compatible; JoTrip-WeatherV3-Research/1.0; public-dashboard-observer)",
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()

        def on_response(response):
            req = response.request
            url = redact_url(response.url)
            key = (req.method, url, response.status)
            if key in seen:
                return
            headers = response.headers
            row = {
                "method": req.method,
                "url": url,
                "status": response.status,
                "resource_type": req.resource_type,
                "content_type": headers.get("content-type"),
                "content_length": headers.get("content-length"),
                "cache_control": headers.get("cache-control"),
            }
            seen[key] = row

        page.on("response", on_response)
        page.on("pageerror", lambda exc: payload["errors"].append({"type": "pageerror", "message": str(exc)[:500]}))

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(15000)
            payload["title"] = page.title()
            payload["final_url"] = redact_url(page.url)
            payload["frames"] = [redact_url(f.url) for f in page.frames]
            payload["status"] = "CAPTURED"
        except Exception as exc:
            payload["status"] = "PARTIAL"
            payload["errors"].append({"type": "navigation", "message": repr(exc)[:1000]})
        finally:
            browser.close()

    rows = list(seen.values())
    payload["responses"] = rows
    payload["response_count"] = len(rows)
    payload["interesting"] = [
        row for row in rows
        if any(token in (row.get("url") or "").lower() for token in (
            "radar", "cmax", "lightning", "wms", "wmts", "tile", "geojson",
            "qpe", "rain", "satellite", "image", "map"
        ))
        or (row.get("resource_type") in {"xhr", "fetch"})
    ]

    # Make auth walls explicit. Never retry or work around them.
    payload["blocked_routes"] = [
        row for row in rows if row.get("status") in {401, 403}
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "response_count": payload.get("response_count", 0),
        "interesting_count": len(payload.get("interesting") or []),
        "blocked_count": len(payload.get("blocked_routes") or []),
        "frames": payload.get("frames"),
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
