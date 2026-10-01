"""Build a UI-ready but disabled Weather V3 preview contract.

This contract intentionally contains no external source URLs and no raw radar
image data. It is safe to wire into a dormant UI adapter while Weather V2
remains the public authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

def _load(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def _radar_coverage(point: dict[str, Any]) -> str:
    ring=(point.get("rings") or {}).get("15km") or {}
    frac=ring.get("valid_fraction")
    if frac is None:
        return "UNKNOWN"
    if frac >= 0.8:
        return "GOOD"
    if frac >= 0.4:
        return "PARTIAL"
    if frac > 0:
        return "LIMITED"
    return "NO_VALID_PIXELS"

def build(runtime: dict[str,Any], radar: dict[str,Any], groundtruth: dict[str,Any],
          satellite: dict[str,Any], events: dict[str,Any] | None = None) -> dict[str,Any]:
    points={}
    radar_points=radar.get("points") or {}
    sat_points=satellite.get("points") or {}
    rain_stations=((groundtruth.get("rainfall") or {}).get("stations") or {})

    point_ids=sorted(set(radar_points)|set(sat_points)|set(rain_stations))
    event_rows=(events or {}).get("events") or []
    events_by_point={}
    for event in event_rows:
        events_by_point.setdefault(event.get("target_point_id"),[]).append(event)

    for point_id in point_ids:
        rp=radar_points.get(point_id) or {}
        sp=sat_points.get(point_id) or {}
        rain=rain_stations.get(point_id) or {}
        ring15=(rp.get("rings") or {}).get("15km") or {}
        ring30=(rp.get("rings") or {}).get("30km") or {}

        actual_rain=None
        if rain.get("data_class")=="ACTUAL" and (groundtruth.get("rainfall") or {}).get("status")=="FRESH":
            if rain.get("rain_observed") in {True,False}:
                actual_rain={
                    "evidence":"ACTUAL",
                    "observed":bool(rain.get("rain_observed")),
                    "observed_at":rain.get("observed_at"),
                    "intensity_mm_h":rain.get("rain_intensity_mm_h"),
                    "increment_mm":rain.get("increment_mm"),
                }

        candidates=[]
        for event in events_by_point.get(point_id,[]):
            fc=event.get("forecast") or {}
            candidates.append({
                "window":fc.get("window"),
                "eta_minutes":fc.get("eta_minutes"),
                "closest_approach_km":fc.get("closest_approach_km"),
                "confidence":fc.get("confidence"),
                "public_usable":False,
            })

        points[point_id]={
            "actual_rain":actual_rain,
            "radar":{
                "evidence":"REMOTE_OBSERVED",
                "observed_at":radar.get("observed_at"),
                "coverage":_radar_coverage(rp) if rp else "UNAVAILABLE",
                "center_dbz":rp.get("center_dbz"),
                "max_dbz_15km":ring15.get("max_dbz"),
                "max_dbz_30km":ring30.get("max_dbz"),
                "valid_fraction_15km":ring15.get("valid_fraction"),
                "negative_evidence_is_weak":True,
            } if rp else None,
            "satellite":{
                "evidence":"REMOTE_OBSERVED",
                "observed_at":satellite.get("sampled_time"),
                "convective_score":sp.get("score"),
                "level":sp.get("level"),
                "cloud_top_temp_c":sp.get("cold_cloud_top_temp_c"),
                "cloud_motion":sp.get("cloud_motion"),
            } if sp else None,
            "nowcast":{
                "status":"LEARNING",
                "public_usable":False,
                "candidates":candidates,
            },
        }

    return {
        "schema_version":"weather-v3-ui-preview-v1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "status":"PREPARED_DISABLED",
        "public_ui_enabled":bool(runtime.get("public_ui_enabled",False)),
        "public_authority":runtime.get("production_decision_authority","WEATHER_V2"),
        "promotion_gate":{
            "v2_ui_update_must_finish_first":True,
            "rights_gate_required_for_new_public_sources":True,
            "minimum_verified_events_for_public_eta":((runtime.get("radar") or {}).get("minimum_verified_events_for_public_eta")),
        },
        "display_contract":{
            "render_when_public_ui_enabled":False,
            "never_label_remote_or_derived_as_actual":True,
            "never_turn_missing_into_zero":True,
            "hide_source_urls_from_end_user":True,
        },
        "points":points,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime",type=Path,default=Path("weather/config/v3_runtime.json"))
    ap.add_argument("--radar",type=Path,required=True)
    ap.add_argument("--groundtruth",type=Path,required=True)
    ap.add_argument("--satellite",type=Path,required=True)
    ap.add_argument("--events",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    payload=build(_load(args.runtime),_load(args.radar),_load(args.groundtruth),_load(args.satellite),_load(args.events))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":payload["status"],"public_ui_enabled":payload["public_ui_enabled"],
                      "points":len(payload["points"]),"output":str(args.output)},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
