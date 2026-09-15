"""Live GEFS atmosphere and wave member-completeness smoke at one lead."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from weather.collectors.live_smoke import _candidate_cycles, _indexed_grib, _utcnow
from weather.processing.ensemble import summarize_members
from weather.processing.units import add_speed_display

ROOTS = (
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod",
    "https://noaa-gefs-pds.s3.amazonaws.com",
)


def _collect_family(kind: str, lead: int, work: Path) -> dict:
    attempts = []
    for cycle in _candidate_cycles():
        stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        values = []
        records = []
        selected_root = None
        for number in range(31):
            member = "c00" if number == 0 else f"p{number:02d}"
            if kind == "atmosphere":
                file_member = "gec00" if number == 0 else f"gep{number:02d}"
                key = f"gefs.{stamp}/{hour}/atmos/pgrb2ap5/{file_member}.t{hour}z.pgrb2a.0p50.f{lead:03d}"
                matcher = "UGRD:10 m above ground"
            else:
                key = f"gefs.{stamp}/{hour}/wave/gridded/gefs.wave.t{hour}z.{member}.global.0p25.f{lead:03d}.grib2"
                matcher = "HTSGW:surface"
            member_result = None
            for root in ROOTS:
                url = f"{root}/{key}"
                try:
                    member_result = _indexed_grib(url, f"{url}.idx", matcher, work / f"{kind}-{member}.grib2")
                    selected_root = selected_root or root
                    break
                except Exception as exc:
                    attempts.append({"member": member, "url": url, "error": f"{type(exc).__name__}: {exc}"})
            if member_result:
                value = member_result["decoded"]["phu_quoc_point"]["value"]
                values.append(value)
                records.append(add_speed_display({"member": member, "value": value,
                                "unit": member_result["decoded"]["units"],
                                "index_record": member_result["index_record"]}))
        if len(values) >= 24:
            summary = summarize_members(values, expected_members=31)
            return {"status": summary["status"], "readiness": "MEMBER_COMPLETE" if len(values) >= 28 else "POINT_ROUTE_EXTRACTED",
                    "qc": "PASS", "kind": kind, "run_time": cycle.isoformat(), "lead_hours": lead,
                    "selected_endpoint": selected_root, "members": records, "summary": summary,
                    "attempt_count": len(attempts), "attempts": attempts[-20:], "checked_at": _utcnow()}
    return {"status": "RETRIEVAL_FAILED", "readiness": "UNAVAILABLE", "qc": "FAIL", "attempts": attempts[-50:]}


def collect(output: Path | None = None, lead: int = 3) -> dict:
    with tempfile.TemporaryDirectory(prefix="jotrip-noaa-members-") as temp:
        work = Path(temp)
        result = {"atmosphere": _collect_family("atmosphere", lead, work),
                  "wave": _collect_family("wave", lead, work)}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lead", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(collect(args.output, args.lead), ensure_ascii=False, indent=2))
