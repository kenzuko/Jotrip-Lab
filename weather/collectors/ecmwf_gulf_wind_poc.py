"""Compact Gulf of Thailand ECMWF wind render pack for renderer POC.

This collector is intentionally isolated from the operational Weather Lab products.
It downloads only 10 m U/V wind for D0-D3, samples the native 0.25 degree grid
across the Gulf watch domain, and writes compact flat arrays for browser rendering.

The output is a render transport product. It does not replace JoTrip numerical truth.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BOUNDS = {
    "west": 100.75,
    "south": 7.50,
    "east": 105.75,
    "north": 13.00,
}
STEP_DEG = 0.25
LEADS = list(range(0, 73, 3))


def _axis(start: float, end: float, step: float) -> list[float]:
    count = int(round((end - start) / step))
    return [round(start + i * step, 2) for i in range(count + 1)]


LATS = _axis(BOUNDS["south"], BOUNDS["north"], STEP_DEG)
LONS = _axis(BOUNDS["west"], BOUNDS["east"], STEP_DEG)


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _sample_grib(path: Path, run_time: datetime) -> list[dict]:
    from eccodes import (
        codes_get,
        codes_grib_find_nearest,
        codes_grib_new_from_file,
        codes_release,
    )

    by_lead: dict[int, dict[str, list[float]]] = {}

    with path.open("rb") as handle:
        while (gid := codes_grib_new_from_file(handle)) is not None:
            try:
                variable = str(codes_get(gid, "shortName"))
                if variable not in {"10u", "u10", "10v", "v10"}:
                    continue
                lead = int(codes_get(gid, "endStep"))
                if lead not in LEADS:
                    continue

                canonical = "u" if variable in {"10u", "u10"} else "v"
                values: list[float] = []
                for lat in LATS:
                    for lon in LONS:
                        nearest = codes_grib_find_nearest(gid, lat, lon)[0]
                        value = float(nearest["value"])
                        values.append(round(value, 3) if math.isfinite(value) else None)

                by_lead.setdefault(lead, {})[canonical] = values
            finally:
                codes_release(gid)

    frames = []
    expected = len(LATS) * len(LONS)
    for lead in LEADS:
        bucket = by_lead.get(lead) or {}
        u = bucket.get("u")
        v = bucket.get("v")
        if not u or not v or len(u) != expected or len(v) != expected:
            continue

        speed = []
        for uu, vv in zip(u, v):
            if uu is None or vv is None:
                speed.append(None)
            else:
                speed.append(round(math.hypot(uu, vv) * 3.6, 2))

        valid = run_time.timestamp() + lead * 3600
        valid_time = datetime.fromtimestamp(valid, tz=timezone.utc).isoformat()
        frames.append({
            "lead_hours": lead,
            "valid_time": valid_time,
            "u_ms": u,
            "v_ms": v,
            "speed_kmh": speed,
        })

    return frames


def collect() -> dict:
    from ecmwf.opendata import Client

    attempts = []
    for source in ("ecmwf", "aws", "google"):
        try:
            with tempfile.TemporaryDirectory(prefix="jotrip-gulf-wind-poc-") as tmp:
                target = Path(tmp) / "wind.grib2"
                client = Client(source=source, maximum_retries=2, retry_after=2)
                result = client.retrieve(
                    type="fc",
                    stream="oper",
                    step=LEADS,
                    param=["10u", "10v"],
                    target=str(target),
                )
                run_time = result.datetime
                if run_time.tzinfo is None:
                    run_time = run_time.replace(tzinfo=timezone.utc)
                run_time = run_time.astimezone(timezone.utc)
                frames = _sample_grib(target, run_time)
                if len(frames) < 20:
                    raise RuntimeError(f"Only {len(frames)} valid frames")

                return {
                    "schema": "JOTRIP_GULF_WIND_POC_V1",
                    "status": "READY",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "ECMWF_IFS_OPEN_DATA_DIRECT",
                    "selected_endpoint": source,
                    "run_time": _iso(run_time),
                    "bounds": BOUNDS,
                    "grid": {
                        "step_deg": STEP_DEG,
                        "ny": len(LATS),
                        "nx": len(LONS),
                        "order": "lat_ascending_then_lon_ascending",
                        "lats": LATS,
                        "lons": LONS,
                    },
                    "frames": frames,
                    "display_interpolation": "RENDER_ONLY",
                    "note": (
                        "Renderer POC transport pack only. Values are direct ECMWF 10 m U/V "
                        "samples on the 0.25 degree Gulf grid; browser smoothing does not "
                        "increase meteorological resolution."
                    ),
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"endpoint": source, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "schema": "JOTRIP_GULF_WIND_POC_V1",
        "status": "UNAVAILABLE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bounds": BOUNDS,
        "grid": {"step_deg": STEP_DEG, "ny": len(LATS), "nx": len(LONS)},
        "frames": [],
        "attempts": attempts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload.get("status"),
        "run_time": payload.get("run_time"),
        "grid": payload.get("grid"),
        "frames": len(payload.get("frames") or []),
        "attempts": payload.get("attempts"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
