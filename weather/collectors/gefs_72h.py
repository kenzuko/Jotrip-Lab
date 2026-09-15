"""Direct GEFS atmosphere and wave member collector for D0-D3.

This production collector is intentionally separate from the one-lead smoke
test. It preserves member/run/lead metadata and fails variables explicitly.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from weather.collectors.ecmwf_72h import POINTS, _decode_all
from weather.collectors.live_smoke import _candidate_cycles, _indexed_grib, _utcnow
from weather.processing.atmosphere import derive_wind_records

ROOTS = ("https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod",
         "https://noaa-gefs-pds.s3.amazonaws.com")
STEPS = list(range(0, 73, 3))
ATMOS_FIELDS = {"ugrd10m": "UGRD:10 m above ground", "vgrd10m": "VGRD:10 m above ground",
                "gust": "GUST:surface", "apcp": "APCP:surface"}
WAVE_FIELDS = {"swh": "HTSGW:surface", "mwd": "DIRPW:surface", "mwp": "PERPW:surface"}


def _member_name(number: int) -> tuple[str, str]:
    return ("c00", "gec00") if number == 0 else (f"p{number:02d}", f"gep{number:02d}")


def collect(output: Path | None = None, members: int = 31, steps: list[int] | None = None) -> dict:
    steps = steps or STEPS
    attempts, records, missing = [], [], []
    cycle = next(_candidate_cycles())
    stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    with tempfile.TemporaryDirectory(prefix="jotrip-gefs-72h-") as temp:
        work = Path(temp)
        for number in range(members):
            wave_member, atmos_member = _member_name(number)
            for lead in steps:
                families = (
                    ("atmosphere", atmos_member,
                     f"gefs.{stamp}/{hour}/atmos/pgrb2ap5/{atmos_member}.t{hour}z.pgrb2a.0p50.f{lead:03d}", ATMOS_FIELDS),
                    ("wave", wave_member,
                     f"gefs.{stamp}/{hour}/wave/gridded/gefs.wave.t{hour}z.{wave_member}.global.0p25.f{lead:03d}.grib2", WAVE_FIELDS),
                )
                for family, member, key, fields in families:
                    for variable, matcher in fields.items():
                        success = None
                        for root in ROOTS:
                            url = f"{root}/{key}"
                            try:
                                target = work / f"{family}-{member}-{lead}-{variable}.grib2"
                                success = _indexed_grib(url, f"{url}.idx", matcher, target)
                                decoded = _decode_all(target, cycle, f"NOAA_GEFS_{family.upper()}_DIRECT", family)
                                for record in decoded:
                                    record["member"] = member
                                    record["lineage_id"] = f"GEFS_{stamp}{hour}_{family}"
                                    record["requested_field"] = variable
                                records.extend(decoded)
                                break
                            except Exception as exc:
                                attempts.append({"member": member, "lead": lead, "field": variable,
                                                 "endpoint": root, "error": f"{type(exc).__name__}: {exc}"})
                        if success is None:
                            missing.append({"member": member, "lead": lead, "field": variable, "family": family})
    expected = members * len(steps) * (len(ATMOS_FIELDS) + len(WAVE_FIELDS)) * len(POINTS)
    ratio = len(records) / expected if expected else 0
    result = {"status": "MEMBER_COMPLETE" if ratio >= .9 else "PARTIAL_OR_FAILED",
              "readiness": "MEMBER_COMPLETE" if ratio >= .9 else "POINT_ROUTE_EXTRACTED" if records else "UNAVAILABLE",
              "qc": "PASS" if ratio >= .75 else "FAIL", "run_time": cycle.isoformat(),
              "horizon_hours": max(steps), "members_requested": members, "steps": steps,
              "expected_point_records": expected, "record_count": len(records),
              "completion_ratio": round(ratio, 4), "records": records,
              "derived_wind": derive_wind_records(records), "missing": missing,
              "attempts": attempts[-100:], "checked_at": _utcnow()}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--members", type=int, default=31)
    parser.add_argument("--lead", type=int, action="append")
    args = parser.parse_args()
    print(json.dumps(collect(args.output, args.members, args.lead), ensure_ascii=False, indent=2))
