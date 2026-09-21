"""Build compact JoTrip 10-day regional forecast from GEFS/PQ Ensemble Local.

Public philosophy:
- D0-D3: keep 6-hour steps.
- D4-D10: publish 12-hour steps to avoid false precision.
- Regional temperature uses the median of point medians.
- Regional wind/rain risk uses the more adverse point in the region.
- Raw model members never appear in the public payload.
"""
from __future__ import annotations
import argparse, json, statistics
from pathlib import Path
from typing import Any

REGIONS={
    "north_northwest":{"name":"Gành Dầu - Cửa Cạn","points":["ganh_dau","cua_can"]},
    "central_west":{"name":"Dương Đông","points":["duong_dong"]},
    "east_northeast":{"name":"Bãi Thơm - Hàm Ninh","points":["bai_thom","ham_ninh"]},
    "south_southeast":{"name":"Bãi Sao - An Thới","points":["bai_sao","an_thoi"]},
}
POINT_NAMES={
    "duong_dong":"Dương Đông","cua_can":"Cửa Cạn","ganh_dau":"Gành Dầu",
    "bai_thom":"Bãi Thơm","ham_ninh":"Hàm Ninh","bai_sao":"Bãi Sao","an_thoi":"Biển An Thới - Mây Rút Ngoài"
}

def load(p:Path)->dict:
    return json.loads(p.read_text(encoding="utf-8"))

def num(v:Any):
    try:return float(v)
    except Exception:return None

def member_quantile(values:list[Any],q:float)->float|None:
    xs=sorted(x for v in values if (x:=num(v)) is not None)
    if not xs:return None
    if len(xs)==1:return xs[0]
    pos=max(0.0,min(1.0,q))*(len(xs)-1)
    lo=int(pos)
    hi=min(len(xs)-1,lo+1)
    if lo==hi:return xs[lo]
    w=pos-lo
    return xs[lo]*(1.0-w)+xs[hi]*w

def dist(row:dict,var:str)->dict:
    v=(row.get("variables") or {}).get(var) or {}
    return v.get("corrected") or v.get("raw") or {}

def public_lead(lead:int)->bool:
    if lead<=72:return lead%6==0
    return lead%12==0 and lead<=240

def confidence_score(lead:int,completion:float|None,calibration:str)->int:
    """Operational confidence index, not a probability of forecast correctness."""
    c=max(0.0,min(1.0,completion or 0.0))
    base=100.0*c
    if lead<=72:
        lead_penalty=0.0
    else:
        lead_penalty=min(35.0,35.0*(lead-72)/(240-72))
    cal=str(calibration).upper()
    calibration_penalty=8.0 if cal=="LEARNING" else (4.0 if cal=="PARTIAL" else 0.0)
    return round(max(35.0,min(95.0,base-lead_penalty-calibration_penalty)))

def confidence_band(score:int)->str:
    if score>=78:return "KHÁ"
    if score>=62:return "TRUNG BÌNH"
    return "THẬN TRỌNG"

def variability_score(wind_spread:float|None,rain_spread:float|None)->int:
    """Normalized ensemble spread index. Not a probability."""
    w=max(0.0,wind_spread or 0.0)/20.0
    r=max(0.0,rain_spread or 0.0)/10.0
    return round(100*min(1.0,max(w,r)))

def _point_nowcast(nowcast:dict|None,pid:str)->dict:
    if not nowcast:return {}
    p=(nowcast.get("points") or {}).get(pid) or {}
    sig=p.get("convective_signal") or {}
    motion=p.get("cloud_motion") or {}
    score=num(p.get("score"))
    if score is None: score=num(sig.get("score"))
    eta=num(motion.get("eta_minutes"))
    approaching=bool(motion.get("approaching"))
    level="LOW"
    if score is not None and score>=75: level="HIGH"
    elif score is not None and score>=50: level="ELEVATED"
    elif score is not None and score>=25: level="WATCH"
    if approaching and eta is not None and eta<=120:
        level="HIGH" if eta<=60 else "ELEVATED"
    return {
        "convective_score":score,
        "level":level,
        "motion_status":motion.get("status"),
        "source_sector":motion.get("source_sector"),
        "motion_heading":motion.get("motion_heading"),
        "motion_speed_kmh":num(motion.get("motion_speed_kmh")),
        "eta_minutes":eta,
        "approaching":approaching,
        "tracking_confidence":motion.get("tracking_confidence"),
    }

def build(ensemble:dict,nowcast:dict|None=None)->dict:
    points=ensemble.get("points") or {}
    by_point={pid:{int(r.get("lead_hours")):r for r in rows if r.get("lead_hours") is not None}
              for pid,rows in points.items() if isinstance(rows,list)}
    completion=num(ensemble.get("completion_ratio"))
    cal=str(ensemble.get("calibration_status") or "LEARNING")
    out_regions={}
    for rid,meta in REGIONS.items():
        rows=[]
        all_leads=sorted({lead for pid in meta["points"] for lead in by_point.get(pid,{}) if public_lead(lead)})
        for lead in all_leads:
            items=[]
            for pid in meta["points"]:
                row=by_point.get(pid,{}).get(lead)
                if not row: continue
                t,w,r=dist(row,"temperature"),dist(row,"wind"),dist(row,"rain")
                wind_var=(row.get("variables") or {}).get("wind") or {}
                wind_q10=num(w.get("q10"))
                if wind_q10 is None:
                    wind_q10=member_quantile(wind_var.get("member_values_corrected") or [],.10)
                items.append({
                    "point_id":pid,"point_name":POINT_NAMES.get(pid,pid),"valid_time":row.get("valid_time"),
                    "members":row.get("member_count"),
                    "temp_q50":num(t.get("q50")),"temp_spread":num(t.get("spread")),
                    "wind_q10":wind_q10,"wind_q50":num(w.get("q50")),"wind_q90":num(w.get("q90")),"wind_spread":num(w.get("spread")),
                    "wind_prob":num(w.get("exceedance_probability")),
                    "rain_q50":num(r.get("q50")),"rain_q90":num(r.get("q90")),"rain_spread":num(r.get("spread")),
                    "rain_prob":num(r.get("exceedance_probability")),
                })
            if not items: continue
            temps=[x["temp_q50"] for x in items if x["temp_q50"] is not None]
            # Risk-first regional aggregation: central temperature, adverse wind/rain tail.
            wind_driver=max(items,key=lambda x:(x["wind_prob"] or 0,x["wind_q90"] or 0))
            rain_driver=max(items,key=lambda x:(x["rain_prob"] or 0,x["rain_q90"] or 0))
            vol_driver=max(items,key=lambda x:max((x["wind_spread"] or 0)/10,(x["rain_spread"] or 0)/4))
            conf_score=confidence_score(lead,completion,cal)
            var_score=variability_score(vol_driver["wind_spread"],vol_driver["rain_spread"])
            now_items=[(pid,_point_nowcast(nowcast,pid)) for pid in meta["points"]]
            now_items=[x for x in now_items if x[1]]
            now_driver=max(
                now_items,
                key=lambda x:(
                    1 if x[1].get("approaching") else 0,
                    -(x[1].get("eta_minutes") if x[1].get("eta_minutes") is not None else 999),
                    x[1].get("convective_score") or 0,
                ),
                default=(None,{})
            )
            near_now=now_driver[1] if lead<=12 else {}
            near_level=near_now.get("level") if near_now else None
            rows.append({
                "lead_hours":lead,
                "valid_time":next((x["valid_time"] for x in items if x["valid_time"]),None),
                "confidence_score":conf_score,
                "confidence_band":confidence_band(conf_score),
                "variability_score":var_score,
                "temperature_c":round(statistics.median(temps),2) if temps else None,
                "wind_q10_kmh":round(wind_driver["wind_q10"],2) if wind_driver["wind_q10"] is not None else None,
                "wind_kmh":round(wind_driver["wind_q50"],2) if wind_driver["wind_q50"] is not None else None,
                "wind_q90_kmh":round(wind_driver["wind_q90"],2) if wind_driver["wind_q90"] is not None else None,
                "wind_prob_30":wind_driver["wind_prob"],
                "rain_mm":round(rain_driver["rain_q50"],2) if rain_driver["rain_q50"] is not None else None,
                "rain_q90_mm":round(rain_driver["rain_q90"],2) if rain_driver["rain_q90"] is not None else None,
                "rain_prob_5":rain_driver["rain_prob"],
                "wind_spread":vol_driver["wind_spread"],
                "rain_spread":vol_driver["rain_spread"],
                "risk_driver":{
                    "wind":wind_driver["point_name"],
                    "rain":rain_driver["point_name"],
                    "variability":vol_driver["point_name"],
                    "nowcast":POINT_NAMES.get(now_driver[0],now_driver[0]) if near_now else None,
                },
                "nowcast_overlay":{
                    "applies":bool(near_now),
                    "scope":"D0_12H_OPERATIONAL_CONTEXT_ONLY",
                    "level":near_level,
                    **near_now,
                    "note":"Observed-satellite short-range context. Raw ensemble q50/q90/probabilities above are not rewritten.",
                } if near_now else None,
                "members_min":min([x["members"] for x in items if x["members"] is not None],default=None),
                "point_count":len(items),
            })
        out_regions[rid]={"name":meta["name"],"points":[POINT_NAMES.get(p,p) for p in meta["points"]],"rows":rows}
    return {
        "schema_version":"1.1",
        "product":"JOTRIP_FORECAST_10D_REGIONAL",
        "run_time":ensemble.get("run_time"),
        "generated_at":ensemble.get("generated_at"),
        "horizon_hours":min(240,int(ensemble.get("horizon_hours") or 0)),
        "source":"PQ_ENSEMBLE_LOCAL_V1 / NOAA GEFS",
        "ensemble_completion_ratio":completion,
        "calibration_status":cal,
        "calibration_ready_groups":ensemble.get("calibration_ready_groups",0),
        "calibration_total_groups":ensemble.get("calibration_total_groups",0),
        "cadence":{"d0_d3_hours":6,"d4_d10_hours":12},
        "regions":out_regions,
        "note":"D0-D3 shown every 6h; D4-D10 every 12h. D0-12h may carry a Himawari nowcast overlay for operational context; raw ensemble q50/q90/probabilities are never rewritten. confidence_score is an operational confidence index, not probability of correctness; variability_score is normalized ensemble spread, not hazard probability.",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ensemble",type=Path,required=True)
    p.add_argument("--nowcast",type=Path,required=False)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    nowcast=load(a.nowcast) if a.nowcast and a.nowcast.exists() else None
    payload=build(load(a.ensemble),nowcast)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    a.output.write_text(raw+"\n",encoding="utf-8")
    print(json.dumps({"bytes":len(raw.encode()),"horizon_hours":payload["horizon_hours"],"rows":{k:len(v["rows"]) for k,v in payload["regions"].items()}},ensure_ascii=False))
if __name__=="__main__":main()
