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


def compact_live(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = payload.get("observations") or []
    latest = rows[-1] if rows else None
    age = None
    if latest:
        try:
            t = datetime.fromisoformat(str(latest["observed_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            age = max(0.0, (now - t).total_seconds() / 60.0)
        except Exception:
            age = None
    status = "UNAVAILABLE" if not latest else ("FRESH" if age is not None and age <= 480 else "STALE")
    return {
        "status": status,
        "source": payload.get("source"),
        "source_namespace": payload.get("source_namespace"),
        "identifier": payload.get("identifier"),
        "station_name": payload.get("station_name"),
        "reference_lat": payload.get("reference_lat"),
        "reference_lon": payload.get("reference_lon"),
        "station_epoch": payload.get("station_epoch"),
        "identity_policy": payload.get("identity_policy"),
        "provenance_url": payload.get("provenance_url"),
        "checked_at": payload.get("generated_at"),
        "latest_observed_at": latest.get("observed_at") if latest else None,
        "age_minutes": round(age, 1) if age is not None else None,
        "latest": latest,
        "recent_observations": rows[-8:],
        "recent_count": len(rows),
        "production_role": "ACTIVE_NEAR_REALTIME_GROUND_OBSERVATION",
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
