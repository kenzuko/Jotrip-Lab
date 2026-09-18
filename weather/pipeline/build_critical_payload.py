"""Build compact first-paint payload for Phu Quoc Weather V2.

V2 keeps feature parity without forcing every heavy source into first paint.
This payload carries summaries for:
- operational status / source health
- current local analysis and model context
- verified actual anchors
- 24h compact forecast
- AQI summary
- tide summary
- Himawari nowcast summary
- ensemble probability summary when available

Heavy full tables, charts, provider maps and member matrices remain deferred.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weather.points import POINT_NAMES

POINTS=tuple(POINT_NAMES)
NAMES=POINT_NAMES
ISLAND_WATCH_ORDER=("duong_dong","cua_can","ganh_dau","bai_thom","ham_ninh","bai_sao","an_thoi")

def load(path: Path|None)->dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def iso(v: Any)->datetime|None:
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def num(v: Any):
    try:
        return round(float(v),3)
    except Exception:
        return None

def compact_rows(point:dict, generated:datetime|None)->list[dict]:
    rows=[]
    raw=point.get("hours",[]) if isinstance(point.get("hours"),list) else []
    for r in raw:
        t=iso(r.get("time_iso"))
        if not t:
            continue
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

def compact_outlook(point:dict)->list[dict]:
    out=[]
    for x in point.get("daily_outlook",[]) if isinstance(point.get("daily_outlook"),list) else []:
        if not isinstance(x,dict):
            continue
        out.append({
            "d":x.get("day_offset"),
            "date":x.get("date"),
            "wind_max":num(x.get("wind_max")),
            "gust_max":num(x.get("gust_max")),
            "hs_max":num(x.get("hs_max")),
            "hmax_max":num(x.get("hmax_max")),
            "rain_total":num(x.get("rain_total")),
        })
    return out[-3:]

def compact_aqi(aqi:dict,key:str)->dict:
    p=(aqi.get("points") or {}).get(key,{})
    return {
        "status":aqi.get("status","UNAVAILABLE"),
        "sampled_time":p.get("sampled_time") or aqi.get("sampled_time"),
        "aqi_us":num(p.get("aqi_us")),
        "category":p.get("category"),
        "aqi_source":p.get("aqi_source"),
        "source_city":p.get("source_city") or p.get("iqair_city"),
        "pm25_ugm3":num(p.get("pm25_ugm3")),
        "pm10_ugm3":num(p.get("pm10_ugm3")),
        "model_aqi_us":num(p.get("model_aqi_us")),
        "divergence":num(p.get("source_divergence_aqi")),
    }

def compact_tide(tide:dict,key:str)->dict:
    p=(tide.get("points") or {}).get(key,{})
    def turn(x:Any):
        if not isinstance(x,dict):
            return None
        return {"type":x.get("type"),"time":x.get("time_iso"),"height_m":num(x.get("height_m"))}
    return {
        "status":p.get("status") or tide.get("status","UNAVAILABLE"),
        "generated_at":tide.get("generated_at"),
        "height_m":num(p.get("current_height_m")),
        "current_time":p.get("current_time"),
        "trend":p.get("trend"),
        "range_24h_m":num(p.get("range_24h_m")),
        "next_high":turn(p.get("next_high")),
        "next_low":turn(p.get("next_low")),
        "next_turn":turn(p.get("next_turn")),
        "source":tide.get("source"),
        "height_reference":tide.get("height_reference"),
    }

def compact_nowcast(nowcast:dict,key:str)->dict:
    p=(nowcast.get("points") or {}).get(key,{})
    sig=p.get("convective_signal") or {}
    return {
        "status":nowcast.get("status","UNAVAILABLE"),
        "sampled_time":nowcast.get("sampled_time"),
        "source":nowcast.get("source"),
        "cloud_top_cold_c":num(p.get("regional_cold_cloud_top_temp_c")),
        "cloud_top_high_m":num(p.get("regional_high_cloud_top_height_m")),
        "cooling_c_per_20m":num(p.get("cooling_c_per_20m_proxy")),
        "convective_score":num(sig.get("score")),
        "convective_level":sig.get("level"),
        "lightning":p.get("lightning_observed") or (nowcast.get("lightning_observed") or {}).get("status"),
    }

def compact_ensemble(ensemble:dict,key:str)->dict:
    rows=(ensemble.get("points") or {}).get(key,[])
    out=[]
    if isinstance(rows,list):
        for row in rows:
            lead=row.get("lead_hours")
            try:
                lead_num=int(lead)
            except Exception:
                continue
            if lead_num <= 0 or lead_num > 72:
                continue
            vars=row.get("variables") or {}
            item={"lead_hours":lead,"valid_time":row.get("valid_time"),"members":row.get("member_count")}
            for name in ("wind","rain","temperature"):
                v=(vars.get(name) or {}).get("corrected") or (vars.get(name) or {}).get("raw") or {}
                item[name]={
                    "q50":num(v.get("q50")),
                    "q90":num(v.get("q90")),
                    "q95":num(v.get("q95")),
                    "spread":num(v.get("spread")),
                    "prob":num(v.get("exceedance_probability")),
                    "threshold":num(v.get("exceedance_threshold")),
                    "members":v.get("member_count"),
                }
            out.append(item)
    return {
        "status":ensemble.get("status","UNAVAILABLE"),
        "readiness":ensemble.get("readiness","UNAVAILABLE"),
        "source":ensemble.get("source"),
        "run_time":ensemble.get("run_time"),
        "completion_ratio":num(ensemble.get("completion_ratio")),
        "calibration_status":ensemble.get("calibration_status","LEARNING"),
        "rows":out,
    }

def build(dashboard:dict, local:dict, ground:dict, aqi:dict|None=None, tide:dict|None=None,
          nowcast:dict|None=None, ensemble:dict|None=None)->dict:
    aqi=aqi or {}
    tide=tide or {}
    nowcast=nowcast or {}
    ensemble=ensemble or {}
    dg=iso(dashboard.get("generated_at"))
    lg=iso(local.get("generated_at"))
    generated=max([x for x in (dg,lg) if x],default=datetime.now(timezone.utc))

    out={}
    for key in POINTS:
        dp=(dashboard.get("points") or {}).get(key,{})
        lp=(local.get("points") or {}).get(key,{})
        out[key]={
            "name":NAMES[key],
            "status":dp.get("status"),
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
                "wave_regional_hs_m":num(dp.get("wave_regional_hs")),
                "marine_sampled_time":dp.get("marine_sampled_time"),
                "wave_max_method":dp.get("wave_max_method"),
                "long_range_status":dp.get("long_range_status"),
            },
            "aqi":compact_aqi(aqi,key),
            "tide":compact_tide(tide,key),
            "nowcast":compact_nowcast(nowcast,key),
            "ensemble":compact_ensemble(ensemble,key),
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
            "rain_observed":s.get("rain_observed"),
            "rain_intensity_mm_h":num(s.get("rain_intensity_mm_h")),
            "increment_qc":s.get("increment_qc"),
            "observed_at":s.get("observed_at"),
            "qc":s.get("qc"),
        })

    sources={}
    for k,vv in (dashboard.get("sources") or {}).items():
        sources[k]={"status":vv.get("status"),"detail":vv.get("detail")}

    # Public-facing source descriptions. Internal diagnostics stay in the engine,
    # but the website should explain each source in normal Vietnamese.
    if "ECMWF" in sources:
        sources["ECMWF"]["detail"]="ECMWF cung cấp nền khí quyển và sóng cho dự báo dài ngày. JoTrip dùng nguồn này để đối chiếu, không công bố nguyên bản như dự báo chính."
    if "ICON" in sources:
        sources["ICON"]["detail"]="ICON của DWD được dùng như một nguồn khí quyển độc lập để so sánh với các mô hình khác và phát hiện khi các kịch bản bắt đầu lệch nhau."
    if "COPERNICUS" in sources:
        sources["COPERNICUS"]["detail"]="Copernicus Marine cung cấp sóng và dòng chảy quanh Phú Quốc. Số liệu biển được ghép theo điểm và thời gian gần nhất phù hợp."

    def ready_status(value:Any, *, partial_ok:bool=False)->str:
        text=str(value or "").upper()
        if text in {"PASS","FRESH","READY","POINT_NUMERIC_READY","MEMBER_MATRIX_READY","LIVE"}:
            return "PASS"
        if partial_ok and text in {"PARTIAL","PARTIAL_ENSEMBLE","DEGRADED"}:
            return "PARTIAL"
        return "FAIL"

    ens_ratio=num(ensemble.get("completion_ratio"))
    sources["GEFS"]={
        "status":ready_status(ensemble.get("readiness"),partial_ok=True),
        "detail":f"NOAA GEFS D0-D10 · tối đa 31 thành viên · dữ liệu hiện đủ {round((ens_ratio or 0)*100)}%. JoTrip tiếp tục đối chiếu và hiệu chỉnh dự báo địa phương bằng quan trắc thực tế trên đảo."
    }
    sources["VVPQ"]={
        "status":ready_status(v.get("status")),
        "detail":"METAR sân bay Phú Quốc là một trong các mốc quan trắc thực tế để JoTrip kiểm tra nhiệt độ, gió, tầm nhìn và trạng thái thời tiết hiện tại."
    }
    sources["VRAIN"]={
        "status":ready_status((ground.get("rainfall") or {}).get("status")),
        "detail":f"Mưa đo thực tế tại {len(gauges)} trạm công khai trên đảo. JoTrip theo dõi mức tăng giữa các lần cập nhật để ước tính cường độ mưa gần hiện tại."
    }
    sources["HIMAWARI"]={
        "status":ready_status(nowcast.get("status")),
        "detail":"Himawari-9 giúp theo dõi mây đối lưu quanh Phú Quốc qua nhiệt độ đỉnh mây, độ cao đỉnh mây và xu hướng phát triển trong khoảng 20 phút."
    }
    sources["AQI"]={
        "status":ready_status(aqi.get("status"),partial_ok=True),
        "detail":"IQAir được ưu tiên khi có điểm đo phù hợp; CAMS được dùng làm nguồn tham chiếu cho PM2.5, PM10 và chất lượng không khí khu vực."
    }
    sources["TRIỀU"]={
        "status":ready_status(tide.get("status"),partial_ok=True),
        "detail":"Triều được tính từ FES2014/Copernicus. Đây là số liệu mô hình, không phải phép đo tại trạm và không thay mực nước hải đồ cảng."
    }
    gaps=[]
    for g in dashboard.get("gaps") or []:
        name=str(g.get("name") or "")
        detail=str(g.get("detail") or "")
        if name=="D4-D10 ensemble consensus":
            gaps.append({
                "name":"Độ đồng thuận nhiều mô hình từ ngày 4 đến ngày 10",
                "detail":"GEFS đã có đủ 10 ngày, nhưng dự báo tổ hợp dài hạn từ các họ mô hình khác vẫn chưa được tích hợp đầy đủ. Vì vậy từ ngày 4 trở đi hệ thống chủ động hạ mức tin cậy."
            })
        elif name=="Hmax trực tiếp":
            gaps.append({
                "name":"Sóng lớn Hmax",
                "detail":"Nguồn ECMWF Open Data hiện chưa cung cấp trực tiếp Hmax cho chuỗi dữ liệu này. Khi cần, JoTrip ước tính Hmax từ Hs bằng phương pháp thống kê và luôn ghi rõ đây là giá trị ước tính."
            })
        elif name=="Nowcast offshore":
            gaps.append({
                "name":"Quan sát dông ngoài khơi",
                "detail":"Chưa có lớp radar/sét ngoài khơi đủ ổn định cho toàn vùng biển quanh Phú Quốc."
            })
        else:
            gaps.append({"name":name or "Phần còn thiếu","detail":detail})

    return {
        "schema_version":"2.1",
        "generated_at":generated.isoformat(),
        "default_point":"duong_dong",
        "island_watch_order":[p for p in ISLAND_WATCH_ORDER if p in out],
        "primary_points":[p for p in ("duong_dong","an_thoi","ganh_dau","rach_gia") if p in out],
        "report_status":dashboard.get("report_status","UNAVAILABLE"),
        "snapshot_id":dashboard.get("snapshot_id"),
        "git_commit_sha":dashboard.get("git_commit_sha"),
        "decision":dashboard.get("decision","NOT_ISSUED"),
        "headline":dashboard.get("headline"),
        "next_review":dashboard.get("next_review"),
        "completeness":num(dashboard.get("completeness")),
        "confidence":num(dashboard.get("confidence")),
        "data_mode":dashboard.get("data_mode"),
        "public_forecast":"JOTRIP_ENSEMBLE_LOCAL",
        "local_generated_at":local.get("generated_at"),
        "source_cycles":dashboard.get("source_cycles") or {},
        "sources":sources,
        "gaps":gaps,
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
            "aqi":aqi.get("status","UNAVAILABLE"),
            "tide":tide.get("status","UNAVAILABLE"),
            "nowcast":nowcast.get("status","UNAVAILABLE"),
            "ensemble":ensemble.get("status","UNAVAILABLE"),
            "local_engine":local.get("engine"),
        },
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dashboard",type=Path,required=True)
    p.add_argument("--local-now",type=Path)
    p.add_argument("--groundtruth",type=Path)
    p.add_argument("--aqi",type=Path)
    p.add_argument("--tide",type=Path)
    p.add_argument("--nowcast",type=Path)
    p.add_argument("--ensemble",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    payload=build(load(a.dashboard),load(a.local_now),load(a.groundtruth),load(a.aqi),load(a.tide),load(a.nowcast),load(a.ensemble))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    a.output.write_text(raw+"\n",encoding="utf-8")
    print(json.dumps({"bytes":len(raw.encode()),"generated_at":payload["generated_at"],"points":list(payload["points"])},ensure_ascii=False))

if __name__=="__main__":
    main()
