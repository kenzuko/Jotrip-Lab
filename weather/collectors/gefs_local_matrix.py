"""Lean NOAA GEFS local ensemble matrix for Phu Quoc.

Uses the official NOMADS GRIB Filter to subset a very small Phu Quoc box before
download. This keeps all 31 GEFS members while avoiding global-field downloads.

V1 atmospheric variables:
- TMP 2m
- UGRD/VGRD 10m
- APCP surface

Native ensemble output is 0.5 degree. We keep exact sampled grid coordinates
and never call it an observation.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from weather.collectors.live_smoke import _candidate_cycles
from weather.points import POINTS

ISLAND_POINT_IDS = tuple(point_id for point_id in POINTS if point_id != "rach_gia")
from weather.processing.ensemble import summarize_members
from weather.processing.ensemble_local import correct_distribution

FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_atmos_0p50a.pl"
LEADS = list(range(6, 73, 6))
MEMBERS = ["c00"] + [f"p{i:02d}" for i in range(1, 31)]
BOX = {"leftlon": 103.0, "rightlon": 104.75, "toplat": 11.0, "bottomlat": 9.0}
UA = "JoTrip-WeatherLab/1.0 NOAA-GEFS-local-ensemble"


def _file_member(member: str) -> str:
    return "gec00" if member == "c00" else "ge" + member


def _request_bytes(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = res.read()
    if not data.startswith(b"GRIB"):
        preview = data[:240].decode("utf-8", errors="replace")
        raise RuntimeError(f"NOMADS did not return GRIB: {preview}")
    return data


def _url(cycle: datetime, member: str, lead: int) -> str:
    stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    file_member = _file_member(member)
    filename = f"{file_member}.t{hour}z.pgrb2a.0p50.f{lead:03d}"
    query = {
        "file": filename,
        "lev_2_m_above_ground": "on",
        "lev_10_m_above_ground": "on",
        "lev_surface": "on",
        "var_TMP": "on",
        "var_UGRD": "on",
        "var_VGRD": "on",
        "var_APCP": "on",
        "subregion": "",
        **{k: str(v) for k, v in BOX.items()},
        "dir": f"/gefs.{stamp}/{hour}/atmos/pgrb2ap5",
    }
    return FILTER + "?" + urllib.parse.urlencode(query)


def _decode(path: Path, cycle: datetime, member: str) -> list[dict]:
    from eccodes import (
        codes_get,
        codes_grib_find_nearest,
        codes_grib_new_from_file,
        codes_release,
    )

    records: list[dict] = []
    with path.open("rb") as fh:
        while (gid := codes_grib_new_from_file(fh)) is not None:
            try:
                short = str(codes_get(gid, "shortName"))
                unit = str(codes_get(gid, "units"))
                end_step = int(codes_get(gid, "endStep"))
                try:
                    start_step = int(codes_get(gid, "startStep"))
                except Exception:
                    start_step = None
                valid = cycle + timedelta(hours=end_step)
                for point_id in ISLAND_POINT_IDS:
                    lat, lon = POINTS[point_id]
                    nearest = codes_grib_find_nearest(gid, lat, lon)[0]
                    value = float(nearest["value"])
                    if short == "2t" or short == "t":
                        if unit.lower() in {"k", "kelvin"} or value > 150:
                            value -= 273.15
                    records.append({
                        "source": "NOAA_GEFS_NOMADS_FILTER",
                        "model": "GEFS_0P50",
                        "run_time": cycle.isoformat(),
                        "member": member,
                        "lead_hours": end_step,
                        "period_start_lead": start_step,
                        "valid_time": valid.isoformat(),
                        "point_id": point_id,
                        "variable": short,
                        "value": value,
                        "unit": "degC" if short in {"2t", "t"} else unit,
                        "requested_lat": lat,
                        "requested_lon": lon,
                        "sampled_lat": float(nearest["lat"]),
                        "sampled_lon": float(nearest["lon"]),
                        "distance_km": float(nearest["distance"]),
                        "data_class": "FORECAST_ENSEMBLE_MEMBER",
                        "qc": "PASS",
                    })
            finally:
                codes_release(gid)
    return records


def _fetch_one(cycle: datetime, member: str, lead: int, work: Path) -> tuple[list[dict], dict]:
    url = _url(cycle, member, lead)
    last = None
    for attempt in range(3):
        try:
            payload = _request_bytes(url)
            target = work / f"{member}-{lead:03d}.grib2"
            target.write_bytes(payload)
            return _decode(target, cycle, member), {
                "member": member, "lead": lead, "status": "PASS",
                "bytes": len(payload), "attempt": attempt + 1,
            }
        except Exception as exc:
            last = exc
            time.sleep(0.35 * (attempt + 1))
    return [], {"member": member, "lead": lead, "status": "FAIL", "error": repr(last), "url": url}


def _canonical_variable(name: str) -> str | None:
    n = name.lower()
    if n in {"2t", "t", "tmp"}:
        return "temperature"
    if n in {"10u", "u", "ugrd"}:
        return "u10"
    if n in {"10v", "v", "vgrd"}:
        return "v10"
    if n in {"tp", "apcp"}:
        return "rain"
    return None


def _member_vectors(records: list[dict]) -> dict:
    buckets: dict[tuple[str, str, int, str], dict[str, dict]] = {}
    for r in records:
        var = _canonical_variable(str(r.get("variable")))
        if not var:
            continue
        key = (str(r["point_id"]), str(r["member"]), int(r["lead_hours"]), str(r["valid_time"]))
        buckets.setdefault(key, {})[var] = r

    out: dict[str, dict] = {}
    for (point, member, lead, valid), b in buckets.items():
        k = f"{point}|{lead}|{valid}"
        item = out.setdefault(k, {"point_id": point, "lead_hours": lead, "valid_time": valid, "members": {}})
        m = item["members"].setdefault(member, {})
        if "temperature" in b:
            m["temperature_c"] = float(b["temperature"]["value"])
        if "u10" in b and "v10" in b:
            u = float(b["u10"]["value"])
            v = float(b["v10"]["value"])
            m["wind_kmh"] = math.hypot(u, v) * 3.6
            m["u10_ms"] = u
            m["v10_ms"] = v
        if "rain" in b:
            rain = max(0.0, float(b["rain"]["value"]))
            m["rain_mm"] = rain
            m["rain_period_start_lead"] = b["rain"].get("period_start_lead")
        sample = next(iter(b.values()))
        m["sampled_lat"] = sample["sampled_lat"]
        m["sampled_lon"] = sample["sampled_lon"]
        m["distance_km"] = sample["distance_km"]
    return out


def _learning_calibration(variable: str) -> dict:
    if variable == "rain":
        return {
            "engine": "PQ_ENSEMBLE_LOCAL_V1", "status": "LEARNING",
            "sample_count": 0, "minimum_samples": 30, "applied_factor": 1.0,
            "method": "SHRUNK_MEDIAN_LOG_RATIO",
        }
    return {
        "engine": "PQ_ENSEMBLE_LOCAL_V1", "status": "LEARNING",
        "sample_count": 0, "minimum_samples": 30, "applied_bias": 0.0,
        "method": "SHRUNK_MEDIAN_ADDITIVE_BIAS",
    }


def _summaries(vectors: dict) -> dict:
    points: dict[str, list[dict]] = {point_id: [] for point_id in ISLAND_POINT_IDS}
    for item in sorted(vectors.values(), key=lambda x: (x["point_id"], x["lead_hours"])):
        members = item["members"]
        row = {
            "lead_hours": item["lead_hours"],
            "valid_time": item["valid_time"],
            "member_count": len(members),
            "expected_members": 31,
            "variables": {},
        }
        for variable, member_key, threshold in (
            ("temperature", "temperature_c", None),
            ("wind", "wind_kmh", 30.0),
            ("rain", "rain_mm", 5.0),
        ):
            values = [m[member_key] for m in members.values() if member_key in m]
            calibration = _learning_calibration(variable)
            dist = correct_distribution(values, calibration, variable=variable, threshold=threshold)
            dist["raw"]["completion_ratio"] = round(len(values) / 31, 3)
            dist["corrected"]["completion_ratio"] = round(len(values) / 31, 3)
            row["variables"][variable] = dist
        points[item["point_id"]].append(row)
    return points


def collect(output: Path | None = None, *, members: list[str] | None = None,
            leads: list[int] | None = None, max_workers: int = 3) -> dict:
    members = members or MEMBERS
    leads = leads or LEADS
    attempts: list[dict] = []

    # Resolve a usable cycle with one tiny request before fan-out.
    cycle = None
    with tempfile.TemporaryDirectory(prefix="jotrip-gefs-local-") as tmp:
        work = Path(tmp)
        probe_member = members[0]
        probe_lead = leads[0]
        for candidate in _candidate_cycles(days=3):
            recs, meta = _fetch_one(candidate, probe_member, probe_lead, work)
            attempts.append({"cycle_probe": candidate.isoformat(), **meta})
            if recs:
                cycle = candidate
                break
        if cycle is None:
            result = {"status": "UNAVAILABLE", "readiness": "UNAVAILABLE", "attempts": attempts}
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return result

        all_records: list[dict] = []
        completed: set[tuple[str, int]] = set()
        # Reuse the successful probe.
        recs, meta = _fetch_one(cycle, probe_member, probe_lead, work)
        if recs:
            all_records.extend(recs)
            completed.add((probe_member, probe_lead))

        tasks = [(m, lead) for m in members for lead in leads if (m, lead) not in completed]
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 4))) as pool:
            futures = {pool.submit(_fetch_one, cycle, m, lead, work): (m, lead) for m, lead in tasks}
            for fut in as_completed(futures):
                recs, meta = fut.result()
                attempts.append(meta)
                if recs:
                    all_records.extend(recs)
                    completed.add(futures[fut])

    expected_files = len(members) * len(leads)
    completion = len(completed) / expected_files if expected_files else 0.0
    vectors = _member_vectors(all_records)
    result = {
        "schema_version": "1.0",
        "status": "MEMBER_MATRIX_READY" if completion >= 0.9 else "PARTIAL_ENSEMBLE",
        "readiness": "MEMBER_MATRIX_READY" if completion >= 0.9 else ("PARTIAL_ENSEMBLE" if all_records else "UNAVAILABLE"),
        "source": "NOAA_NOMADS_GEFS_GRIB_FILTER",
        "model": "GEFS_0P50",
        "run_time": cycle.isoformat(),
        "horizon_hours": max(leads),
        "step_hours": sorted(leads),
        "members": members,
        "expected_member_step_files": expected_files,
        "completed_member_step_files": len(completed),
        "completion_ratio": round(completion, 4),
        "box": BOX,
        "points": _summaries(vectors),
        "calibration_engine": "PQ_ENSEMBLE_LOCAL_V1",
        "calibration_status": "LEARNING",
        "calibration_note": "Raw member distributions are preserved until >=30 matched ACTUAL verification cases exist for the relevant point/variable/lead/regime.",
        "raw_member_records": len(all_records),
        "attempts": [a for a in attempts if a.get("status") == "FAIL"][-80:],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--members", type=int, default=31)
    p.add_argument("--lead", type=int, action="append")
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()
    selected = MEMBERS[:max(1, min(31, args.members))]
    result = collect(args.output, members=selected, leads=args.lead or LEADS, max_workers=args.workers)
    print(json.dumps({
        "status": result.get("status"),
        "run_time": result.get("run_time"),
        "completion_ratio": result.get("completion_ratio"),
        "horizon_hours": result.get("horizon_hours"),
        "rows": {k: len(v) for k, v in result.get("points", {}).items()},
    }, ensure_ascii=False, indent=2))
