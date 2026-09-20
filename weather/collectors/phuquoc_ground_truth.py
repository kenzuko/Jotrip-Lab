"""Collect public, machine-readable Phu Quoc ground truth.

Sources:
- Aviation Weather Center METAR JSON for VVPQ.
- VRain public current accumulation feed for Phu Quoc rain gauges.

No authentication bypass is attempted. Stations whose public numeric feed is known to
be empty are retained as metadata only and MUST NOT be treated as observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AWC_URL = "https://aviationweather.gov/api/data/metar?ids=VVPQ&format=json&hours=24"
VRAIN_CURRENT_URL = "https://data.vrain.vn/public/current/all.json"
VRAIN_TIME_URL = "https://vrain.vn/api/public/v1/time"
USER_AGENT = "JoTrip-WeatherLab/1.0 ground-truth collector (public data)"

PHU_QUOC_RAIN_BOUNDS = (9.80, 10.55, 103.65, 104.25)

KNOWN_STATIONS = {
    "VVPQ": {
        "station_id": "VVPQ",
        "station_name": "Phu Quoc International Airport",
        "location_id": "phu_quoc_airport",
        "lat": 10.169,
        "lon": 103.995,
        "source": "AVIATION_WEATHER_CENTER_METAR",
        "readiness": "PRODUCTION_ACTUAL",
    },
}


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode("utf-8"))


def _iso_from_epoch(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _finite(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _latest_vvpq(rows: Any, now: datetime) -> dict:
    if not isinstance(rows, list):
        return {"status": "UNAVAILABLE", "detail": "AWC payload is not a list"}
    candidates = [r for r in rows if str(r.get("icaoId", "")).upper() == "VVPQ"]
    candidates.sort(key=lambda r: int(r.get("obsTime") or 0), reverse=True)
    if not candidates:
        return {"status": "UNAVAILABLE", "detail": "No VVPQ METAR returned"}

    r = candidates[0]
    observed_at = _iso_from_epoch(r.get("obsTime")) or r.get("reportTime")
    observed_dt = _parse_iso(observed_at)
    age_min = None
    if observed_dt:
        age_min = max(0.0, (now - observed_dt).total_seconds() / 60.0)

    wspd_kt = _finite(r.get("wspd"))
    vis_sm = _finite(r.get("visib"))
    raw = str(r.get("rawOb") or "")
    wx = str(r.get("wxString") or "")
    clouds = r.get("clouds") if isinstance(r.get("clouds"), list) else []
    convective = ("CB" in raw) or ("TCU" in raw) or ("TS" in wx)

    status = "FRESH" if age_min is not None and age_min <= 90 else "STALE"
    return {
        "status": status,
        "station_id": "VVPQ",
        "station_name": "Phu Quoc International Airport",
        "location_id": "phu_quoc_airport",
        "lat": _finite(r.get("lat")) or 10.169,
        "lon": _finite(r.get("lon")) or 103.995,
        "source": "AVIATION_WEATHER_CENTER_METAR",
        "source_channel": "METAR",
        "data_class": "ACTUAL",
        "observed_at": observed_at,
        "age_minutes": round(age_min, 1) if age_min is not None else None,
        "temperature_c": _finite(r.get("temp")),
        "dewpoint_c": _finite(r.get("dewp")),
        "wind_direction_deg": _finite(r.get("wdir")),
        "wind_speed_kt": wspd_kt,
        "wind_speed_ms": round(wspd_kt * 0.514444, 3) if wspd_kt is not None else None,
        "wind_speed_kmh": round(wspd_kt * 1.852, 2) if wspd_kt is not None else None,
        "pressure_hpa": _finite(r.get("altim")),
        "visibility_sm": vis_sm,
        "visibility_m": round(vis_sm * 1609.344) if vis_sm is not None else None,
        "weather": wx or None,
        "convective_cloud": convective,
        "clouds": clouds,
        "flight_category": r.get("fltCat"),
        "raw_observation": raw,
        "qc": "PASS" if status == "FRESH" else "STALE",
        "provenance_url": AWC_URL,
        "raw_payload_hash": _sha(r),
    }


def _previous_station(previous: dict | None, station_key: str) -> dict | None:
    if not isinstance(previous, dict):
        return None
    return previous.get("rainfall", {}).get("stations", {}).get(station_key)


def _rain_key(name: str) -> str:
    mapping = {
        "Cửa Cạn": "cua_can",
        "Bãi Thơm": "bai_thom",
        "An Thới": "an_thoi",
    }
    return mapping.get(name, name.lower().replace(" ", "_"))


def _vrain(current: Any, timing: Any, previous: dict | None, now: datetime) -> dict:
    rows = current if isinstance(current, list) else []
    lat0, lat1, lon0, lon1 = PHU_QUOC_RAIN_BOUNDS

    start_epoch = timing.get("fr") if isinstance(timing, dict) else None
    end_epoch = timing.get("n") if isinstance(timing, dict) else None
    period_start = _iso_from_epoch(start_epoch)
    period_end = _iso_from_epoch(end_epoch)
    end_dt = _parse_iso(period_end)
    age_min = max(0.0, (now - end_dt).total_seconds() / 60.0) if end_dt else None

    stations: dict[str, dict] = {}
    for r in rows:
        lat = _finite(r.get("lt"))
        lon = _finite(r.get("lg"))
        if lat is None or lon is None or not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            continue
        name = str(r.get("sn") or "").strip()
        if not name:
            continue
        key = _rain_key(name)
        accum = _finite(r.get("d"))
        item = {
            "station_id": f"VRAIN_{key.upper()}",
            "station_name": name,
            "location_id": f"rain_{key}",
            "lat": lat,
            "lon": lon,
            "source": "VRAIN_PUBLIC",
            "source_channel": "current/all.json",
            "data_class": "ACTUAL",
            "observed_at": period_end,
            "age_minutes": round(age_min, 1) if age_min is not None else None,
            "variable": "precipitation",
            "accumulation_mm": accum,
            "accumulation_label": r.get("l"),
            "period_start": period_start,
            "period_end": period_end,
            "statistic": "ACCUMULATION",
            "timestamp_semantics": "END_OF_WINDOW",
            "increment_mm": None,
            "increment_window_minutes": None,
            "rain_observed": None,
            "rain_intensity_mm_h": None,
            "increment_qc": "NO_PREVIOUS_SAMPLE",
            "qc": "PASS" if accum is not None else "MISSING",
            "provenance_url": VRAIN_CURRENT_URL,
            "raw_payload_hash": _sha(r),
        }

        prev = _previous_station(previous, key)
        if prev and accum is not None:
            prev_accum = _finite(prev.get("accumulation_mm"))
            prev_start = prev.get("period_start")
            prev_end_dt = _parse_iso(prev.get("period_end") or prev.get("observed_at"))
            if prev_accum is not None and prev_start == period_start and prev_end_dt and end_dt and end_dt > prev_end_dt:
                minutes = (end_dt - prev_end_dt).total_seconds() / 60.0
                delta = accum - prev_accum
                if -0.05 <= delta and 5 <= minutes <= 20:
                    increment = round(max(0.0, delta), 3)
                    item["increment_mm"] = increment
                    item["increment_window_minutes"] = round(minutes, 1)
                    item["rain_observed"] = increment > 0
                    item["rain_intensity_mm_h"] = round(increment * 60.0 / minutes, 3)
                    item["increment_qc"] = "PASS"
                elif delta < -0.05:
                    item["increment_qc"] = "ACCUMULATION_RESET"
                elif minutes < 5:
                    item["increment_qc"] = "WINDOW_TOO_SHORT"
                elif minutes > 20:
                    item["increment_qc"] = "WINDOW_TOO_OLD_FOR_CURRENT_RAIN"
        stations[key] = item

    return {
        "status": "FRESH" if stations and age_min is not None and age_min <= 90 else ("STALE" if stations else "UNAVAILABLE"),
        "source": "VRAIN_PUBLIC",
        "period_start": period_start,
        "period_end": period_end,
        "stations": stations,
        "provenance_url": VRAIN_CURRENT_URL,
    }


def collect(previous: dict | None = None) -> dict:
    now = datetime.now(timezone.utc)
    errors: list[dict] = []

    try:
        awc = _fetch_json(AWC_URL)
        vvpq = _latest_vvpq(awc, now)
    except Exception as exc:  # network boundary
        errors.append({"source": "VVPQ_AWC", "error": repr(exc)})
        vvpq = {"status": "UNAVAILABLE", "detail": repr(exc)}

    try:
        vrain_current = _fetch_json(VRAIN_CURRENT_URL)
        vrain_time = _fetch_json(VRAIN_TIME_URL)
        rainfall = _vrain(vrain_current, vrain_time, previous, now)
    except Exception as exc:  # network boundary
        errors.append({"source": "VRAIN", "error": repr(exc)})
        rainfall = {"status": "UNAVAILABLE", "stations": {}, "detail": repr(exc)}

    payload = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "status": "READY" if vvpq.get("status") in {"FRESH", "STALE"} or rainfall.get("stations") else "UNAVAILABLE",
        "actual_policy": "Only machine-readable numeric observations with timestamps are ACTUAL. Remote sensing and models are separate classes.",
        "atmosphere": {"vvpq": vvpq},
        "rainfall": rainfall,
        "station_status": KNOWN_STATIONS,
        "errors": errors,
    }
    payload["payload_hash"] = _sha(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()

    previous = None
    if args.previous and args.previous.exists():
        try:
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    payload = collect(previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "generated_at": payload["generated_at"],
        "vvpq": payload["atmosphere"]["vvpq"].get("status"),
        "rain_stations": list(payload["rainfall"].get("stations", {})),
        "rain_increment_ready": [
            k for k, v in payload["rainfall"].get("stations", {}).items()
            if v.get("increment_qc") == "PASS"
        ],
        "errors": payload["errors"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
