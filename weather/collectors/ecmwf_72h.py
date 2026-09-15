"""Collect direct ECMWF atmosphere and wave fields for D0-D3 at locked points."""
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
}
STEPS = list(range(0, 73, 3))


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
                        "source": source, "stream": stream, "run_time": run_time.isoformat(),
                        "valid_time": valid_time.isoformat(), "lead_hours": step,
                        "member": None, "variable": variable, "point_id": point_id,
                        "requested_lat": lat, "requested_lon": lon,
                        "sampled_lat": float(nearest["lat"]), "sampled_lon": float(nearest["lon"]),
                        "distance_km": float(nearest["distance"]), "value": float(nearest["value"]),
                        "unit": unit, "qc": "PASS", "provenance": "DIRECT",
                    }))
            finally:
                codes_release(gid)
    return records


def collect(output: Path | None = None) -> dict:
    from ecmwf.opendata import Client

    attempts = []
    for source in ("ecmwf", "aws", "google"):
        try:
            with tempfile.TemporaryDirectory(prefix="jotrip-ecmwf-72h-") as temp:
                work = Path(temp)
                client = Client(source=source, maximum_retries=2, retry_after=2)
                atmosphere = work / "atmos.grib2"
                atmos_result = client.retrieve(type="fc", stream="oper", step=STEPS,
                                               param=["10u", "10v", "tp"], target=str(atmosphere))
                run_time = atmos_result.datetime.astimezone(timezone.utc)
                records = _decode_all(atmosphere, run_time, "ECMWF_IFS_DIRECT", "oper")
                wave_error = None
                try:
                    wave = work / "wave.grib2"
                    client.retrieve(type="fc", stream="wave", step=STEPS,
                                    param=["swh", "mwd", "mwp", "pp1d"], target=str(wave))
                    records.extend(_decode_all(wave, run_time, "ECMWF_WAVE_DIRECT", "wave"))
                except Exception as exc:
                    wave_error = f"{type(exc).__name__}: {exc}"
                result = {
                    "status": "POINT_ROUTE_EXTRACTED" if records else "FIELD_DECODE_FAILED",
                    "readiness": "POINT_ROUTE_EXTRACTED" if records else "UNAVAILABLE",
                    "qc": "PASS" if records else "FAIL", "selected_endpoint": source,
                    "run_time": run_time.isoformat(), "horizon_hours": 72,
                    "steps": STEPS, "record_count": len(records), "records": records,
                    "wave_error": wave_error, "attempts": attempts, "checked_at": _utcnow(),
                }
                if output:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return result
        except Exception as exc:
            attempts.append({"endpoint": source, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "RETRIEVAL_FAILED", "readiness": "UNAVAILABLE", "qc": "FAIL", "attempts": attempts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.output), ensure_ascii=False, indent=2))
