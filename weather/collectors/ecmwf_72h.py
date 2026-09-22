"""Collect direct ECMWF atmosphere and wave fields for D0-D10 at locked points.

D0-D3 keeps the freshest operational cycle, including 06/18 UTC short cycles.
D4-D10 comes from the latest 00/12 UTC cycle that exposes step 240. The two
record sets are kept separate so accumulated precipitation is never differenced
across different model runs.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.collectors.live_smoke import _utcnow
from weather.points import POINTS, POINT_METADATA
from weather.processing.units import add_speed_display
from weather.spatial_domain import (
    ECMWF_MEDIUM_BOUNDS,
    ECMWF_RENDER_STEP_DEG,
    ECMWF_SHORT_BOUNDS,
    grid_requests,
)

SHORT_STEPS = list(range(0, 73, 3))
MEDIUM_STEPS = list(range(0, 145, 3)) + list(range(150, 241, 6))
STEPS = SHORT_STEPS  # backward compatibility for existing callers

# The interactive D0-D3 map uses a wide Gulf envelope so the visible viewport
# never reaches an artificial data edge. D4-D10 keeps the compact core grid
# because it is a trend product, not the live spatial map.
SPATIAL_GRID_DEG = ECMWF_RENDER_STEP_DEG
SHORT_SPATIAL_GRID_REQUESTS = grid_requests(ECMWF_SHORT_BOUNDS, SPATIAL_GRID_DEG)
MEDIUM_SPATIAL_GRID_REQUESTS = grid_requests(ECMWF_MEDIUM_BOUNDS, SPATIAL_GRID_DEG)


def _decode_all(
    path: Path,
    run_time: datetime,
    source: str,
    stream: str,
    spatial_grid_requests: tuple[tuple[float, float], ...],
) -> list[dict]:
    from eccodes import codes_get, codes_grib_find_nearest, codes_grib_new_from_file, codes_release

    records = []
    with path.open("rb") as handle:
        while (gid := codes_grib_new_from_file(handle)) is not None:
            try:
                step = int(codes_get(gid, "endStep"))
                variable = str(codes_get(gid, "shortName"))
                unit = str(codes_get(gid, "units"))
                valid_time = run_time + timedelta(hours=step)
                targets = []
                for point_id, (semantic_lat, semantic_lon) in POINTS.items():
                    requested_lat, requested_lon = semantic_lat, semantic_lon
                    sample_kind = "OPERATIONAL_ANCHOR"
                    marine_ref = POINT_METADATA.get(point_id, {}).get("marine_forecast_reference") if stream == "wave" else None
                    if isinstance(marine_ref, dict):
                        try:
                            requested_lat = float(marine_ref["lat"])
                            requested_lon = float(marine_ref["lon"])
                            sample_kind = "MARINE_REFERENCE"
                        except (KeyError, TypeError, ValueError):
                            requested_lat, requested_lon = semantic_lat, semantic_lon
                            sample_kind = "OPERATIONAL_ANCHOR"
                    targets.append((point_id, requested_lat, requested_lon, sample_kind, semantic_lat, semantic_lon))
                targets += [
                    (f"grid_{lat:.2f}_{lon:.2f}", lat, lon, "SPATIAL_GRID", lat, lon)
                    for lat, lon in spatial_grid_requests
                ]
                for point_id, lat, lon, sample_kind, semantic_lat, semantic_lon in targets:
                    nearest = codes_grib_find_nearest(gid, lat, lon)[0]
                    records.append(add_speed_display({
                        "source": source,
                        "stream": stream,
                        "run_time": run_time.isoformat(),
                        "valid_time": valid_time.isoformat(),
                        "lead_hours": step,
                        "member": None,
                        "variable": variable,
                        "point_id": point_id,
                        "sample_kind": sample_kind,
                        "semantic_lat": semantic_lat,
                        "semantic_lon": semantic_lon,
                        "requested_lat": lat,
                        "requested_lon": lon,
                        "sampled_lat": float(nearest["lat"]),
                        "sampled_lon": float(nearest["lon"]),
                        "distance_km": float(nearest["distance"]),
                        "value": float(nearest["value"]),
                        "unit": unit,
                        "qc": "PASS",
                        "provenance": "DIRECT_MARINE_REFERENCE" if sample_kind == "MARINE_REFERENCE" else "DIRECT",
                    }))
            finally:
                codes_release(gid)
    return records


def _cycle_kwargs(run_time: datetime | None) -> dict:
    if run_time is None:
        return {}
    return {"date": run_time.strftime("%Y%m%d"), "time": run_time.hour}


def _latest_full_cycle(client) -> datetime:
    latest = client.latest(type="fc", stream="oper", step=240, param="10u")
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return latest.astimezone(timezone.utc)


def _collect_gust(
    client,
    work: Path,
    run_time: datetime,
    steps: list[int],
    prefix: str,
    spatial_grid_requests: tuple[tuple[float, float], ...],
) -> tuple[list[dict], str | None, str | None]:
    """Fetch gust independently so an outage cannot break base wind/rain ingest."""
    errors = []
    gust_steps = [step for step in steps if step > 0]
    for parameter in ("10fg", "i10fg"):
        try:
            target = work / f"{prefix}-gust-{parameter}.grib2"
            client.retrieve(
                type="fc",
                stream="oper",
                step=gust_steps,
                param=[parameter],
                target=str(target),
                **_cycle_kwargs(run_time),
            )
            records = _decode_all(
                target, run_time, "ECMWF_IFS_DIRECT", "oper", spatial_grid_requests
            )
            if records:
                return records, parameter, None
        except Exception as exc:
            errors.append(f"{parameter}: {type(exc).__name__}: {exc}")
    return [], None, " | ".join(errors) if errors else "No gust records returned"


def _collect_wave_max(client, work: Path, run_time: datetime, steps: list[int], prefix: str) -> tuple[list[dict], str | None, str | None]:
    """Keep the direct-Hmax slot explicit without querying an unpublished Open Data field."""
    return [], None, (
        "ECMWF Open Data hiện không phát hành trực tiếp Hmax; "
        "Weather Lab dùng proxy Rayleigh 20 phút từ Hs và ghi rõ phương pháp."
    )


def _collect_cycle(
    client,
    work: Path,
    steps: list[int],
    prefix: str,
    run_time: datetime | None = None,
    spatial_grid_requests: tuple[tuple[float, float], ...] = SHORT_SPATIAL_GRID_REQUESTS,
) -> dict:
    atmosphere = work / f"{prefix}-atmos.grib2"
    atmos_result = client.retrieve(
        type="fc",
        stream="oper",
        step=steps,
        param=["10u", "10v", "2t", "tp"],
        target=str(atmosphere),
        **_cycle_kwargs(run_time),
    )
    actual_run = run_time or atmos_result.datetime.astimezone(timezone.utc)
    if actual_run.tzinfo is None:
        actual_run = actual_run.replace(tzinfo=timezone.utc)
    actual_run = actual_run.astimezone(timezone.utc)

    records = _decode_all(
        atmosphere, actual_run, "ECMWF_IFS_DIRECT", "oper", spatial_grid_requests
    )
    gust_records, gust_parameter, gust_error = _collect_gust(
        client, work, actual_run, steps, prefix, spatial_grid_requests
    )
    records.extend(gust_records)

    wave_error = None
    try:
        wave = work / f"{prefix}-wave.grib2"
        client.retrieve(
            type="fc",
            stream="wave",
            step=steps,
            param=["swh", "mwd", "mwp", "pp1d"],
            target=str(wave),
            **_cycle_kwargs(actual_run),
        )
        records.extend(
            _decode_all(wave, actual_run, "ECMWF_WAVE_DIRECT", "wave", spatial_grid_requests)
        )
    except Exception as exc:
        wave_error = f"{type(exc).__name__}: {exc}"

    wave_max_records, wave_max_parameter, wave_max_error = _collect_wave_max(
        client, work, actual_run, steps, prefix
    )
    records.extend(wave_max_records)
    return {
        "run_time": actual_run,
        "records": records,
        "gust_parameter": gust_parameter,
        "gust_error": gust_error,
        "wave_error": wave_error,
        "wave_max_parameter": wave_max_parameter,
        "wave_max_error": wave_max_error,
    }



def _speed_kmh(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    u = str(unit or "").lower().replace(" ", "")
    v = float(value)
    if "m/s" in u or "ms**-1" in u or "ms-1" in u or "m*s**-1" in u:
        v *= 3.6
    return round(v, 3)


def _temp_c(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    v = float(value)
    if str(unit or "").lower() in {"k", "kelvin"} or v > 150:
        v -= 273.15
    return round(v, 3)


def _valid_scalar(value: float | None, low: float | None = None, high: float | None = None) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    # ECMWF wave GRIB may expose 9999 at land / unavailable cells.
    if abs(v) >= 9000:
        return None
    if low is not None and v < low:
        return None
    if high is not None and v > high:
        return None
    return v


def _rain_mm(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    v = max(0.0, float(value))
    u = str(unit or "").lower().replace(" ", "")
    if u in {"m", "mofwaterequivalent"} or ("m" in u and "kg" not in u and "mm" not in u):
        v *= 1000.0
    return round(v, 4)


def _spatial_frames(records: list[dict]) -> list[dict]:
    """Convert one ECMWF cycle into compact per-time spatial frames."""
    grouped: dict[tuple[str, str], dict[str, dict]] = {}
    cell_meta: dict[str, dict] = {}

    for record in records:
        if record.get("sample_kind") != "SPATIAL_GRID" or record.get("qc") != "PASS":
            continue
        cell_id = str(record.get("point_id"))
        valid = str(record.get("valid_time"))
        grouped.setdefault((cell_id, valid), {})[str(record.get("variable"))] = record
        cell_meta[cell_id] = {
            "cell_id": cell_id,
            "lat": round(float(record.get("sampled_lat")), 4),
            "lon": round(float(record.get("sampled_lon")), 4),
            "requested_lat": round(float(record.get("requested_lat")), 4),
            "requested_lon": round(float(record.get("requested_lon")), 4),
        }

    per_cell: dict[str, list[dict]] = {}
    for (cell_id, valid), bucket in grouped.items():
        lead = min((int(r.get("lead_hours", 0)) for r in bucket.values()), default=0)
        u = bucket.get("10u") or bucket.get("u10")
        v = bucket.get("10v") or bucket.get("v10")
        u_ms = float(u["value"]) if u else None
        v_ms = float(v["value"]) if v else None
        wind_kmh = math.hypot(u_ms, v_ms) * 3.6 if u_ms is not None and v_ms is not None else None
        wind_dir = (math.degrees(math.atan2(-u_ms, -v_ms)) + 360.0) % 360.0 if u_ms is not None and v_ms is not None else None
        temp = bucket.get("2t") or bucket.get("t2m")
        gust = bucket.get("10fg") or bucket.get("i10fg")
        tp = bucket.get("tp")
        swh = bucket.get("swh")
        mwd = bucket.get("mwd")
        period = bucket.get("pp1d") or bucket.get("mwp")
        row = {
            **cell_meta[cell_id],
            "valid_time": valid,
            "lead_hours": lead,
            "temperature_c": _temp_c(float(temp["value"]), temp.get("unit")) if temp else None,
            "u10_ms": round(u_ms, 4) if u_ms is not None else None,
            "v10_ms": round(v_ms, 4) if v_ms is not None else None,
            "wind_kmh": round(wind_kmh, 3) if wind_kmh is not None else None,
            "wind_direction_deg": round(wind_dir, 1) if wind_dir is not None else None,
            "gust_kmh": _speed_kmh(float(gust["value"]), gust.get("unit")) if gust else None,
            "tp_accum_mm": _rain_mm(float(tp["value"]), tp.get("unit")) if tp else None,
            "rain_mm": None,
            "wave_hs_m": (
                round(_valid_scalar(swh["value"], 0.0, 30.0), 3)
                if swh and _valid_scalar(swh["value"], 0.0, 30.0) is not None else None
            ),
            "wave_direction_deg": (
                round(_valid_scalar(mwd["value"], 0.0, 360.0), 1)
                if mwd and _valid_scalar(mwd["value"], 0.0, 360.0) is not None else None
            ),
            "wave_period_s": (
                round(_valid_scalar(period["value"], 0.0, 60.0), 2)
                if period and _valid_scalar(period["value"], 0.0, 60.0) is not None else None
            ),
        }
        per_cell.setdefault(cell_id, []).append(row)

    # TP is accumulated within one model cycle. Difference only inside that
    # cycle, never across the short/medium cycle boundary.
    for rows in per_cell.values():
        rows.sort(key=lambda x: x["valid_time"])
        previous = None
        for row in rows:
            current = row.get("tp_accum_mm")
            if current is not None:
                row["rain_mm"] = round(max(0.0, current if previous is None else current - previous), 3)
                previous = current
            row.pop("tp_accum_mm", None)

    by_time: dict[tuple[int, str], list[dict]] = {}
    for rows in per_cell.values():
        for row in rows:
            key = (int(row["lead_hours"]), str(row["valid_time"]))
            by_time.setdefault(key, []).append(row)

    frames = []
    for (lead, valid), cells in sorted(by_time.items(), key=lambda x: x[0][1]):
        cells.sort(key=lambda x: (x["lat"], x["lon"]))
        frames.append({"lead_hours": lead, "valid_time": valid, "cells": cells})
    return frames


def _merge_spatial(short_records: list[dict], medium_records: list[dict], short_run: datetime, medium_run: datetime) -> dict:
    short_frames = _spatial_frames(short_records)
    medium_frames = _spatial_frames(medium_records)
    short_end = max((datetime.fromisoformat(f["valid_time"].replace("Z", "+00:00")) for f in short_frames), default=None)
    frames = list(short_frames)
    if short_end is not None:
        frames.extend(
            f for f in medium_frames
            if datetime.fromisoformat(f["valid_time"].replace("Z", "+00:00")) > short_end
        )
    else:
        frames = medium_frames

    cells = {}
    for frame in frames:
        for row in frame["cells"]:
            cells[row["cell_id"]] = {
                "id": row["cell_id"],
                "lat": row["lat"],
                "lon": row["lon"],
                "requested_lat": row["requested_lat"],
                "requested_lon": row["requested_lon"],
            }

    return {
        "status": "READY" if frames else "UNAVAILABLE",
        "product": "ECMWF_IFS_DIRECT_SPATIAL",
        "requested_grid_deg": SPATIAL_GRID_DEG,
        "short_bounds": ECMWF_SHORT_BOUNDS,
        "medium_bounds": ECMWF_MEDIUM_BOUNDS,
        "display_interpolation": "RENDER_ONLY",
        "short_run_time": short_run.isoformat(),
        "medium_run_time": medium_run.isoformat(),
        "cell_count": len(cells),
        "cells": sorted(cells.values(), key=lambda x: (x["lat"], x["lon"])),
        "frames": frames,
        "variables": [
            "temperature_c", "u10_ms", "v10_ms", "wind_kmh", "wind_direction_deg",
            "gust_kmh", "rain_mm", "wave_hs_m", "wave_direction_deg", "wave_period_s"
        ],
        "note": "Direct ECMWF Open Data sampled on a 0.25° renderer grid. D0-D3 uses the wide Gulf display envelope; D4-D10 keeps a compact Phu Quoc core grid. Interpolation is display-only.",
    }



def collect(output: Path | None = None) -> dict:
    from ecmwf.opendata import Client

    attempts = []
    for source in ("ecmwf", "aws", "google"):
        try:
            with tempfile.TemporaryDirectory(prefix="jotrip-ecmwf-d10-") as temp:
                work = Path(temp)
                client = Client(source=source, maximum_retries=2, retry_after=2)

                short = _collect_cycle(
                    client,
                    work,
                    SHORT_STEPS,
                    "short",
                    spatial_grid_requests=SHORT_SPATIAL_GRID_REQUESTS,
                )
                full_cycle = _latest_full_cycle(client)
                medium = _collect_cycle(
                    client,
                    work,
                    MEDIUM_STEPS,
                    "medium",
                    run_time=full_cycle,
                    spatial_grid_requests=MEDIUM_SPATIAL_GRID_REQUESTS,
                )

                short_all = short["records"]
                medium_all = medium["records"]
                short_records = [r for r in short_all if r.get("sample_kind") != "SPATIAL_GRID"]
                medium_records = [r for r in medium_all if r.get("sample_kind") != "SPATIAL_GRID"]
                short_spatial = [r for r in short_all if r.get("sample_kind") == "SPATIAL_GRID"]
                medium_spatial = [r for r in medium_all if r.get("sample_kind") == "SPATIAL_GRID"]
                spatial = _merge_spatial(short_spatial, medium_spatial, short["run_time"], medium["run_time"])
                total_records = len(short_records) + len(medium_records)
                result = {
                    "status": "POINT_ROUTE_EXTRACTED" if short_records and medium_records else "FIELD_DECODE_FAILED",
                    "readiness": "POINT_ROUTE_EXTRACTED" if short_records and medium_records else "UNAVAILABLE",
                    "qc": "PASS" if short_records and medium_records else "FAIL",
                    "selected_endpoint": source,
                    "run_time": short["run_time"].isoformat(),
                    "medium_run_time": medium["run_time"].isoformat(),
                    "horizon_hours": 240,
                    "steps": SHORT_STEPS,
                    "medium_steps": MEDIUM_STEPS,
                    "short_record_count": len(short_records),
                    "medium_record_count": len(medium_records),
                    "record_count": total_records,
                    "spatial_record_count": len(short_spatial) + len(medium_spatial),
                    "spatial": spatial,
                    "records": short_records,
                    "medium_records": medium_records,
                    "gust_parameter": short["gust_parameter"],
                    "gust_error": short["gust_error"],
                    "medium_gust_parameter": medium["gust_parameter"],
                    "medium_gust_error": medium["gust_error"],
                    "wave_error": short["wave_error"],
                    "medium_wave_error": medium["wave_error"],
                    "wave_max_parameter": short["wave_max_parameter"],
                    "wave_max_error": short["wave_max_error"],
                    "medium_wave_max_parameter": medium["wave_max_parameter"],
                    "medium_wave_max_error": medium["wave_max_error"],
                    "policy": "D0-D3 freshest oper cycle; D4-D10 latest 00/12 cycle with step 240",
                    "attempts": attempts,
                    "checked_at": _utcnow(),
                }
                if output:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return result
        except Exception as exc:
            attempts.append({"endpoint": source, "error": f"{type(exc).__name__}: {exc}"})
    result = {
        "status": "RETRIEVAL_FAILED",
        "readiness": "UNAVAILABLE",
        "qc": "FAIL",
        "attempts": attempts,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.output), ensure_ascii=False, indent=2))
