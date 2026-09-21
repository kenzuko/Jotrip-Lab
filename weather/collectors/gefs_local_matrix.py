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
import statistics
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
VERIFICATION_TARGETS = {
    "vvpq": (10.169, 103.995),
    "vrain_cua_can": (10.292693, 103.914799),
    "vrain_bai_thom": (10.411765, 104.031055),
    "vrain_an_thoi": (10.018482, 104.0149),
}
CALIBRATION_ANCHORS = {
    "duong_dong": {"temperature": "vvpq", "wind": "vvpq"},
    "cua_can": {"rain": "vrain_cua_can"},
    "bai_thom": {"rain": "vrain_bai_thom"},
    "an_thoi": {"rain": "vrain_an_thoi"},
}
from weather.processing.ensemble import summarize_members
from weather.processing.ensemble_local import correct_distribution

FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_atmos_0p50a.pl"
LEADS = list(range(6, 241, 6))
MEMBERS = ["c00"] + [f"p{i:02d}" for i in range(1, 31)]
BOX = {"leftlon": 103.0, "rightlon": 104.75, "toplat": 11.0, "bottomlat": 9.0}
NATIVE_GRID_DEG = 0.5

# V5 spatial field keeps the model grid instead of throwing it away after
# extracting the seven operational anchors. These requests intentionally align
# to the native GEFS 0.5° grid. Display interpolation belongs to the renderer
# and must never be described as higher model resolution.
SPATIAL_GRID_REQUESTS = tuple(
    (round(lat, 2), round(lon, 2))
    for lat in (9.0, 9.5, 10.0, 10.5, 11.0)
    for lon in (103.0, 103.5, 104.0, 104.5)
)
UA = "JoTrip-WeatherLab/1.0 NOAA-GEFS-local-ensemble"

# V1 physical exposure layer. This is deliberately separate from statistical
# calibration: raw GEFS grid wind is preserved, while the public corrected
# distribution may apply a transparent local shielding factor by wind direction.
# Bãi Sao is on the east/southeast coast and is materially sheltered from
# prevailing W-SW flow by Phú Quốc's land mass. Other points remain neutral
# until their directional exposure tables are field-audited.
WIND_EXPOSURE_ENGINE = "PQ_LOCAL_WIND_EXPOSURE_V1"
WIND_EXPOSURE_8 = {
    "bai_sao": {
        "N": 0.90, "NE": 1.00, "E": 1.00, "SE": 0.95,
        "S": 0.82, "SW": 0.62, "W": 0.58, "NW": 0.72,
    },
}
WIND_SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _wind_from_direction_deg(u_ms: float, v_ms: float) -> float:
    """Meteorological direction wind comes FROM, degrees clockwise from north."""
    return (math.degrees(math.atan2(-u_ms, -v_ms)) + 360.0) % 360.0


def _wind_sector(direction_deg: float) -> str:
    return WIND_SECTORS[int((direction_deg + 22.5) // 45.0) % 8]


def _wind_exposure_factor(point_id: str, direction_deg: float) -> float:
    table = WIND_EXPOSURE_8.get(point_id)
    if not table:
        return 1.0
    return float(table.get(_wind_sector(direction_deg), 1.0))


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


def _grid_id(lat: float, lon: float) -> str:
    return f"grid_{lat:.2f}_{lon:.2f}"


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
                targets = [
                    (point_id, POINTS[point_id][0], POINTS[point_id][1], "OPERATIONAL_ANCHOR")
                    for point_id in ISLAND_POINT_IDS
                ] + [
                    (point_id, lat, lon, "VERIFICATION_ANCHOR")
                    for point_id, (lat, lon) in VERIFICATION_TARGETS.items()
                ] + [
                    (_grid_id(lat, lon), lat, lon, "SPATIAL_GRID")
                    for lat, lon in SPATIAL_GRID_REQUESTS
                ]
                for point_id, lat, lon, sample_kind in targets:
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
                        "sample_kind": sample_kind,
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
            wind_kmh = math.hypot(u, v) * 3.6
            direction_deg = _wind_from_direction_deg(u, v)
            exposure_factor = _wind_exposure_factor(point, direction_deg)
            m["wind_kmh"] = wind_kmh
            m["wind_local_kmh"] = wind_kmh * exposure_factor
            m["wind_direction_deg"] = direction_deg
            m["wind_exposure_factor"] = exposure_factor
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


def _lead_bucket(lead_hours: int) -> str | None:
    for name, lo, hi in (
        ("D0_24", 0, 24),
        ("D1_48", 25, 48),
        ("D2_72", 49, 72),
        ("D3_5", 73, 120),
        ("D6_10", 121, 240),
    ):
        if lo <= int(lead_hours) <= hi:
            return name
    return None


def _calibration_for(bundle: dict | None, point_id: str, variable: str, lead_hours: int) -> dict:
    target = (CALIBRATION_ANCHORS.get(point_id) or {}).get(variable)
    bucket = _lead_bucket(lead_hours)
    if not bundle or not target or not bucket:
        return _learning_calibration(variable)
    cal = ((((bundle.get("targets") or {}).get(target) or {}).get(variable) or {}).get(bucket))
    return cal if isinstance(cal, dict) else _learning_calibration(variable)


def _verification_summaries(vectors: dict) -> dict:
    points: dict[str, list[dict]] = {point_id: [] for point_id in VERIFICATION_TARGETS}
    for item in sorted(vectors.values(), key=lambda x: (x["point_id"], x["lead_hours"])):
        point_id = item["point_id"]
        if point_id not in points:
            continue
        members = item["members"]
        temp = [m["temperature_c"] for m in members.values() if "temperature_c" in m]
        wind = [m["wind_kmh"] for m in members.values() if "wind_kmh" in m]
        rain = [m["rain_mm"] for m in members.values() if "rain_mm" in m]
        starts = [m.get("rain_period_start_lead") for m in members.values() if m.get("rain_period_start_lead") is not None]
        sample = next(iter(members.values()), {})
        points[point_id].append({
            "lead_hours": item["lead_hours"],
            "valid_time": item["valid_time"],
            "member_count": len(members),
            "temperature_q50_c": correct_distribution(temp, _learning_calibration("temperature"), variable="temperature")["raw"].get("q50"),
            "wind_q50_kmh": correct_distribution(wind, _learning_calibration("wind"), variable="wind")["raw"].get("q50"),
            "rain_q50_mm": correct_distribution(rain, _learning_calibration("rain"), variable="rain")["raw"].get("q50"),
            "rain_period_start_lead": statistics.median(starts) if starts else None,
            "sampled_lat": sample.get("sampled_lat"),
            "sampled_lon": sample.get("sampled_lon"),
            "distance_km": sample.get("distance_km"),
        })
    return points


def _summaries(vectors: dict, calibration_bundle: dict | None = None) -> dict:
    points: dict[str, list[dict]] = {point_id: [] for point_id in ISLAND_POINT_IDS}
    for item in sorted(vectors.values(), key=lambda x: (x["point_id"], x["lead_hours"])):
        if item["point_id"] not in points:
            continue
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
            calibration = _calibration_for(calibration_bundle, item["point_id"], variable, item["lead_hours"])
            dist = correct_distribution(values, calibration, variable=variable, threshold=threshold)
            if variable == "wind":
                local_values = [m["wind_local_kmh"] for m in members.values() if "wind_local_kmh" in m]
                local_dist = correct_distribution(local_values, calibration, variable=variable, threshold=threshold)
                dist["corrected"] = local_dist["corrected"]
                factors = [m["wind_exposure_factor"] for m in members.values() if "wind_exposure_factor" in m]
                dist["local_exposure"] = {
                    "engine": WIND_EXPOSURE_ENGINE,
                    "status": "HEURISTIC_V1" if item["point_id"] in WIND_EXPOSURE_8 else "NEUTRAL",
                    "mean_factor": round(sum(factors) / len(factors), 4) if factors else 1.0,
                    "directional_table": WIND_EXPOSURE_8.get(item["point_id"]),
                    "note": "Physical directional exposure is applied member-by-member before public wind probabilities; raw GEFS grid wind remains preserved.",
                }
                dist["rule"] = "Raw = GEFS grid wind. Corrected = local directional exposure, then statistical calibration when calibration becomes READY."
            dist["raw"]["completion_ratio"] = round(len(values) / 31, 3)
            dist["corrected"]["completion_ratio"] = round(len(values) / 31, 3)
            row["variables"][variable] = dist
        points[item["point_id"]].append(row)
    return points





def _raw_distribution(values: list[float], variable: str, threshold: float | None = None) -> dict:
    """Spatial cells remain raw GEFS until a cell-level calibration exists."""
    payload = correct_distribution(
        values,
        _learning_calibration(variable),
        variable=variable,
        threshold=threshold,
    )["raw"]
    return {
        "q50": payload.get("q50"),
        "q90": payload.get("q90"),
        "q95": payload.get("q95"),
        "spread": payload.get("spread"),
        "prob": payload.get("exceedance_probability"),
        "threshold": payload.get("exceedance_threshold"),
        "members": payload.get("member_count"),
    }


def _spatial_summaries(vectors: dict) -> dict:
    """Build compact D0-D10 ensemble fields on the native GEFS 0.5° grid."""
    by_frame: dict[tuple[int, str], list[dict]] = {}
    cells: dict[str, dict] = {}

    for item in vectors.values():
        cell_id = str(item.get("point_id") or "")
        if not cell_id.startswith("grid_"):
            continue
        members = item.get("members") or {}
        if not members:
            continue

        samples = list(members.values())
        sample = samples[0]
        lat = round(float(sample.get("sampled_lat")), 4)
        lon = round(float(sample.get("sampled_lon")), 4)
        cells[cell_id] = {"id": cell_id, "lat": lat, "lon": lon}

        temp = [float(m["temperature_c"]) for m in samples if m.get("temperature_c") is not None]
        wind = [float(m["wind_kmh"]) for m in samples if m.get("wind_kmh") is not None]
        rain = [float(m["rain_mm"]) for m in samples if m.get("rain_mm") is not None]
        us = [float(m["u10_ms"]) for m in samples if m.get("u10_ms") is not None]
        vs = [float(m["v10_ms"]) for m in samples if m.get("v10_ms") is not None]
        u50 = statistics.median(us) if us else None
        v50 = statistics.median(vs) if vs else None
        direction = _wind_from_direction_deg(u50, v50) if u50 is not None and v50 is not None else None

        row = {
            "cell_id": cell_id,
            "temperature": _raw_distribution(temp, "temperature"),
            "wind": {
                **_raw_distribution(wind, "wind", 30.0),
                "u10_q50_ms": round(u50, 4) if u50 is not None else None,
                "v10_q50_ms": round(v50, 4) if v50 is not None else None,
                "direction_q50_deg": round(direction, 1) if direction is not None else None,
            },
            "rain": _raw_distribution(rain, "rain", 5.0),
        }
        key = (int(item["lead_hours"]), str(item["valid_time"]))
        by_frame.setdefault(key, []).append(row)

    frames = []
    for (lead, valid), rows in sorted(by_frame.items(), key=lambda x: x[0][0]):
        rows.sort(key=lambda x: x["cell_id"])
        member_counts = [
            int(v.get("members") or 0)
            for row in rows
            for v in (row["temperature"], row["wind"], row["rain"])
            if v.get("members") is not None
        ]
        frames.append({
            "lead_hours": lead,
            "valid_time": valid,
            "members_min": min(member_counts) if member_counts else 0,
            "cells": rows,
        })

    ordered_cells = sorted(cells.values(), key=lambda x: (x["lat"], x["lon"]))
    return {
        "status": "READY" if frames and ordered_cells else "UNAVAILABLE",
        "model": "GEFS_0P50",
        "native_resolution_deg": NATIVE_GRID_DEG,
        "display_interpolation": "RENDER_ONLY",
        "bounds": BOX,
        "cell_count": len(ordered_cells),
        "cells": ordered_cells,
        "frames": frames,
        "variables": {
            "wind": ["q50", "q90", "q95", "spread", "prob", "u10_q50_ms", "v10_q50_ms", "direction_q50_deg"],
            "rain": ["q50", "q90", "q95", "spread", "prob"],
            "temperature": ["q50", "q90", "q95", "spread"],
        },
        "probability_thresholds": {"wind_kmh": 30.0, "rain_mm": 5.0},
        "note": "Native GEFS 0.5° ensemble field. Smooth map rendering does not increase model resolution.",
    }


def collect(output: Path | None = None, *, members: list[str] | None = None,
            leads: list[int] | None = None, max_workers: int = 3,
            calibration_bundle: dict | None = None) -> dict:
    members = members or MEMBERS
    leads = leads or LEADS
    attempts: list[dict] = []

    # Resolve a usable cycle with one tiny request before fan-out.
    cycle = None
    with tempfile.TemporaryDirectory(prefix="jotrip-gefs-local-") as tmp:
        work = Path(tmp)
        probe_member = members[0]
        probe_lead = leads[0]
        horizon_probe = max(leads)
        partial_cycle = None
        # Prefer the newest cycle whose full requested horizon is already
        # published. NOMADS releases long leads progressively, so probing only
        # f006 made a fresh-but-incomplete cycle collapse a nominal 10-day
        # product to ~3 days.
        for candidate in _candidate_cycles(days=3):
            recs, meta = _fetch_one(candidate, probe_member, horizon_probe, work)
            attempts.append({"cycle_horizon_probe": candidate.isoformat(), **meta})
            if recs:
                cycle = candidate
                break
            if partial_cycle is None:
                early, early_meta = _fetch_one(candidate, probe_member, probe_lead, work)
                attempts.append({"cycle_early_probe": candidate.isoformat(), **early_meta})
                if early:
                    partial_cycle = candidate
        if cycle is None:
            cycle = partial_cycle
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
        "horizon_hours": max((int(r["lead_hours"]) for r in all_records), default=0),
        "requested_horizon_hours": max(leads),
        "step_hours": sorted(leads),
        "members": members,
        "expected_member_step_files": expected_files,
        "completed_member_step_files": len(completed),
        "completion_ratio": round(completion, 4),
        "box": BOX,
        "points": _summaries(vectors, calibration_bundle),
        "verification_points": _verification_summaries(vectors),
        "spatial": _spatial_summaries(vectors),
        "calibration_engine": "PQ_ENSEMBLE_LOCAL_V1",
        "wind_exposure_engine": WIND_EXPOSURE_ENGINE,
        "wind_exposure_points": sorted(WIND_EXPOSURE_8),
        "calibration_status": (calibration_bundle or {}).get("status", "LEARNING"),
        "calibration_ready_groups": (calibration_bundle or {}).get("ready_groups", 0),
        "calibration_total_groups": (calibration_bundle or {}).get("total_groups", 0),
        "calibration_note": "Only ACTUAL VVPQ/VRain verification cases can train coefficients. A group is applied only after >=30 matched cases.",
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
    p.add_argument("--calibration", type=Path)
    args = p.parse_args()
    selected = MEMBERS[:max(1, min(31, args.members))]
    calibration_bundle = {}
    if args.calibration and args.calibration.exists():
        try:
            calibration_bundle = json.loads(args.calibration.read_text(encoding="utf-8"))
        except Exception:
            calibration_bundle = {}
    result = collect(
        args.output,
        members=selected,
        leads=args.lead or LEADS,
        max_workers=args.workers,
        calibration_bundle=calibration_bundle,
    )
    print(json.dumps({
        "status": result.get("status"),
        "run_time": result.get("run_time"),
        "completion_ratio": result.get("completion_ratio"),
        "horizon_hours": result.get("horizon_hours"),
        "rows": {k: len(v) for k, v in result.get("points", {}).items()},
        "spatial_cells": (result.get("spatial") or {}).get("cell_count"),
        "spatial_frames": len((result.get("spatial") or {}).get("frames") or []),
    }, ensure_ascii=False, indent=2))
