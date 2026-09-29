"""Fetch raw SYNOP observations for Phu Quoc WMO 48917.

Raw station reports are archived verbatim first. A narrow tested decoder then
attaches measured wind and precipitation accumulation groups while retaining
the original SYNOP groups for auditability. No model, fusion, interpolation,
or spatial estimate is introduced.

Source: OGIMET getsynop public CSV endpoint.
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
USER_AGENT = "JoTrip-WeatherLab/1.0 raw-SYNOP-groundtruth"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def _fetch_csv(begin: datetime, end: datetime) -> tuple[str, str]:
    params = urllib.parse.urlencode(
        {
            "block": STATION_ID,
            "begin": begin.strftime("%Y%m%d%H%M"),
            "end": end.strftime("%Y%m%d%H%M"),
            "lang": "eng",
            "header": "yes",
        }
    )
    errors: list[str] = []
    for endpoint in ENDPOINTS:
        url = f"{endpoint}?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/csv,text/plain,*/*;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
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
        if len(fields) < 7:
            continue

        station = fields[0].strip()
        if station != STATION_ID:
            # getsynop block is a prefix match; never ingest neighbouring stations.
            continue

        year, month, day, hour, minute = [x.strip() for x in fields[1:6]]
        try:
            obs = datetime(
                int(year), int(month), int(day), int(hour), int(minute), tzinfo=timezone.utc
            )
        except ValueError:
            continue

        report = ",".join(fields[6:]).strip()
        if not report:
            continue

        decoded = decode_synop_actual(report)
        rows.append(
            {
                "station_id": STATION_ID,
                "station_name": "Phu Quoc",
                "source": SOURCE,
                "source_channel": "SYNOP_AAXX_RAW",
                "data_class": "ACTUAL",
                "observation_class": "RAW_OBS",
                "observed_at": obs.isoformat(),
                "raw_observation": report,
                "raw_payload_hash": _sha256(report),
                "decoded_actual": decoded,
                "qc": "PASS_RAW_WITH_TESTED_SUBSET_DECODE",
            }
        )

    rows.sort(key=lambda row: row["observed_at"])
    return rows


def collect(begin: datetime, end: datetime) -> dict[str, Any]:
    if end < begin:
        raise ValueError("end must be >= begin")
    if end - begin > timedelta(days=31):
        raise ValueError("one request is limited to 31 days; backfill in chunks")

    provenance_url, raw_csv = _fetch_csv(begin, end)
    rows = _parse_rows(raw_csv)

    return {
        "schema_version": "weather-raw-synop-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "station_id": STATION_ID,
        "station_name": "Phu Quoc",
        "source": SOURCE,
        "data_class": "ACTUAL",
        "observation_class": "RAW_OBS",
        "begin": begin.isoformat(),
        "end": end.isoformat(),
        "provenance_url": provenance_url,
        "raw_response_hash": _sha256(raw_csv),
        "count": len(rows),
        "observations": rows,
        "policy": (
            "Raw station observations are archived verbatim. Only tested WMO SYNOP "
            "wind and precipitation groups are decoded. No model, fusion, interpolation, "
            "or spatial estimate is introduced."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--begin", help="UTC YYYYMMDDHHmm")
    parser.add_argument("--end", help="UTC YYYYMMDDHHmm")
    parser.add_argument("--days", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = _parse_utc(args.end) if args.end else now
    begin = _parse_utc(args.begin) if args.begin else end - timedelta(days=args.days)

    payload = collect(begin, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "station_id": payload["station_id"],
                "begin": payload["begin"],
                "end": payload["end"],
                "count": payload["count"],
                "provenance_url": payload["provenance_url"],
                "first_observed_at": payload["observations"][0]["observed_at"]
                if payload["observations"]
                else None,
                "last_observed_at": payload["observations"][-1]["observed_at"]
                if payload["observations"]
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
