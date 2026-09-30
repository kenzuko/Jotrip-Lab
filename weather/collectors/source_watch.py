"""Lightweight change detector for fast Weather sources.

This watcher answers only one question: did the upstream source publish a new
identity/value? It intentionally does not decode Himawari NetCDF, build Local
Now, calibrate models or archive snapshots.

A successful fetch is not itself a new observation.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from weather.collectors.phuquoc_ground_truth import (
    AWC_URL,
    PHU_QUOC_RAIN_BOUNDS,
    VRAIN_CURRENT_URL,
    USER_AGENT,
    _rain_key,
    _sha,
)

HIMAWARI_BUCKET_URL = "https://noaa-himawari9.s3.amazonaws.com/"
HIMAWARI_PREFIX_ROOT = "AHI-L2-FLDK-Clouds"


def _read(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as res:
        return json.loads(res.read().decode("utf-8"))


def _fetch_xml(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml"})
    with urllib.request.urlopen(req, timeout=12) as res:
        return ET.fromstring(res.read())


def _vvpq_signature(rows: Any) -> dict:
    if not isinstance(rows, list):
        return {}
    candidates = [r for r in rows if str(r.get("icaoId", "")).upper() == "VVPQ"]
    candidates.sort(key=lambda r: int(r.get("obsTime") or 0), reverse=True)
    if not candidates:
        return {}
    row = candidates[0]
    return {
        "observed_epoch": int(row.get("obsTime") or 0) or None,
        "raw_payload_hash": _sha(row),
        "raw_observation": row.get("rawOb"),
    }


def _vrain_signatures(rows: Any) -> dict[str, dict]:
    if not isinstance(rows, list):
        return {}
    lat0, lat1, lon0, lon1 = PHU_QUOC_RAIN_BOUNDS
    out: dict[str, dict] = {}
    for row in rows:
        try:
            lat = float(row.get("lt"))
            lon = float(row.get("lg"))
        except (TypeError, ValueError):
            continue
        if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
            continue
        name = str(row.get("sn") or "").strip()
        if not name:
            continue
        key = _rain_key(name)
        out[key] = {
            "raw_payload_hash": _sha(row),
            "accumulation_mm": row.get("d"),
            "label": row.get("l"),
        }
    return out


def _latest_himawari_object(now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    found: list[dict] = []
    # Listing only metadata is cheap. Two hours is ample for the expected
    # ~10-minute source cadence while still tolerating publication delay.
    for hours_back in range(0, 3):
        stamp = now - timedelta(hours=hours_back)
        prefix = f"{HIMAWARI_PREFIX_ROOT}/{stamp:%Y/%m/%d/%H}"
        query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "max-keys": "1000"})
        root = _fetch_xml(HIMAWARI_BUCKET_URL + "?" + query)
        for content in root.findall(".//{*}Contents"):
            key = content.findtext("{*}Key") or ""
            if "/AHI-CHGT_" not in key or not key.endswith(".nc"):
                continue
            modified = content.findtext("{*}LastModified")
            found.append({"key": key, "last_modified": modified})
        if found:
            break
    if not found:
        return {}
    found.sort(key=lambda x: str(x.get("last_modified") or ""), reverse=True)
    return found[0]


def _previous_vvpq(payload: dict) -> dict:
    v = ((payload.get("atmosphere") or {}).get("vvpq") or {})
    return {
        "observed_at": v.get("observed_at"),
        "raw_payload_hash": v.get("raw_payload_hash"),
        "raw_observation": v.get("raw_observation"),
    }


def _previous_vrain(payload: dict) -> dict[str, dict]:
    stations = ((payload.get("rainfall") or {}).get("stations") or {})
    return {
        key: {
            "raw_payload_hash": value.get("raw_payload_hash"),
            "accumulation_mm": value.get("accumulation_mm"),
        }
        for key, value in stations.items()
    }


def _hashes_changed(current: dict[str, dict], previous: dict[str, dict]) -> bool:
    if not current:
        return False
    if not previous:
        return True
    for key, value in current.items():
        if key not in previous:
            return True
        if value.get("raw_payload_hash") != previous[key].get("raw_payload_hash"):
            return True
    return False


def watch(previous_groundtruth: dict, previous_nowcast: dict, only: str = "all") -> dict:
    if only not in {"all", "groundtruth", "himawari"}:
        raise ValueError(f"Unsupported source watch subset: {only}")
    checked_at = datetime.now(timezone.utc).isoformat()
    errors: dict[str, str] = {}

    current_vvpq: dict = {}
    current_vrain: dict[str, dict] = {}
    current_himawari: dict = {}

    if only in {"all", "groundtruth"}:
        try:
            current_vvpq = _vvpq_signature(_fetch_json(AWC_URL))
        except Exception as exc:
            errors["vvpq"] = f"{type(exc).__name__}: {exc}"

        try:
            current_vrain = _vrain_signatures(_fetch_json(VRAIN_CURRENT_URL))
        except Exception as exc:
            errors["vrain"] = f"{type(exc).__name__}: {exc}"

    if only in {"all", "himawari"}:
        try:
            current_himawari = _latest_himawari_object()
        except Exception as exc:
            errors["himawari"] = f"{type(exc).__name__}: {exc}"

    prev_vvpq = _previous_vvpq(previous_groundtruth)
    prev_vrain = _previous_vrain(previous_groundtruth)
    prev_himawari_key = previous_nowcast.get("latest_object")

    vvpq_changed = bool(
        current_vvpq
        and current_vvpq.get("raw_payload_hash")
        and current_vvpq.get("raw_payload_hash") != prev_vvpq.get("raw_payload_hash")
    )
    vrain_changed = _hashes_changed(current_vrain, prev_vrain)
    himawari_changed = bool(
        current_himawari.get("key")
        and current_himawari.get("key") != prev_himawari_key
    )

    return {
        "schema_version": "weather-source-watch-v1",
        "checked_at": checked_at,
        "status": "PASS" if not errors else "DEGRADED",
        "sources_probed": only,
        "groundtruth_changed": vvpq_changed or vrain_changed,
        "vvpq_changed": vvpq_changed,
        "vrain_changed": vrain_changed,
        "himawari_changed": himawari_changed,
        "current": {
            "vvpq": current_vvpq,
            "vrain": current_vrain,
            "himawari": current_himawari,
        },
        "previous": {
            "vvpq": prev_vvpq,
            "vrain": prev_vrain,
            "himawari": {"latest_object": prev_himawari_key},
        },
        "errors": errors,
        "policy": "Fetch metadata/compact JSON only; heavy processors run only when source identity changes.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-groundtruth", type=Path)
    parser.add_argument("--previous-nowcast", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=("all", "groundtruth", "himawari"), default="all")
    args = parser.parse_args()
    result = watch(_read(args.previous_groundtruth), _read(args.previous_nowcast), only=args.only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
