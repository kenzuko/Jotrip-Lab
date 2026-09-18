"""Build a tiny above-the-fold payload for Phu Quoc Weather V2.

The full dashboard, tide, AQI, ensemble matrices and map providers are not
required for first paint. This payload intentionally contains only:
- current local analysis
- verified actual anchors
- compact current model context
- next 24h compact forecast rows
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POINTS=("duong_dong","an_thoi","ganh_dau","rach_gia")
NAMES={"duong_dong":"Dương Đông","an_thoi":"An Thới","ganh_dau":"Gành Dầu","rach_gia":"Rạch Giá"}

def load(path: Path|None)->dict:
    if not path or not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def iso(v: Any)->datetime|None:
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None

def num(v: Any):
    try: return round(float(v),3)
    except Exception: return None

def compact_rows(point:dict, generated:datetime|None)->list[dict]:
    rows=[]
    for r in point.get("hours",[]) if isinstance(point.get("hours"),list) else []:
        t=iso(r.get("time_iso"))
        if not t: continue
        if generated and not (generated.timestamp()-3*3600 <= t.timestamp() <= generated.timestamp()+24*3600):
            continue
        rows.append({
            "t":r.get("time_iso"),
            "temp":num(r.get("temperature")),
            "wind":num(r.get("wind")),
            "gust":num(r.get("gust")),
            "rain":num(r.get("rain")),
            "wave":num(r.get("wave")),
            "hmax":num(r.get("wave_max")),
            "period":num(r.get("period")),
        })
    rows.sort(key=lambda x:x["t"] or "")
    return rows[:10]

def build(dashboard:dict, local:dict, ground:dict)->dict:
    dg=iso(dashboard.get("generated_at"))
    lg=iso(local.get("generated_at"))
    generated=max([x for x in (dg,lg) if x],default=datetime.now(timezone.utc))
    out={}
    for key in POINTS:
        dp=(dashboard.get("points") or {}).get(key,{})
        lp=(local.get("points") or {}).get(key,{})
        out[key]={
            "name":NAMES[key],
            "local":{
                "available":bool(lp),
                "temperature_c":num(lp.get("temperature_c")),
                "wind_kmh":num(lp.get("wind_kmh")),
                "rain_rate_mm_h":num((lp.get("rain") or {}).get("rain_rate_mm_h")),
                "rain_confidence":num((lp.get("rain") or {}).get("confidence")),
                "convection_score":num((lp.get("rain") or {}).get("convective_score")),
                "wave_hs_m":num(lp.get("wave_hs_m")),
                "temperature_class":(lp.get("temperature") or {}).get("data_class"),
                "wind_class":(lp.get("wind") or {}).get("data_class"),
                "rain_class":(lp.get("rain") or {}).get("data_class"),
                "marine_class":(lp.get("marine") or {}).get("data_class"),
            },
            "model":{
                "temperature_c":num(dp.get("temperature")),
                "wind_kmh":num(dp.get("wind")),
                "gust_kmh":num(dp.get("gust")),
                "rain_3h_mm":num(dp.get("rain")),
                "wave_hs_m":num(dp.get("wave")),
                "wave_hmax_m":num(dp.get("wave_max")),
                "period_s":num(dp.get("period")),
                "current_kmh":num(dp.get("current")),
            },
            "next24h":compact_rows(dp,dg),
        }
    v=(ground.get("atmosphere") or {}).get("vvpq",{})
    gauges=[]
    for s in ((ground.get("rainfall") or {}).get("stations") or {}).values():
        gauges.append({
            "name":s.get("station_name"),
            "lat":num(s.get("lat")),"lon":num(s.get("lon")),
            "accum_mm":num(s.get("accumulation_mm")),
            "increment_mm":num(s.get("increment_mm")),
            "increment_min":num(s.get("increment_window_minutes")),
            "observed_at":s.get("observed_at"),
            "qc":s.get("qc"),
        })
    return {
        "schema_version":"2.0",
        "generated_at":generated.isoformat(),
        "default_point":"duong_dong",
        "report_status":dashboard.get("report_status","UNAVAILABLE"),
        "forecast_generated_at":dashboard.get("generated_at"),
        "local_generated_at":local.get("generated_at"),
        "points":out,
        "actual":{
            "vvpq":{
                "status":v.get("status"),
                "observed_at":v.get("observed_at"),
                "temperature_c":num(v.get("temperature_c")),
                "wind_kmh":num(v.get("wind_speed_kmh")),
                "wind_direction_deg":num(v.get("wind_direction_deg")),
                "pressure_hpa":num(v.get("pressure_hpa")),
                "visibility_m":num(v.get("visibility_m")),
                "weather":v.get("weather"),
                "convective_cloud":bool(v.get("convective_cloud")),
            },
            "rain_gauges":gauges,
        },
        "source_state":{
            "vvpq":v.get("status","UNAVAILABLE"),
            "vrain":(ground.get("rainfall") or {}).get("status","UNAVAILABLE"),
            "local_engine":local.get("engine"),
        },
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dashboard",type=Path,required=True)
    p.add_argument("--local-now",type=Path)
    p.add_argument("--groundtruth",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    payload=build(load(a.dashboard),load(a.local_now),load(a.groundtruth))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    a.output.write_text(raw+"\n",encoding="utf-8")
    print(json.dumps({"bytes":len(raw.encode()),"generated_at":payload["generated_at"],"points":list(payload["points"])},ensure_ascii=False))
if __name__=="__main__": main()
