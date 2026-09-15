"""Live numeric smoke tests for direct international model sources.

This module downloads the smallest practical GRIB payload from each source and
decodes at least one numeric field. It is deliberately separate from the fast
HTTP health probe: HTTP 200 alone is not evidence that a source is usable by
the numerical engine.
"""
from __future__ import annotations

import argparse
import bz2
import json
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PHU_QUOC_LAT = 10.0191
PHU_QUOC_LON = 104.0150
USER_AGENT = "JoTrip-Lab/1.0 direct-model-smoke"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(url: str, *, byte_range: tuple[int, int] | None = None, timeout: int = 30) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if byte_range:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _candidate_cycles(days: int = 3):
    now = datetime.now(timezone.utc)
    for offset in range(days):
        day = (now - timedelta(days=offset)).date()
        for hour in (18, 12, 6, 0):
            cycle = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
            if cycle <= now - timedelta(hours=4):
                yield cycle


def _decode_grib(path: Path, *, nearest: bool = True) -> dict:
    try:
        from eccodes import (
            codes_get,
            codes_grib_find_nearest,
            codes_grib_new_from_file,
            codes_release,
        )
    except ImportError as exc:
        raise RuntimeError("eccodes Python package is required for numeric smoke tests") from exc

    with path.open("rb") as stream:
        gid = codes_grib_new_from_file(stream)
        if gid is None:
            raise RuntimeError("No GRIB message decoded")
        try:
            raw_step = codes_get(gid, "endStep")
            try:
                normalized_step = int(raw_step)
            except (TypeError, ValueError):
                normalized_step = str(raw_step)
            decoded = {
                "short_name": codes_get(gid, "shortName"),
                "units": codes_get(gid, "units"),
                "data_date": int(codes_get(gid, "dataDate")),
                "data_time": int(codes_get(gid, "dataTime")),
                "step": normalized_step,
                "grid_type": codes_get(gid, "gridType"),
                "number_of_points": int(codes_get(gid, "numberOfPoints")),
                "minimum": float(codes_get(gid, "minimum")),
                "maximum": float(codes_get(gid, "maximum")),
            }
            if nearest:
                point = codes_grib_find_nearest(gid, PHU_QUOC_LAT, PHU_QUOC_LON)[0]
                decoded["phu_quoc_point"] = {
                    "lat": float(point["lat"]),
                    "lon": float(point["lon"]),
                    "value": float(point["value"]),
                    "distance_km": float(point["distance"]),
                }
            return decoded
        finally:
            codes_release(gid)


def smoke_ecmwf(workdir: Path) -> dict:
    from ecmwf.opendata import Client

    attempts = []
    for source in ("ecmwf", "aws", "google"):
        target = workdir / f"ecmwf-{source}.grib2"
        try:
            client = Client(source=source, maximum_retries=2, retry_after=2)
            result = client.retrieve(type="fc", stream="oper", step=0, param="10u", target=str(target))
            decoded = _decode_grib(target)
            return {
                "status": "NUMERIC_READY",
                "selected_endpoint": source,
                "fallback_level": len(attempts),
                "run_time": result.datetime.isoformat(),
                "decoded": decoded,
                "attempts": attempts,
                "checked_at": _utcnow(),
            }
        except Exception as exc:  # source failover must include decode errors
            attempts.append({"endpoint": source, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "RETRIEVAL_FAILED", "attempts": attempts, "checked_at": _utcnow()}


def _indexed_grib(url: str, idx_url: str, matcher: str, target: Path) -> dict:
    index = _request(idx_url).decode("utf-8", errors="replace").splitlines()
    records = []
    for line in index:
        parts = line.split(":")
        if len(parts) >= 5 and parts[1].isdigit():
            records.append((int(parts[1]), line))
    for position, (start, line) in enumerate(records):
        if matcher.lower() not in line.lower():
            continue
        end = records[position + 1][0] - 1 if position + 1 < len(records) else start + 8_000_000
        payload = _request(url, byte_range=(start, end))
        if not payload.startswith(b"GRIB") or not payload.rstrip().endswith(b"7777"):
            raise RuntimeError(f"Incomplete GRIB message for {matcher}")
        target.write_bytes(payload)
        return {"index_record": line, "bytes": len(payload), "decoded": _decode_grib(target)}
    raise RuntimeError(f"Variable not found in index: {matcher}")


def smoke_noaa_atmos(workdir: Path) -> dict:
    attempts = []
    roots = (
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod",
        "https://noaa-gefs-pds.s3.amazonaws.com",
    )
    for cycle in _candidate_cycles():
        stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        key = f"gefs.{stamp}/{hour}/atmos/pgrb2ap5/gec00.t{hour}z.pgrb2a.0p50.f003"
        for level, root in enumerate(roots):
            url = f"{root}/{key}"
            try:
                result = _indexed_grib(url, f"{url}.idx", "UGRD:10 m above ground", workdir / "gefs-atmos.grib2")
                return {"status": "NUMERIC_READY", "selected_endpoint": root, "fallback_level": level,
                        "run_time": cycle.isoformat(), **result, "attempts": attempts, "checked_at": _utcnow()}
            except Exception as exc:
                attempts.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "RETRIEVAL_FAILED", "attempts": attempts, "checked_at": _utcnow()}


def smoke_noaa_wave(workdir: Path) -> dict:
    attempts = []
    roots = (
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod",
        "https://noaa-gefs-pds.s3.amazonaws.com",
    )
    for cycle in _candidate_cycles():
        stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        key = f"gefs.{stamp}/{hour}/wave/gridded/gefs.wave.t{hour}z.c00.global.0p25.f003.grib2"
        for level, root in enumerate(roots):
            url = f"{root}/{key}"
            try:
                result = _indexed_grib(url, f"{url}.idx", "HTSGW:surface", workdir / "gefs-wave.grib2")
                return {"status": "NUMERIC_READY", "selected_endpoint": root, "fallback_level": level,
                        "run_time": cycle.isoformat(), **result, "attempts": attempts, "checked_at": _utcnow()}
            except Exception as exc:
                attempts.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "RETRIEVAL_FAILED", "attempts": attempts, "checked_at": _utcnow()}


def smoke_dwd(workdir: Path) -> dict:
    attempts = []
    root = "https://opendata.dwd.de/weather/nwp/icon/grib"
    for hour in (0, 6, 12, 18):
        directory = f"{root}/{hour:02d}/u_10m/"
        try:
            html = _request(directory).decode("utf-8", errors="replace")
            names = re.findall(r'href="([^"]+_000_U_10M\.grib2\.bz2)"', html, flags=re.I)
            if not names:
                raise RuntimeError("No step-000 U_10M object in directory")
            name = sorted(set(names))[-1]
            compressed = _request(directory + name, timeout=60)
            payload = bz2.decompress(compressed)
            if not payload.startswith(b"GRIB"):
                raise RuntimeError("DWD payload is not GRIB")
            target = workdir / "icon-u10.grib2"
            target.write_bytes(payload)
            # ICON global uses an unstructured grid. Decode the actual numeric
            # field here; point extraction is gated until the official grid
            # coordinate file is joined by cell index.
            decoded = _decode_grib(target, nearest=False)
            return {"status": "FIELD_NUMERIC_READY_POINT_PENDING", "selected_endpoint": "dwd",
                    "object": directory + name, "compressed_bytes": len(compressed),
                    "decoded_bytes": len(payload), "decoded": decoded, "attempts": attempts,
                    "checked_at": _utcnow()}
        except Exception as exc:
            attempts.append({"url": directory, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "RETRIEVAL_FAILED", "attempts": attempts, "checked_at": _utcnow()}


def run_smoke(output: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="jotrip-weather-") as temp:
        workdir = Path(temp)
        result = {
            "ECMWF_DIRECT": smoke_ecmwf(workdir),
            "NOAA_GEFS_DIRECT": smoke_noaa_atmos(workdir),
            "NOAA_GEFS_WAVE_DIRECT": smoke_noaa_wave(workdir),
            "DWD_ICON_DIRECT": smoke_dwd(workdir),
            "COPERNICUS_MARINE_DIRECT": {
                "status": "AUTH_REQUIRED",
                "reason": "Free Copernicus Marine account credentials are not configured",
                "checked_at": _utcnow(),
            },
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_smoke(args.output), ensure_ascii=False, indent=2))
