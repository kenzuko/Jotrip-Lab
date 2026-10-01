"""One-shot iWeather public payload-shape probe for Weather V3.

This extends the browser metadata probe only enough to understand the public
rendered product:
- selected public JSON responses are summarized/sanitized in memory
- the radar PNG is inspected in memory for geometry/color statistics
- no raw JSON body or image bytes are written to disk
- no credentials are supplied, copied or replayed
"""
from __future__ import annotations

import io
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "https://iweather.gov.vn/dashboard/?areaRadar=COM&productRadar=CMAX"
OUT = Path("weather/research/v3-iweather-payload-shape.json")
JSON_PATHS = {
    "/product/configProduct",
    "/product/lastradar",
}
SENSITIVE_KEYS = {
    "token", "access_token", "apikey", "api_key", "key", "signature", "sig",
    "session", "jwt", "authorization", "password", "secret"
}


def find_browser() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def sanitize(value, *, depth=0):
    if depth > 5:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        out = {}
        for k, v in list(value.items())[:120]:
            if str(k).lower() in SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = sanitize(v, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(v, depth=depth + 1) for v in value[:80]]
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:300]


def shape(value, *, depth=0):
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        return {str(k): shape(v, depth=depth+1) for k, v in list(value.items())[:150]}
    if isinstance(value, list):
        sample = value[:3]
        return {
            "_type": "list",
            "count": len(value),
            "sample_shape": [shape(v, depth=depth+1) for v in sample],
        }
    return type(value).__name__


def radar_image_stats(raw: bytes) -> dict:
    with Image.open(io.BytesIO(raw)) as img:
        rgba = img.convert("RGBA")
        width, height = rgba.size
        pixels = list(rgba.getdata())
        opaque = [p for p in pixels if p[3] > 0]
        nontransparent = len(opaque)
        bbox = rgba.getbbox()
        colors = Counter(opaque)
        top = [
            {"rgba": list(color), "count": count}
            for color, count in colors.most_common(40)
        ]
        return {
            "format": img.format,
            "width": width,
            "height": height,
            "mode": img.mode,
            "nontransparent_pixels": nontransparent,
            "total_pixels": width * height,
            "nontransparent_fraction": round(nontransparent / (width * height), 6) if width and height else None,
            "nontransparent_bbox": list(bbox) if bbox else None,
            "unique_nontransparent_colors": len(colors),
            "top_nontransparent_colors": top,
        }


def main() -> None:
    browser_path = find_browser()
    out = {
        "schema_version": "weather-v3-iweather-payload-shape-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": URL,
        "mode": "PUBLIC_BROWSER_IN_MEMORY_DERIVATION_ONLY",
        "rules": {
            "no_auth_bypass": True,
            "no_login": True,
            "no_token_replay": True,
            "no_raw_json_archive": True,
            "no_image_archive": True,
            "derived_metadata_only": True,
        },
        "status": "INITIALIZING",
        "json_products": {},
        "radar_image": None,
        "errors": [],
    }

    if not browser_path:
        out["status"] = "NO_SYSTEM_BROWSER"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    captured_paths: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=browser_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = browser.new_page(
            locale="vi-VN",
            user_agent="Mozilla/5.0 (compatible; JoTrip-WeatherV3-Research/1.0; public-render-observer)",
            viewport={"width": 1365, "height": 900},
        )

        def on_response(response):
            try:
                parts = urlsplit(response.url)
                path = parts.path
                if path in JSON_PATHS and response.status == 200 and path not in captured_paths:
                    data = response.json()
                    out["json_products"][path] = {
                        "content_type": response.headers.get("content-type"),
                        "shape": shape(data),
                        "sanitized_sample": sanitize(data),
                    }
                    captured_paths.add(path)
                elif path == "/product/radar" and response.status == 200 and out["radar_image"] is None:
                    raw = response.body()
                    out["radar_image"] = radar_image_stats(raw)
                    out["radar_image"]["timestamp_query_present"] = "time=" in (parts.query or "")
                    out["radar_image"]["mode_query_present"] = "mode=" in (parts.query or "")
                    out["radar_image"]["area_query_present"] = "area=" in (parts.query or "")
                    out["radar_image"]["product_query_present"] = "product=" in (parts.query or "")
            except Exception as exc:
                out["errors"].append({"type": "response_parse", "path": urlsplit(response.url).path, "message": repr(exc)[:700]})

        page.on("response", on_response)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(15000)
            out["status"] = "CAPTURED"
            out["title"] = page.title()
        except Exception as exc:
            out["status"] = "PARTIAL"
            out["errors"].append({"type": "navigation", "message": repr(exc)[:1000]})
        finally:
            browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": out["status"],
        "json_products": sorted(out["json_products"]),
        "radar_image": out["radar_image"],
        "errors": out["errors"],
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
