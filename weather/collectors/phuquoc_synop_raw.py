"""Fetch recent raw SYNOP observations for Phu Quoc WMO 48917.

This stream is kept separate from ICAO VVPQ and KTT station-book identifiers.
Raw reports are preserved before a narrow tested decoder is applied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from weather.processing.synop_actual import decode_synop_actual

STATION_ID = "48917"
SOURCE = "OGIMET_GETSYNOP"
ENDPOINTS = (
    "https://www.ogimet.com/cgi-bin/getsynop",
    "http://www.ogimet.com/cgi-bin/getsynop",
)
USER_AGENT = "JoTrip-WeatherLab/2.0 raw-SYNOP-groundtruth"
IDENTITY_RESOLUTION = {
    "resolution_id": "WMO_INDEX:48917:CURRENT_2026_DUONG_DONG:v1",
    "status": "LOCKED",
    "effective_at": "2026-10-01T06:35:33+00:00",
    "decision": "INDEPENDENT_FROM_CURRENT_VVPQ",
    "confidence": "HIGH",
    "supersedes_legacy_ingest_assessments": [
        "IDENTITY_PENDING_POST_2012",
        "CONFLICTING_OPERATIONAL_AND_CLIMATE_METADATA",
        "UNRESOLVED_DO_NOT_COUNT_AS_INDEPENDENT_EVIDENCE",
    ],
    "evidence": [
        "JMA/TCC current 2026 metadata: WMO 48917 PHU QUOC near 10.22N,103.97E",
        "Vietnam KTTV BHV1/SHV1 station book: Hai van Phu Quoc uses station code 48917",
        "Vietnam KTTV automated station list: Phu Quoc automated station is separately identified as 60018",
        "Current VVPQ AIP coordinates are near 10.169722N,103.993056E",
        "Same-timestamp 48917 SYNOP and VVPQ METAR coexist with distinct values; 48917 also carries SYNOP Section 222 marine groups",
    ],
    "raw_archive_semantics": (
        "Immutable raw files preserve the identity assessment present when that observation was first archived. "
        "Runtime identity is governed by this current versioned resolution; older embedded identity annotations "
        "are provenance history and do not override the current gate."
    ),
}
STREAM_IDENTITY = {
    "source_namespace": "WMO_INDEX",
    "identifier": "48917",
    "station_name": "PHU QUOC",
    "reference_lat": 10.22,
    "reference_lon": 103.97,
    "coordinate_precision": "STATION_METADATA_APPROX_0_01_DEG",
    "location_context": "DUONG_DONG_AREA",
    "station_epoch": "CURRENT_2026_METADATA_DUONG_DONG",
    "physical_identity": "PHU_QUOC_MARINE_SYNOPTIC_OBSERVATION_PROGRAM",
    "identity_status": "INDEPENDENT_FROM_CURRENT_VVPQ",
    "identity_confidence": "HIGH",
    "identity_resolution_id": IDENTITY_RESOLUTION["resolution_id"],
    "identity_policy": "Independent from current ICAO:VVPQ for operational evidence. Never merge with ICAO:VVPQ, KTT_BOOK_STATION_CODE:48917 or KTTV_AUTO:60018 solely by identifier/cross-id.",
    "relocation_status": "NO_VERIFIED_POST_2012_RELOCATION_FOUND",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def _fetch_csv(begin: datetime, end: datetime) -> tuple[str, str]:
    params = urllib.parse.urlencode({
        "block": STATION_ID,
        "begin": begin.strftime("%Y%m%d%H%M"),
        "end": end.strftime("%Y%m%d%H%M"),
        "lang": "eng",
        "header": "yes",
    })
    errors: list[str] = []
    for endpoint in ENDPOINTS:
        url = f"{endpoint}?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,text/plain,*/*;q=0.5",
        })
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                body = res.read().decode("utf-8", errors="replace")
            if body.strip():
                return url, body
            errors.append(f"{url}: empty response")
        except Exception as exc:
            errors.append(f"{url}: {exc!r}")
    raise RuntimeError("; ".join(errors))


def _parse_rows(raw_csv: str) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(raw_csv))
    rows: list[dict[str, Any]] = []
    for fields in reader:
        if not fields:
            continue
        if fields[0].strip().upper() in {"WMOIND", "STATION", "ESTACION"}:
            continue
        if len(fields) < 7 or fields[0].strip() != STATION_ID:
            continue
        year, month, day, hour, minute = [x.strip() for x in fields[1:6]]
        try:
            obs = datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=timezone.utc)
        except ValueError:
            continue
        report = ",".join(fields[6:]).strip()
        if not report:
            continue
        rows.append({
            **STREAM_IDENTITY,
            "source": SOURCE,
            "source_channel": "SYNOP_AAXX_RAW",
            "data_class": "ACTUAL",
            "observation_class": "RAW_OBS",
            "observed_at": obs.isoformat(),
            "raw_observation": report,
            "raw_payload_hash": _sha256(report),
            "decoded_actual": decode_synop_actual(report),
            "qc": "PASS_RAW_WITH_TESTED_SUBSET_DECODE",
        })
    rows.sort(key=lambda row: row["observed_at"])
    return rows


def collect(begin: datetime, end: datetime) -> dict[str, Any]:
    if end < begin:
        raise ValueError("end must be >= begin")
    if end - begin > timedelta(days=31):
        raise ValueError("one request is limited to 31 days")
    provenance_url, raw_csv = _fetch_csv(begin, end)
    rows = _parse_rows(raw_csv)
    return {
        "schema_version": "weather-raw-synop-v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **STREAM_IDENTITY,
        "identity_resolution": IDENTITY_RESOLUTION,
        "source": SOURCE,
        "data_class": "ACTUAL",
        "observation_class": "RAW_OBS",
        "begin": begin.isoformat(),
        "end": end.isoformat(),
        "provenance_url": provenance_url,
        "raw_response_hash": _sha256(raw_csv),
        "count": len(rows),
        "observations": rows,
    }


def _has_runtime_numeric(row: dict[str, Any]) -> bool:
    decoded = row.get("decoded_actual") or {}
    wind = decoded.get("wind") or {}
    return any(
        value is not None
        for value in (
            wind.get("speed_kmh"),
            decoded.get("air_temperature_c"),
            decoded.get("dewpoint_c"),
            decoded.get("station_pressure_hpa"),
            decoded.get("sea_level_pressure_hpa"),
        )
    )


def compact_live(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = payload.get("observations") or []
    latest = rows[-1] if rows else None
    numeric_rows = [row for row in rows if _has_runtime_numeric(row)]
    latest_numeric = numeric_rows[-1] if numeric_rows else None

    def age_minutes(row: dict[str, Any] | None) -> float | None:
        if not row:
            return None
        try:
            t = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            return max(0.0, (now - t).total_seconds() / 60.0)
        except Exception:
            return None

    feed_age = age_minutes(latest)
    numeric_age = age_minutes(latest_numeric)
    status = "UNAVAILABLE" if not latest else ("FRESH" if feed_age is not None and feed_age <= 480 else "STALE")
    numeric_status = (
        "UNAVAILABLE" if not latest_numeric
        else ("FRESH" if numeric_age is not None and numeric_age <= 480 else "STALE")
    )
    resolution = payload.get("identity_resolution") or {}
    identity_locked = (
        resolution.get("status") == "LOCKED"
        and resolution.get("decision") == "INDEPENDENT_FROM_CURRENT_VVPQ"
        and resolution.get("resolution_id") == payload.get("identity_resolution_id")
    )
    return {
        "status": status,
        "numeric_status": numeric_status,
        "source": payload.get("source"),
        "source_namespace": payload.get("source_namespace"),
        "identifier": payload.get("identifier"),
        "station_name": payload.get("station_name"),
        "reference_lat": payload.get("reference_lat"),
        "reference_lon": payload.get("reference_lon"),
        "coordinate_precision": payload.get("coordinate_precision"),
        "location_context": payload.get("location_context"),
        "station_epoch": payload.get("station_epoch"),
        "physical_identity": payload.get("physical_identity"),
        "identity_status": payload.get("identity_status"),
        "identity_confidence": payload.get("identity_confidence"),
        "identity_policy": payload.get("identity_policy"),
        "identity_resolution_id": payload.get("identity_resolution_id"),
        "identity_resolution": resolution,
        "relocation_status": payload.get("relocation_status"),
        "provenance_url": payload.get("provenance_url"),
        "checked_at": payload.get("generated_at"),
        "latest_observed_at": latest.get("observed_at") if latest else None,
        "age_minutes": round(feed_age, 1) if feed_age is not None else None,
        "latest_numeric_observed_at": latest_numeric.get("observed_at") if latest_numeric else None,
        "numeric_age_minutes": round(numeric_age, 1) if numeric_age is not None else None,
        "latest": latest,
        "latest_numeric": latest_numeric,
        "recent_observations": rows[-8:],
        "recent_count": len(rows),
        "production_role": "ACTIVE_NEAR_REALTIME_GROUND_OBSERVATION",
        "runtime_eligible": bool(numeric_status == "FRESH" and identity_locked),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--begin", help="UTC YYYYMMDDHHmm")
    parser.add_argument("--end", help="UTC YYYYMMDDHHmm")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = _parse_utc(args.end) if args.end else now
    begin = _parse_utc(args.begin) if args.begin else end - timedelta(days=args.days)
    payload = collect(begin, end)
    payload["live"] = compact_live(payload, now)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["live"]["status"],
        "count": payload["count"],
        "latest_observed_at": payload["live"]["latest_observed_at"],
        "age_minutes": payload["live"]["age_minutes"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
