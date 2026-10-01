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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from weather.collectors.phuquoc_synop_raw import collect as collect_synop, compact_live as compact_synop_live
from weather.processing.groundtruth_corpus import build_corpus

AWC_URL = "https://aviationweather.gov/api/data/metar?ids=VVPQ&format=json&hours=24"
VRAIN_CURRENT_URL = "https://data.vrain.vn/public/current/all.json"
VRAIN_TIME_URL = "https://vrain.vn/api/public/v1/time"
USER_AGENT = "JoTrip-WeatherLab/2.0 ground-truth collector (public data)"
GROUNDTRUTH_SEED = Path("weather/groundtruth/corpus/observations_seed_v6.csv")
GROUNDTRUTH_REGISTRY = Path("weather/config/groundtruth_sources.json")

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
    source_reported_at = _iso_from_epoch(end_epoch)
    source_reported_dt = _parse_iso(source_reported_at)
    checked_at = now.isoformat()

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
        raw_hash = _sha(r)
        prev = _previous_station(previous, key)
        prev_hash = str((prev or {}).get("raw_payload_hash") or "")
        same_payload = bool(prev and prev_hash and prev_hash == raw_hash)

        # The VRain /time endpoint advances even when the station row itself has
        # not changed. A fetch timestamp is therefore NOT a new observation.
        # Preserve the last proven observation time until the station payload changes.
        previous_observed_at = (prev or {}).get("observed_at") or (prev or {}).get("period_end")
        observed_at = previous_observed_at if same_payload and previous_observed_at else source_reported_at
        observed_dt = _parse_iso(observed_at)
        age_min = max(0.0, (now - observed_dt).total_seconds() / 60.0) if observed_dt else None
        effective_period_end = (prev or {}).get("period_end") if same_payload and (prev or {}).get("period_end") else source_reported_at

        prev_accum = _finite((prev or {}).get("accumulation_mm"))
        value_changed = bool(
            not same_payload
            and prev_accum is not None
            and accum is not None
            and abs(accum - prev_accum) > 0.0005
        )
        last_value_changed_at = (
            source_reported_at if value_changed
            else (prev or {}).get("last_value_changed_at")
            or previous_observed_at
            or observed_at
        )

        item = {
            "station_id": f"VRAIN_{key.upper()}",
            "station_name": name,
            "location_id": f"rain_{key}",
            "lat": lat,
            "lon": lon,
            "source": "VRAIN_PUBLIC",
            "source_channel": "current/all.json",
            "data_class": "ACTUAL",
            "observed_at": observed_at,
            "source_reported_at": source_reported_at,
            "fetched_at": checked_at,
            "last_checked_at": checked_at,
            "last_value_changed_at": last_value_changed_at,
            "sample_state": "UNCHANGED_PAYLOAD" if same_payload else "NEW_SOURCE_PAYLOAD",
            "value_changed": value_changed,
            "age_minutes": round(age_min, 1) if age_min is not None else None,
            "variable": "precipitation",
            "accumulation_mm": accum,
            "accumulation_label": r.get("l"),
            "period_start": period_start,
            "period_end": effective_period_end,
            "statistic": "ACCUMULATION",
            "timestamp_semantics": "SOURCE_WINDOW_END_ONLY_WHEN_PAYLOAD_CHANGES",
            "increment_mm": None,
            "increment_window_minutes": None,
            "rain_observed": None,
            "rain_intensity_mm_h": None,
            "recent_change_mm": None,
            "recent_change_window_minutes": None,
            "rain_recently_observed": None,
            "increment_qc": "NO_NEW_SENSOR_SAMPLE" if same_payload else "NO_PREVIOUS_SAMPLE",
            "qc": "PASS" if accum is not None else "MISSING",
            "provenance_url": VRAIN_CURRENT_URL,
            "raw_payload_hash": raw_hash,
        }

        # Only compare two distinct station payloads. Re-querying an unchanged
        # row must never create a fake 5/10-minute zero-rain observation.
        if prev and not same_payload and accum is not None:
            prev_start = prev.get("period_start")
            prev_end_dt = _parse_iso(prev.get("period_end") or prev.get("observed_at"))
            if prev_accum is not None and prev_start == period_start and prev_end_dt and source_reported_dt and source_reported_dt > prev_end_dt:
                minutes = (source_reported_dt - prev_end_dt).total_seconds() / 60.0
                delta = accum - prev_accum
                if delta >= -0.05 and minutes >= 5:
                    recent_change = round(max(0.0, delta), 3)
                    item["recent_change_mm"] = recent_change
                    item["recent_change_window_minutes"] = round(minutes, 1)
                    item["rain_recently_observed"] = recent_change > 0
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

    station_ages = [v.get("age_minutes") for v in stations.values() if _finite(v.get("age_minutes")) is not None]
    freshest_age = min(station_ages) if station_ages else None
    return {
        "status": "FRESH" if stations and freshest_age is not None and freshest_age <= 90 else ("STALE" if stations else "UNAVAILABLE"),
        "source": "VRAIN_PUBLIC",
        "period_start": period_start,
        "period_end": source_reported_at,
        "source_reported_at": source_reported_at,
        "fetched_at": checked_at,
        "stations": stations,
        "provenance_url": VRAIN_CURRENT_URL,
    }



def _operational_tier(source: dict) -> str:
    source_id = str(source.get("id") or "")
    if source_id in {"vvpq_metar_speci", "vrain_phu_quoc"}:
        return "ACTIVE_REALTIME"
    if source_id == "wmo_48917_synop":
        return "ACTIVE_NEAR_REALTIME"
    role = str(source.get("role") or "").upper()
    status = str(source.get("status") or "").upper()
    if any(x in role for x in {"HISTORICAL", "BACKTEST", "VERIFICATION", "CROSSCHECK", "REGIONAL_QA"}):
        return "VALIDATION_HISTORICAL"
    if any(x in status for x in {"PENDING", "UNRESOLVED", "NOT_ACQUIRED", "VALUES_NOT", "FEED_PENDING"}) or "CANDIDATE" in role or "EXTRACTION" in role or "REGISTRY_ONLY" in role:
        return "HOLD_CANDIDATE"
    if "RETIRED" in status:
        return "RETIRED"
    return "VALIDATION_HISTORICAL"


def _health_from_live_status(status: Any) -> str:
    state = str(status or "").upper()
    if state == "FRESH":
        return "HEALTHY"
    if state == "STALE":
        return "DEGRADED_STALE"
    if state in {"READY", "PASS"}:
        return "HEALTHY"
    return "UNAVAILABLE"


def _latest_rain_observation(rainfall: dict) -> tuple[str | None, float | None]:
    rows = []
    for station in (rainfall.get("stations") or {}).values():
        observed = station.get("observed_at")
        parsed = _parse_iso(observed)
        if parsed is not None:
            rows.append((parsed, observed, _finite(station.get("age_minutes"))))
    if not rows:
        return None, None
    _, observed, age = max(rows, key=lambda row: row[0])
    return observed, age


def _operational_source_registry(full_registry: dict, *, vvpq: dict, rainfall: dict,
                                 synop_48917: dict, corpus_full: dict) -> dict:
    """Attach operational role/health/freshness to every researched source.

    Static research identity is never discarded. Live sources receive dynamic
    observation health. Historical and candidate sources retain explicit
    non-live states so absence cannot be misread as calm/dry/no-lightning.
    """
    sources = []
    rain_last, rain_age = _latest_rain_observation(rainfall)
    generated_from = full_registry.get("generated_from") or (
        "WEATHER_GROUNDTRUTH_FINAL_HANDOFF_20260930 + REGISTRY_V5"
    )

    official_rows = [
        r for r in (corpus_full.get("records") or [])
        if str(r.get("source_class") or "").upper() == "OFFICIAL_AGGREGATE_OBS"
    ]
    official_last = None
    for row in official_rows:
        candidate = row.get("period_end_local") or row.get("obs_time_utc")
        parsed = _parse_iso(candidate)
        if parsed is not None and (official_last is None or parsed > official_last[0]):
            official_last = (parsed, candidate)

    for source in (full_registry.get("sources") or []):
        source_id = str(source.get("id") or "")
        tier = _operational_tier(source)
        entry = {
            **source,
            "tier": tier,
            "provenance": source.get("provenance") or {
                "registry": generated_from,
                "namespace": source.get("namespace"),
                "identifier": source.get("identifier"),
            },
            "freshness": {
                "state": "NOT_APPLICABLE",
                "age_minutes": None,
                "budget_minutes": None,
            },
            "health": "AVAILABLE_FOR_ROLE" if tier == "VALIDATION_HISTORICAL" else (
                "HOLD" if tier == "HOLD_CANDIDATE" else "UNKNOWN"
            ),
            "last_observation": None,
            "status_reason": source.get("notes") or str(source.get("status") or "NO_RUNTIME_OBSERVATION"),
        }

        if source_id == "vvpq_metar_speci":
            entry["health"] = _health_from_live_status(vvpq.get("status"))
            entry["last_observation"] = vvpq.get("observed_at")
            entry["freshness"] = {
                "state": vvpq.get("status") or "UNAVAILABLE",
                "age_minutes": _finite(vvpq.get("age_minutes")),
                "budget_minutes": 90,
            }
            entry["status_reason"] = (
                "Current METAR/SPECI observation is usable."
                if vvpq.get("status") == "FRESH"
                else "Current VVPQ feed is not fresh enough; do not infer local calm/dry conditions from its absence."
            )
            entry["provenance"] = {
                "feed": AWC_URL,
                "observation_channel": "METAR/SPECI",
                "registry": generated_from,
            }
        elif source_id == "vrain_phu_quoc":
            entry["health"] = _health_from_live_status(rainfall.get("status"))
            entry["last_observation"] = rain_last
            entry["freshness"] = {
                "state": rainfall.get("status") or "UNAVAILABLE",
                "age_minutes": rain_age,
                "budget_minutes": 90,
            }
            entry["status_reason"] = (
                "At least one gauge has a recent sensor observation."
                if rainfall.get("status") == "FRESH"
                else "No sufficiently fresh gauge sample; absence is not evidence of no rain."
            )
            entry["provenance"] = {
                "feed": VRAIN_CURRENT_URL,
                "timing_feed": VRAIN_TIME_URL,
                "registry": generated_from,
            }
        elif source_id == "wmo_48917_synop":
            entry["health"] = _health_from_live_status(synop_48917.get("status"))
            entry["last_observation"] = synop_48917.get("latest_observed_at")
            entry["freshness"] = {
                "state": synop_48917.get("status") or "UNAVAILABLE",
                "age_minutes": _finite(synop_48917.get("age_minutes")),
                "budget_minutes": 480,
            }
            entry["status_reason"] = (
                "Raw current SYNOP is available within the synoptic freshness budget."
                if synop_48917.get("status") == "FRESH"
                else "SYNOP is outside the near-real-time freshness budget or unavailable; keep historical verification but do not use as current evidence."
            )
            entry["provenance"] = {
                "feed": synop_48917.get("provenance_url"),
                "observation_channel": "WMO FM-12 SYNOP AAXX raw",
                "registry": generated_from,
            }
            entry["identity_status"] = synop_48917.get("identity_status") or source.get("identity_status")
            entry["identity_confidence"] = synop_48917.get("identity_confidence") or source.get("identity_confidence")
        elif source_id == "official_rainfall_reports" and official_last:
            entry["last_observation"] = official_last[1]
            entry["freshness"] = {
                "state": "HISTORICAL_WINDOWED_OBSERVATION",
                "age_minutes": None,
                "budget_minutes": None,
            }
            entry["status_reason"] = "Verified measured accumulation windows are retained for validation/backtest, never current weather."
        elif tier == "HOLD_CANDIDATE":
            entry["freshness"]["state"] = "NO_STABLE_RUNTIME_FEED"
            entry["status_reason"] = source.get("notes") or (
                "Source is retained in the registry but has no stable timestamped numeric feed eligible for runtime."
            )
        elif tier == "VALIDATION_HISTORICAL":
            entry["freshness"]["state"] = "HISTORICAL_NOT_CURRENT"
            entry["status_reason"] = source.get("notes") or (
                "Observation/archive source is retained for validation, backtest, drift or corroboration, not current Local Now."
            )

        sources.append(entry)

    return {
        "schema_version": "groundtruth-operational-registry-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(sources),
        "tiers": [
            "ACTIVE_REALTIME",
            "ACTIVE_NEAR_REALTIME",
            "VALIDATION_HISTORICAL",
            "HOLD_CANDIDATE",
            "RETIRED",
        ],
        "sources": sources,
        "policy": {
            "absence_is_negative_observation": False,
            "null_means_no_phenomenon": False,
            "live_actual_requires_timestamped_observation": True,
            "remote_observation_is_groundtruth": False,
        },
    }


def collect(previous: dict | None = None, artifacts: dict | None = None) -> dict:
    now = datetime.now(timezone.utc)
    errors: list[dict] = []
    artifacts = artifacts if artifacts is not None else {}

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

    # WMO 48917 is a current near-real-time observation stream independent from
    # current VVPQ at the station-program level. Identity was locked before Local
    # Now promotion; raw SYNOP remains separately archived and never deduplicated
    # with VVPQ merely because third-party metadata cross-links the identifiers.
    try:
        synop_raw = collect_synop(now - timedelta(days=2), now)
        artifacts["synop_raw"] = synop_raw
        synop_48917 = compact_synop_live(synop_raw, now)
    except Exception as exc:  # network boundary; VVPQ/VRain remain independent
        errors.append({"source": "WMO_48917_SYNOPTIC", "error": repr(exc)})
        synop_48917 = {
            "status": "UNAVAILABLE",
            "source_namespace": "WMO_INDEX",
            "identifier": "48917",
            "production_role": "ACTIVE_NEAR_REALTIME_GROUND_OBSERVATION",
            "detail": repr(exc),
        }

    # Research discovery is no longer left outside the application. The verified
    # corpus and the complete source registry travel with the production payload,
    # while each provenance class keeps its own allowed role.
    try:
        corpus_full = build_corpus(GROUNDTRUTH_SEED, GROUNDTRUTH_REGISTRY)
        artifacts["corpus_full"] = corpus_full
        full_registry = corpus_full.get("source_registry") or {"sources": []}
        corpus = {
            "schema_version": corpus_full.get("schema_version"),
            "record_count": corpus_full.get("record_count", 0),
            "counts_by_class": corpus_full.get("counts_by_class") or {},
            "counts_by_metric": corpus_full.get("counts_by_metric") or {},
            "policy": corpus_full.get("policy") or {},
            "canonical_path": "data/weather-groundtruth/corpus/verified-latest.json",
        }
        source_registry = _operational_source_registry(
            full_registry,
            vvpq=vvpq,
            rainfall=rainfall,
            synop_48917=synop_48917,
            corpus_full=corpus_full,
        )
        source_registry["canonical_path"] = "data/weather-groundtruth/corpus/source-registry.json"
    except Exception as exc:
        errors.append({"source": "GROUNDTRUTH_CORPUS", "error": repr(exc)})
        corpus_full = {
            "schema_version": "weather-groundtruth-corpus-v1",
            "record_count": 0,
            "records": [],
            "source_registry": {"sources": []},
        }
        corpus = {
            "schema_version": "weather-groundtruth-corpus-v1",
            "record_count": 0,
            "counts_by_class": {},
            "counts_by_metric": {},
            "policy": {},
            "canonical_path": "data/weather-groundtruth/corpus/verified-latest.json",
        }
        source_registry = {
            "schema_version": "groundtruth-source-registry-v2",
            "source_count": 0,
            "sources": [],
            "canonical_path": "data/weather-groundtruth/corpus/source-registry.json",
        }

    live_ready = (
        vvpq.get("status") in {"FRESH", "STALE"}
        or bool(rainfall.get("stations"))
        or synop_48917.get("status") in {"FRESH", "STALE"}
    )
    payload = {
        "schema_version": "2.0",
        "generated_at": now.isoformat(),
        "status": "READY" if live_ready else "UNAVAILABLE",
        "actual_policy": (
            "Current-time ACTUAL requires timestamped in-situ or raw coded observations. "
            "Historical aggregate/published observations are verification-only; remote sensing, "
            "models and fusion remain separate classes."
        ),
        "atmosphere": {"vvpq": vvpq, "synop_48917": synop_48917},
        "rainfall": rainfall,
        "historical_corpus": corpus,
        "source_registry": source_registry,
        "station_status": KNOWN_STATIONS,
        "errors": errors,
    }
    payload["payload_hash"] = _sha(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--corpus-output", type=Path)
    parser.add_argument("--synop-output", type=Path)
    args = parser.parse_args()

    previous = None
    if args.previous and args.previous.exists():
        try:
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    artifacts: dict = {}
    payload = collect(previous, artifacts=artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.corpus_output:
        corpus_payload = artifacts.get("corpus_full") or build_corpus(GROUNDTRUTH_SEED, GROUNDTRUTH_REGISTRY)
        args.corpus_output.parent.mkdir(parents=True, exist_ok=True)
        args.corpus_output.write_text(
            json.dumps(corpus_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.synop_output:
        synop_payload = artifacts.get("synop_raw") or {
            "schema_version": "weather-raw-synop-v3",
            "status": "UNAVAILABLE",
            "observations": [],
        }
        args.synop_output.parent.mkdir(parents=True, exist_ok=True)
        args.synop_output.write_text(
            json.dumps(synop_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "status": payload["status"],
        "generated_at": payload["generated_at"],
        "vvpq": payload["atmosphere"]["vvpq"].get("status"),
        "synop_48917": payload["atmosphere"]["synop_48917"].get("status"),
        "groundtruth_corpus_records": payload.get("historical_corpus", {}).get("record_count", 0),
        "rain_stations": list(payload["rainfall"].get("stations", {})),
        "rain_increment_ready": [
            k for k, v in payload["rainfall"].get("stations", {}).items()
            if v.get("increment_qc") == "PASS"
        ],
        "errors": payload["errors"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
