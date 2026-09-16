"""Collect direct ECMWF atmosphere and wave fields for D0-D10 at locked points.

D0-D3 keeps the freshest operational cycle, including 06/18 UTC short cycles.
D4-D10 comes from the latest 00/12 UTC cycle that exposes step 240. The two
record sets are kept separate so accumulated precipitation is never differenced
across different model runs.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.collectors.live_smoke import _utcnow
from weather.processing.units import add_speed_display

POINTS = {
    "duong_dong": (10.2172, 103.9593),
    "an_thoi": (10.0191, 104.0150),
    "ganh_dau": (10.3759, 103.9000),
    "rach_gia": (10.00677, 105.07845),
}
SHORT_STEPS = list(range(0, 73, 3))
MEDIUM_STEPS = list(range(0, 145, 3)) + list(range(150, 241, 6))
STEPS = SHORT_STEPS  # backward compatibility for existing callers


def _decode_all(path: Path, run_time: datetime, source: str, stream: str) -> list[dict]:
    from eccodes import codes_get, codes_grib_find_nearest, codes_grib_new_from_file, codes_release

    records = []
    with path.open("rb") as handle:
        while (gid := codes_grib_new_from_file(handle)) is not None:
            try:
                step = int(codes_get(gid, "endStep"))
                variable = str(codes_get(gid, "shortName"))
                unit = str(codes_get(gid, "units"))
                valid_time = run_time + timedelta(hours=step)
                for point_id, (lat, lon) in POINTS.items():
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
                        "requested_lat": lat,
                        "requested_lon": lon,
                        "sampled_lat": float(nearest["lat"]),
                        "sampled_lon": float(nearest["lon"]),
                        "distance_km": float(nearest["distance"]),
                        "value": float(nearest["value"]),
                        "unit": unit,
                        "qc": "PASS",
                        "provenance": "DIRECT",
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


def _collect_gust(client, work: Path, run_time: datetime, steps: list[int], prefix: str) -> tuple[list[dict], str | None, str | None]:
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
            records = _decode_all(target, run_time, "ECMWF_IFS_DIRECT", "oper")
            if records:
                return records, parameter, None
        except Exception as exc:
            errors.append(f"{parameter}: {type(exc).__name__}: {exc}")
    return [], None, " | ".join(errors) if errors else "No gust records returned"


def _collect_wave_max(client, work: Path, run_time: datetime, steps: list[int], prefix: str) -> tuple[list[dict], str | None, str | None]:
    """Fetch ECMWF expected maximum individual wave height when available."""
    hmax_steps = [step for step in steps if step > 0]
    try:
        target = work / f"{prefix}-wave-hmax.grib2"
        client.retrieve(
            type="fc",
            stream="wave",
            step=hmax_steps,
            param=["hmax"],
            target=str(target),
            **_cycle_kwargs(run_time),
        )
        records = _decode_all(target, run_time, "ECMWF_WAVE_DIRECT", "wave")
        if records:
            return records, "hmax", None
        return [], None, "No hmax records returned"
    except Exception as exc:
        return [], None, f"hmax: {type(exc).__name__}: {exc}"


def _collect_cycle(client, work: Path, steps: list[int], prefix: str, run_time: datetime | None = None) -> dict:
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

    records = _decode_all(atmosphere, actual_run, "ECMWF_IFS_DIRECT", "oper")
    gust_records, gust_parameter, gust_error = _collect_gust(client, work, actual_run, steps, prefix)
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
        records.extend(_decode_all(wave, actual_run, "ECMWF_WAVE_DIRECT", "wave"))
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


def collect(output: Path | None = None) -> dict:
    from ecmwf.opendata import Client

    attempts = []
    for source in ("ecmwf", "aws", "google"):
        try:
            with tempfile.TemporaryDirectory(prefix="jotrip-ecmwf-d10-") as temp:
                work = Path(temp)
                client = Client(source=source, maximum_retries=2, retry_after=2)

                short = _collect_cycle(client, work, SHORT_STEPS, "short")
                full_cycle = _latest_full_cycle(client)
                medium = _collect_cycle(client, work, MEDIUM_STEPS, "medium", run_time=full_cycle)

                short_records = short["records"]
                medium_records = medium["records"]
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
