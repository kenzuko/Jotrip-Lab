"""Lightweight model-cycle watcher for Weather Lab.

Checks metadata every 30 minutes. ECMWF is tracked as two cycles: the freshest
short operational cycle for D0-D3 and the latest 00/12 cycle exposing step 240
for D4-D10. Heavy ingestion runs only when a tracked cycle changes.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from weather.collectors.live_smoke import USER_AGENT, _candidate_cycles, _request

DWD_ROOT = "https://opendata.dwd.de/weather/nwp/icon/grib"
NOAA_ROOTS = (
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod",
    "https://noaa-gefs-pds.s3.amazonaws.com",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_previous(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_ecmwf(step: int) -> str:
    from ecmwf.opendata import Client

    errors = []
    for source in ("ecmwf", "aws", "google"):
        try:
            client = Client(source=source, maximum_retries=1, retry_after=1)
            latest = client.latest(type="fc", stream="oper", step=step, param="10u")
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            return latest.astimezone(timezone.utc).isoformat()
        except Exception as exc:
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"ECMWF step {step} cycle lookup failed: " + " | ".join(errors))


def latest_ecmwf_cycle() -> str:
    return _latest_ecmwf(3)


def latest_ecmwf_medium_cycle() -> str:
    return _latest_ecmwf(240)


def latest_gefs_cycle() -> str:
    errors = []
    for cycle in _candidate_cycles(days=2):
        stamp, hour = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
        key = f"gefs.{stamp}/{hour}/atmos/pgrb2ap5/gec00.t{hour}z.pgrb2a.0p50.f003.idx"
        for root in NOAA_ROOTS:
            url = f"{root}/{key}"
            try:
                payload = _request(url, timeout=10)
                if b"UGRD:10 m above ground" in payload:
                    return cycle.isoformat()
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("GEFS cycle lookup failed: " + " | ".join(errors[-8:]))


def _icon_stamp(name: str) -> str | None:
    match = re.search(r"_(\d{10})_000_U_10M\.grib2\.bz2$", name, flags=re.I)
    return match.group(1) if match else None


def latest_icon_cycle() -> str:
    candidates: list[tuple[str, str]] = []
    errors = []
    for hour in (0, 6, 12, 18):
        directory = f"{DWD_ROOT}/{hour:02d}/u_10m/"
        try:
            html = _request(directory, timeout=10).decode("utf-8", errors="replace")
            for name in re.findall(r'href="([^"]+_000_U_10M\.grib2\.bz2)"', html, flags=re.I):
                stamp = _icon_stamp(name)
                if stamp:
                    candidates.append((stamp, directory + name))
        except Exception as exc:
            errors.append(f"{directory}: {type(exc).__name__}: {exc}")
    if not candidates:
        raise RuntimeError("ICON cycle lookup failed: " + " | ".join(errors))
    stamp, _ = max(candidates, key=lambda item: item[0])
    parsed = datetime.strptime(stamp, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def compare_cycles(current: dict[str, str | None], previous: dict[str, str | None]) -> list[str]:
    changed = []
    for source, cycle in current.items():
        if cycle and cycle != previous.get(source):
            changed.append(source)
    return changed


def watch(snapshot: Path | None = None) -> dict:
    previous_payload = _load_previous(snapshot)
    previous = previous_payload.get("source_cycles", {}) if isinstance(previous_payload, dict) else {}
    current: dict[str, str | None] = {
        "ECMWF": None,
        "ECMWF_MEDIUM": None,
        "GEFS": None,
        "ICON": None,
    }
    errors: dict[str, str] = {}

    lookups = {
        "ECMWF": latest_ecmwf_cycle,
        "ECMWF_MEDIUM": latest_ecmwf_medium_cycle,
        "GEFS": latest_gefs_cycle,
        "ICON": latest_icon_cycle,
    }
    for source, lookup in lookups.items():
        try:
            current[source] = lookup()
        except Exception as exc:
            errors[source] = f"{type(exc).__name__}: {exc}"

    changed = compare_cycles(current, previous)
    known = [source for source, cycle in current.items() if cycle]
    return {
        "checked_at": _utcnow(),
        "status": "PASS" if len(known) == len(current) else "DEGRADED",
        "run_heavy": bool(changed),
        "changed_sources": changed,
        "current_cycles": current,
        "previous_cycles": previous,
        "errors": errors,
        "policy": "30-minute metadata watch; D0-D3 short cycle + D4-D10 step-240 medium cycle; heavy ingest only on change",
        "user_agent": USER_AGENT,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = watch(args.snapshot)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
