"""Capture one public iWeather COM/CMAX frame in an ordinary browser and emit
only derived Phu Quoc shadow observations.

No radar image bytes, session token or raw response body are written to disk.
No product URL is manually replayed. The script listens only to requests that
the public dashboard makes naturally.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from weather.processing.iweather_cmax import GeoBounds, decode_cmax_png

URL = "https://iweather.gov.vn/dashboard/?areaRadar=COM&productRadar=CMAX"
POINTS_PATH = Path("weather/config/points.json")
OUT = Path("weather/research/v3-iweather-cmax-shadow-receipt.json")
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _browser() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _parse_source_time(raw: str | None) -> str | None:
    if not raw or len(raw) != 12 or not raw.isdigit():
        return None
    try:
        local = datetime.strptime(raw, "%Y%m%d%H%M").replace(tzinfo=VN_TZ)
        return local.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _select_config(config: dict, source_time: str | None) -> tuple[str | None, dict | None]:
    keys = sorted(k for k in config if str(k).isdigit())
    if not keys:
        return None, None
    if source_time:
        candidates = [k for k in keys if k <= source_time]
        key = candidates[-1] if candidates else keys[-1]
    else:
        key = keys[-1]
    return key, config.get(key)


def main() -> None:
    browser_path = _browser()
    output = {
        "schema_version": "weather-v3-iweather-cmax-shadow-receipt-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "INITIALIZING",
        "mode": "PUBLIC_BROWSER_EPHEMERAL_RENDER_INTERPRETATION",
        "source_id": "iweather_radar_cmax",
        "source_class": "REMOTE_OBSERVED",
        "rights_state": "UNRESOLVED",
        "lifecycle": "SHADOW",
        "production_eligible": False,
        "independence_group": "VN_NATIONAL_RADAR_NETWORK",
        "rules": {
            "no_auth_bypass": True,
            "no_login": True,
            "no_token_archive": True,
            "no_image_archive": True,
            "no_raw_response_archive": True,
            "no_manual_product_replay": True,
            "negative_radar_is_not_dry_ground_truth": True,
        },
        "source_time_raw": None,
        "observed_at": None,
        "config_epoch": None,
        "decoder": None,
        "points": {},
        "errors": [],
    }

    if not browser_path:
        output["status"] = "NO_BROWSER"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    state: dict[str, object] = {"config": None, "time": None, "png": None}

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
                path = response.url.split("?", 1)[0]
                if response.status != 200:
                    return
                if path.endswith("/product/configProduct") and state["config"] is None:
                    state["config"] = response.json()
                elif path.endswith("/product/lastradar") and state["time"] is None:
                    payload = response.json()
                    if isinstance(payload, dict):
                        state["time"] = payload.get("time")
                elif path.endswith("/product/radar") and state["png"] is None:
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "image/png" in ctype:
                        state["png"] = response.body()
            except Exception as exc:
                output["errors"].append({"type": "response", "message": repr(exc)[:600]})

        page.on("response", on_response)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(15000)
        except Exception as exc:
            output["errors"].append({"type": "navigation", "message": repr(exc)[:800]})
        finally:
            browser.close()

    source_time = str(state["time"]) if state["time"] is not None else None
    output["source_time_raw"] = source_time
    output["observed_at"] = _parse_source_time(source_time)

    config = state["config"] if isinstance(state["config"], dict) else {}
    epoch, selected = _select_config(config, source_time)
    output["config_epoch"] = epoch

    png = state["png"]
    if not selected or not isinstance(png, (bytes, bytearray)):
        output["status"] = "INCOMPLETE_PUBLIC_RENDER"
    else:
        radar_cfg = (selected.get("radarConfig") or {}).get("COM") or {}
        try:
            bounds = GeoBounds(
                lon_min=float(radar_cfg["x_min"]),
                lon_max=float(radar_cfg["x_max"]),
                lat_min=float(radar_cfg["y_min"]),
                lat_max=float(radar_cfg["y_max"]),
            )
            points_doc = json.loads(POINTS_PATH.read_text(encoding="utf-8"))
            decoded = decode_cmax_png(
                bytes(png),
                bounds=bounds,
                points=points_doc.get("points") or {},
            )
            output["decoder"] = {
                "name": decoded["decoder"],
                "unit": decoded["unit"],
                "image_width": decoded["image_width"],
                "image_height": decoded["image_height"],
                "bounds": decoded["bounds"],
                "sentinel_policy": decoded["sentinel_policy"],
                "negative_evidence_policy": decoded["negative_evidence_policy"],
            }
            output["points"] = decoded["points"]
            output["status"] = "SHADOW_POINT_OBSERVATIONS_READY"
        except Exception as exc:
            output["status"] = "DECODE_FAILED"
            output["errors"].append({"type": "decode", "message": repr(exc)[:1000]})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "source_time_raw": output["source_time_raw"],
        "observed_at": output["observed_at"],
        "config_epoch": output["config_epoch"],
        "point_count": len(output["points"]),
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
