"""Weather V3 shadow event records and conservative verification."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib, json
from typing import Any, Iterable

def _dt(value):
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()

def build_events(*, issued_at: str, eta_candidates: Iterable[dict[str,Any]],
                 verifier_by_point: dict[str,str], source_snapshot_ref: str|None=None):
    issued=_dt(issued_at)
    if not issued:
        raise ValueError("issued_at must be ISO timestamp")
    events=[]
    for candidate in eta_candidates:
        point_id=str(candidate["point_id"])
        eta=int(candidate["eta_minutes"])
        center=issued+timedelta(minutes=eta)
        half=15 if eta<=60 else 25
        start,end=center-timedelta(minutes=half),center+timedelta(minutes=half)
        stable={"issued_at":_iso(issued),"point_id":point_id,"track_id":candidate.get("track_id"),
                "eta_minutes":eta,"window_start":_iso(start),"window_end":_iso(end)}
        event_id="WXV3-"+hashlib.sha1(json.dumps(stable,sort_keys=True).encode()).hexdigest()[:14].upper()
        anchor=verifier_by_point.get(point_id)
        events.append({
            "schema_version":"weather-v3-event-v1","event_id":event_id,
            "status":"SHADOW_PENDING_VERIFICATION","issued_at":_iso(issued),
            "target_point_id":point_id,
            "forecast":{"signal":"RADAR_ECHO_PATH_CANDIDATE","eta_minutes":eta,
                        "window":candidate.get("window"),
                        "verification_window_start":_iso(start),"verification_window_end":_iso(end),
                        "closest_approach_km":candidate.get("closest_approach_km"),
                        "max_dbz_current":candidate.get("max_dbz_current"),
                        "confidence":candidate.get("confidence") or "LOW_SHADOW",
                        "public_usable":False},
            "evidence":{"radar_track_id":candidate.get("track_id"),"radar_source":"iweather_radar_cmax",
                        "source_snapshot_ref":source_snapshot_ref,
                        "touches_invalid_pixels":candidate.get("touches_invalid_pixels")},
            "verification":{"anchor_id":anchor,"status":"PENDING" if anchor else "NO_VERIFIER",
                            "result":None,"first_rain_at":None,"timing_error_minutes":None}
        })
    return events

def verify_event(event: dict[str,Any], observations: Iterable[dict[str,Any]], *, max_gap_minutes:int=20):
    out=json.loads(json.dumps(event))
    verifier=(out.get("verification") or {}).get("anchor_id")
    if not verifier:
        out["verification"]["status"]="NO_VERIFIER"
        return out
    start,end=_dt(out["forecast"]["verification_window_start"]),_dt(out["forecast"]["verification_window_end"])
    issued=_dt(out["issued_at"]); eta=int(out["forecast"]["eta_minutes"])
    predicted=issued+timedelta(minutes=eta)
    usable=[]
    for row in observations:
        if row.get("anchor_id")!=verifier: continue
        at=_dt(row.get("observed_at"))
        if not at or at<start or at>end: continue
        if row.get("freshness") not in {"FRESH","PASS","CURRENT"}: continue
        if row.get("rain_observed") not in {True,False}: continue
        usable.append((at,bool(row["rain_observed"])))
    usable.sort(key=lambda x:x[0])
    rainy=[at for at,flag in usable if flag]
    if rainy:
        first=rainy[0]
        out["verification"].update({"status":"VERIFIED","result":"HIT","first_rain_at":_iso(first),
            "timing_error_minutes":round((first-predicted).total_seconds()/60,1),
            "usable_sample_count":len(usable)})
        out["status"]="SHADOW_VERIFIED"
        return out
    if len(usable)<2:
        out["verification"].update({"status":"INSUFFICIENT_ACTUAL_COVERAGE","result":None,
                                    "usable_sample_count":len(usable)})
        return out
    max_gap=max((b[0]-a[0]).total_seconds()/60 for a,b in zip(usable,usable[1:]))
    edge_start=(usable[0][0]-start).total_seconds()/60
    edge_end=(end-usable[-1][0]).total_seconds()/60
    if max_gap<=max_gap_minutes and edge_start<=max_gap_minutes and edge_end<=max_gap_minutes:
        out["verification"].update({"status":"VERIFIED","result":"FALSE_ALARM","usable_sample_count":len(usable),
                                    "max_gap_minutes":round(max_gap,1)})
        out["status"]="SHADOW_VERIFIED"
    else:
        out["verification"].update({"status":"INSUFFICIENT_ACTUAL_COVERAGE","result":None,
                                    "usable_sample_count":len(usable),"max_gap_minutes":round(max_gap,1)})
    return out

def skill_summary(events):
    verified=[e for e in events if (e.get("verification") or {}).get("status")=="VERIFIED"]
    hits=[e for e in verified if e["verification"].get("result")=="HIT"]
    false_alarms=[e for e in verified if e["verification"].get("result")=="FALSE_ALARM"]
    timing=[float(e["verification"]["timing_error_minutes"]) for e in hits
            if e["verification"].get("timing_error_minutes") is not None]
    return {"schema_version":"weather-v3-skill-summary-v1","verified_event_count":len(verified),
            "hit_count":len(hits),"false_alarm_count":len(false_alarms),
            "hit_rate_among_verified_predictions":round(len(hits)/len(verified),4) if verified else None,
            "mean_absolute_timing_error_minutes":round(sum(abs(x) for x in timing)/len(timing),1) if timing else None,
            "promotion_ready":False,
            "promotion_note":"Requires minimum verified events plus coverage and rights checks."}
