"""Collect city-level realtime US AQI from IQAir Community API.

This collector is optional and isolated. It never changes Weather/Marine decision logic.
The Community API exposes realtime city-level AQI but not pollutant concentrations,
so CAMS remains the PM2.5/PM10/model-reference layer.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from weather.points import POINTS

API = "https://api.airvisual.com/v2/nearest_city"
COMMUNITY_MIN_INTERVAL_SECONDS = 13.0  # stays below 5 requests/minute


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _category(aqi: int | None) -> str | None:
    if aqi is None:
        return None
    if aqi <= 50:
        return "GOOD"
    if aqi <= 100:
        return "MODERATE"
    if aqi <= 150:
        return "UNHEALTHY_FOR_SENSITIVE_GROUPS"
    if aqi <= 200:
        return "UNHEALTHY"
    if aqi <= 300:
        return "VERY_UNHEALTHY"
    return "HAZARDOUS"


def _request(lat: float, lon: float, key: str) -> dict:
    url = f"{API}?{urlencode({'lat': lat, 'lon': lon, 'key': key})}"
    req = Request(url, headers={"User-Agent": "JoTrip-Weather-Lab/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise RuntimeError(f"IQAir API status={payload.get('status')!r}")
    return payload["data"]


def collect(key: str) -> dict:
    points: dict[str, dict] = {}
    errors: dict[str, str] = {}
    sampled: list[str] = []
    for index, (point_id, (lat, lon)) in enumerate(POINTS.items()):
        if index:
            time.sleep(COMMUNITY_MIN_INTERVAL_SECONDS)
        try:
            data = _request(lat, lon, key)
            current = data.get("current") or {}
            pollution = current.get("pollution") or {}
            aqi = pollution.get("aqius")
            aqi = int(aqi) if aqi is not None else None
            ts = pollution.get("ts")
            if ts:
                sampled.append(str(ts))
            location = data.get("location") or {}
            coords = location.get("coordinates") if isinstance(location.get("coordinates"), list) else []
            points[point_id] = {
                "aqi_us": aqi,
                "category": _category(aqi),
                "dominant_pollutant": pollution.get("mainus"),
                "sampled_time": ts,
                "city": data.get("city"),
                "state": data.get("state"),
                "country": data.get("country"),
                "source_lat": coords[1] if len(coords) >= 2 else None,
                "source_lon": coords[0] if len(coords) >= 2 else None,
                "source_type": "REALTIME_CITY_PLATFORM",
                "coverage_note": "IQAir Community API city/nearest-city realtime AQI; source may combine ground observations and modelled estimates depending on local coverage.",
            }
            if aqi is None:
                errors[point_id] = "AQI missing in IQAir payload"
        except Exception as exc:
            errors[point_id] = f"{type(exc).__name__}: {exc}"

    ready = sum(1 for p in points.values() if p.get("aqi_us") is not None)
    return {
        "status": "POINT_NUMERIC_READY" if ready == len(POINTS) else ("PARTIAL" if ready else "UNAVAILABLE"),
        "source": "IQAIR_COMMUNITY_REALTIME",
        "source_type": "REALTIME_CITY_PLATFORM",
        "method": "NEAREST_CITY_US_AQI",
        "sampled_time": max(sampled) if sampled else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "points": points,
        "errors": errors,
        "detail": f"IQAir Community API realtime city-level AQI ready for {ready}/{len(POINTS)} Weather Lab points; requests paced for Community API limits",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("IQAIR_API_KEY", "").strip()
    if not key:
        payload = {
            "status": "CREDENTIALS_MISSING",
            "source": "IQAIR_COMMUNITY_REALTIME",
            "source_type": "REALTIME_CITY_PLATFORM",
            "method": "NEAREST_CITY_US_AQI",
            "sampled_time": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "points": {},
            "errors": {},
            "detail": "Set optional GitHub Actions secret IQAIR_API_KEY to enable realtime IQAir AQI. CAMS remains the fallback.",
        }
    else:
        try:
            payload = collect(key)
        except Exception as exc:
            payload = {
                "status": "UNAVAILABLE",
                "source": "IQAIR_COMMUNITY_REALTIME",
                "source_type": "REALTIME_CITY_PLATFORM",
                "method": "NEAREST_CITY_US_AQI",
                "sampled_time": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "points": {},
                "errors": {"collector": f"{type(exc).__name__}: {exc}"},
                "detail": "IQAir optional layer unavailable; CAMS fallback is unaffected.",
            }
    _write(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
