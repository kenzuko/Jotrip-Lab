"""Build a compact Weather source/product state manifest.

The manifest is metadata only. It lets consumers decide what changed without
opening or diffing large Weather products.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError):
        return None
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _max_iso(values: list[Any]) -> str | None:
    parsed=[d for d in (_parse(v) for v in values) if d is not None]
    return max(parsed).isoformat() if parsed else None


def build(dashboard: dict, groundtruth: dict, local_now: dict, nowcast: dict, ensemble: dict) -> dict:
    vvpq=((groundtruth.get("atmosphere") or {}).get("vvpq") or {})
    stations=((groundtruth.get("rainfall") or {}).get("stations") or {})
    rain_observed=[v.get("observed_at") for v in stations.values() if v.get("observed_at")]
    cycles=dashboard.get("source_cycles") or {}
    updated=_max_iso([
        dashboard.get("generated_at"),
        groundtruth.get("generated_at"),
        local_now.get("generated_at"),
        nowcast.get("generated_at"),
        nowcast.get("sampled_time"),
        ensemble.get("generated_at"),
    ])
    return {
        "schema_version":"weather-state-v1",
        "snapshot_id":dashboard.get("snapshot_id"),
        "updated_at":updated,
        "sources":{
            "groundtruth":{
                "product_generated_at":groundtruth.get("generated_at"),
                "vvpq_observed_at":vvpq.get("observed_at"),
                "vrain_latest_observed_at":_max_iso(rain_observed),
                "vrain_latest_checked_at":_max_iso([v.get("last_checked_at") or v.get("fetched_at") for v in stations.values()]),
            },
            "nowcast":{
                "sampled_time":nowcast.get("sampled_time"),
                "generated_at":nowcast.get("generated_at"),
                "source_id":nowcast.get("latest_object"),
            },
            "forecast":{
                "dashboard_generated_at":dashboard.get("generated_at"),
                "cycles":cycles,
            },
            "ensemble":{
                "run_time":ensemble.get("run_time"),
                "generated_at":ensemble.get("generated_at"),
            },
        },
        "products":{
            "local_now_generated_at":local_now.get("generated_at"),
            "dashboard_snapshot_id":dashboard.get("snapshot_id"),
        },
        "policy":{
            "fetch_time_is_not_observation_time":True,
            "source_cycles_are_independent":True,
            "last_known_good_allowed":True,
        },
    }


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--dashboard",type=Path,required=True)
    parser.add_argument("--groundtruth",type=Path,required=True)
    parser.add_argument("--local-now",type=Path,required=True)
    parser.add_argument("--nowcast",type=Path,required=True)
    parser.add_argument("--ensemble",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    payload=build(_read(args.dashboard),_read(args.groundtruth),_read(args.local_now),_read(args.nowcast),_read(args.ensemble))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
