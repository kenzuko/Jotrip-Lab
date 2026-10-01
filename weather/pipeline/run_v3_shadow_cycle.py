"""Run one Weather V3 shadow-learning cycle from derived receipts only.

Inputs are already-normalized/derived artifacts. No external source is fetched
here. The cycle:
- compares current and previous CMAX derived component receipts
- creates shadow ETA candidates
- opens verification events for points with a real verifier
- appends fresh ACTUAL verifier samples
- verifies pending predictions conservatively
- updates a rolling skill summary

The output never becomes production authority by itself.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from weather.processing.radar_motion_v3 import match_components, eta_candidates
from weather.processing.event_skill_v3 import build_events, verify_event, skill_summary


def _load(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fresh_verifier_observations(groundtruth: dict[str,Any]) -> list[dict[str,Any]]:
    rain=groundtruth.get("rainfall") or {}
    if rain.get("status")!="FRESH":
        return []
    rows=[]
    for station in (rain.get("stations") or {}).values():
        if station.get("data_class")!="ACTUAL":
            continue
        if station.get("rain_observed") not in {True,False}:
            continue
        if not station.get("observed_at") or not station.get("station_id"):
            continue
        rows.append({
            "anchor_id":station["station_id"],
            "observed_at":station["observed_at"],
            "rain_observed":bool(station["rain_observed"]),
            "freshness":"FRESH",
            "increment_mm":station.get("increment_mm"),
            "intensity_mm_h":station.get("rain_intensity_mm_h"),
        })
    return rows


def _merge_unique(existing: list[dict[str,Any]], incoming: list[dict[str,Any]], key_fields: tuple[str,...]):
    seen={tuple(row.get(k) for k in key_fields) for row in existing}
    out=list(existing)
    for row in incoming:
        key=tuple(row.get(k) for k in key_fields)
        if key not in seen:
            out.append(row); seen.add(key)
    return out


def run_cycle(current: dict[str,Any], previous: dict[str,Any], groundtruth: dict[str,Any],
              points: dict[str,Any], runtime: dict[str,Any], state: dict[str,Any]) -> dict[str,Any]:
    radar_cfg=runtime.get("radar") or {}
    threshold=int(radar_cfg.get("tracking_threshold_dbz",20))
    max_speed=float(radar_cfg.get("max_track_speed_kmh",120))
    impact=float(radar_cfg.get("impact_radius_km",15))
    horizon=int(radar_cfg.get("max_nowcast_minutes",120))

    tracking=match_components(previous,current,threshold_dbz=threshold,max_speed_kmh=max_speed) if previous else {
        "status":"NO_PREVIOUS_FRAME","threshold_dbz":threshold,"tracks":[]
    }
    candidates=eta_candidates(
        tracking, points.get("points") or {},
        impact_radius_km=impact, max_nowcast_minutes=horizon
    )

    verifier_by_point={}
    for point_id,anchor in ((runtime.get("verification") or {}).get("anchors") or {}).items():
        if point_id in (points.get("points") or {}):
            verifier_by_point[point_id]=anchor

    new_events=build_events(
        issued_at=current.get("observed_at") or datetime.now(timezone.utc).isoformat(),
        eta_candidates=candidates,
        verifier_by_point=verifier_by_point,
        source_snapshot_ref=current.get("observed_at"),
    )
    events=_merge_unique(state.get("events") or [],new_events,("event_id",))

    observations=_merge_unique(
        state.get("verifier_observations") or [],
        _fresh_verifier_observations(groundtruth),
        ("anchor_id","observed_at"),
    )

    now=datetime.now(timezone.utc)
    obs_cutoff=now-timedelta(hours=12)
    observations=[
        row for row in observations
        if (_dt(row.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc))>=obs_cutoff
    ]

    verified=[]
    for event in events:
        if (event.get("verification") or {}).get("status")=="VERIFIED":
            verified.append(event)
        else:
            verified.append(verify_event(event,observations))

    event_cutoff=now-timedelta(days=7)
    verified=[
        e for e in verified
        if (_dt(e.get("issued_at")) or datetime.min.replace(tzinfo=timezone.utc))>=event_cutoff
    ]

    skill=skill_summary(verified)
    minimum=int(radar_cfg.get("minimum_verified_events_for_public_eta",30))
    skill["minimum_verified_events_for_public_eta"]=minimum
    skill["promotion_ready"]=bool(
        skill.get("verified_event_count",0)>=minimum
        and runtime.get("public_ui_enabled") is True
        and radar_cfg.get("public_display_enabled") is True
        and radar_cfg.get("rights_gate_required_before_public_promotion") is False
    )

    return {
        "schema_version":"weather-v3-shadow-state-v1",
        "generated_at":now.isoformat(),
        "status":"SHADOW_ONLY",
        "production_authority":runtime.get("production_decision_authority","WEATHER_V2"),
        "public_ui_enabled":bool(runtime.get("public_ui_enabled",False)),
        "latest_radar_observed_at":current.get("observed_at"),
        "previous_radar_observed_at":previous.get("observed_at") if previous else None,
        "tracking":tracking,
        "eta_candidates":candidates,
        "events":verified,
        "verifier_observations":observations,
        "skill":skill,
        "safety":{
            "negative_radar_is_not_dry_ground_truth":True,
            "stale_actual_never_verifies_no_rain":True,
            "two_frame_eta_is_never_public_usable":True,
        }
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--current-radar",type=Path,required=True)
    ap.add_argument("--previous-radar",type=Path)
    ap.add_argument("--groundtruth",type=Path,required=True)
    ap.add_argument("--points",type=Path,default=Path("weather/config/points.json"))
    ap.add_argument("--runtime",type=Path,default=Path("weather/config/v3_runtime.json"))
    ap.add_argument("--state-in",type=Path)
    ap.add_argument("--state-out",type=Path,required=True)
    args=ap.parse_args()

    result=run_cycle(
        _load(args.current_radar),_load(args.previous_radar),_load(args.groundtruth),
        _load(args.points),_load(args.runtime),_load(args.state_in)
    )
    args.state_out.parent.mkdir(parents=True,exist_ok=True)
    args.state_out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "tracks":len(result["tracking"].get("tracks") or []),
        "eta_candidates":len(result["eta_candidates"]),
        "events":len(result["events"]),
        "verified_events":result["skill"]["verified_event_count"],
        "promotion_ready":result["skill"]["promotion_ready"],
        "output":str(args.state_out)
    },ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
