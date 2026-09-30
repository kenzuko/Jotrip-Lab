"""Human-readable weather interpretation for JoTrip Weather.

The layer translates evidence without changing it:
ACTUAL stays tied to observation time/scope; feels-like is DERIVED; and rain
duration is only stated when nowcast supplies a usable exit time.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Any
from weather.points import POINT_NAMES

FRESH_ACTUAL_MINUTES=90.0
LAST_OBSERVED_MINUTES=360.0

def _num(v:Any)->float|None:
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None

def _time(v:Any)->datetime|None:
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def _age_minutes(observed_at:Any,generated_at:datetime)->float|None:
    d=_time(observed_at)
    return max(0.0,(generated_at-d).total_seconds()/60.0) if d else None

def relative_humidity_percent(temperature_c:float|None,dewpoint_c:float|None)->float|None:
    t,td=_num(temperature_c),_num(dewpoint_c)
    if t is None or td is None:return None
    td=min(td,t)
    a,b=17.625,243.04
    rh=100.0*math.exp((a*td)/(b+td)-(a*t)/(b+t))
    return round(max(0.0,min(100.0,rh)),1)

def heat_index_c(temperature_c:float|None,humidity_percent:float|None)->float|None:
    t_c,rh=_num(temperature_c),_num(humidity_percent)
    if t_c is None or rh is None:return None
    if t_c<26.7 or rh<40.0:return round(t_c,1)
    t=t_c*9/5+32
    hi=(-42.379+2.04901523*t+10.14333127*rh-0.22475541*t*rh
        -0.00683783*t*t-0.05481717*rh*rh+0.00122874*t*t*rh
        +0.00085282*t*rh*rh-0.00000199*t*t*rh*rh)
    if rh<13 and 80<=t<=112:
        hi-=((13-rh)/4)*math.sqrt(max(0.0,(17-abs(t-95))/17))
    elif rh>85 and 80<=t<=87:
        hi+=((rh-85)/10)*((87-t)/5)
    return round((hi-32)*5/9,1)

def rain_intensity_label(rate_mm_h:float|None)->str|None:
    r=_num(rate_mm_h)
    if r is None:return None
    if r<=0.05:return "không mưa đáng kể"
    if r<2.5:return "mưa rào nhẹ"
    if r<7.5:return "mưa vừa"
    return "mưa lớn"

def _comfort_label(t,td,feels)->str|None:
    t,td,feels=_num(t),_num(td),_num(feels)
    if t is None:return None
    if feels is not None and feels>=43:return "Rất nóng và rất oi"
    if feels is not None and feels>=38:return "Rất nóng và oi"
    if td is not None:
        if td>=27:return "Nóng và rất oi" if t>=29 else "Rất oi"
        if td>=25:return "Nóng và khá oi" if t>=29 else "Khá oi"
        if td>=23:return "Ấm và ẩm" if t<29 else "Nóng và hơi oi"
        if td>=20:return "Hơi ẩm"
    if t>=32:return "Nóng"
    if t>=29:return "Ấm"
    return "Khá dễ chịu"

def _comfort_reason(t,td,rh,feels,wind)->str|None:
    t,td,rh,feels,wind=map(_num,(t,td,rh,feels,wind))
    if t is None:return None
    parts=[]
    if feels is not None and feels>=t+2 and (rh or 0)>=65:
        parts.append("Độ ẩm cao làm cơ thể cảm thấy nóng hơn nhiệt độ đo được")
    elif td is not None and td>=25:
        parts.append("Không khí có nhiều hơi ẩm nên cảm giác khá oi")
    if wind is not None:
        if wind>=15:parts.append("Có gió nên cảm giác đỡ bí hơn một chút")
        elif wind<5 and (td or 0)>=24:parts.append("Gió yếu nên cảm giác oi rõ hơn")
    if not parts:parts.append("Cảm nhận ngoài trời hiện khá gần với nhiệt độ đo được")
    return ". ".join(parts)+"."

def _actual_status(value_present:bool,observed_at:Any,generated_at:datetime,qc:Any)->tuple[str,float|None]:
    age=_age_minutes(observed_at,generated_at)
    if not value_present:return "UNAVAILABLE",age
    if str(qc or "").upper()=="PASS" and age is not None and age<=FRESH_ACTUAL_MINUTES:
        return "ACTUAL",round(age,1)
    if age is not None and age<=LAST_OBSERVED_MINUTES:
        return "LAST_OBSERVED",round(age,1)
    return "STALE",round(age,1) if age is not None else None

def _rain_station_for_point(point_id:str,stations:dict)->dict|None:
    direct=stations.get(point_id)
    if isinstance(direct,dict):return direct
    loc="rain_"+point_id
    return next((s for s in stations.values() if isinstance(s,dict) and s.get("location_id")==loc),None)

def _exit_window(nowcast_point:dict,generated_at:datetime)->dict|None:
    motion=(nowcast_point or {}).get("cloud_motion") or {}
    if str(motion.get("tracking_confidence") or "").upper() not in {"MEDIUM","MEDIUM_HIGH","HIGH"}:
        return None
    exit_time=_time(motion.get("exit_time"))
    if not exit_time:return None
    mins=(exit_time-generated_at).total_seconds()/60
    if not 10<=mins<=120:return None
    lower=max(10,int(mins//15)*15);upper=lower+15
    return {"lower_minutes":lower,"upper_minutes":upper,
            "text":f"Dự kiến mưa sẽ giảm trong khoảng {lower}-{upper} phút.",
            "basis":"NOWCAST_EXIT_TIME","data_class":"DERIVED"}

def build_island_comfort(groundtruth:dict,generated_at:datetime)->dict:
    v=(groundtruth.get("atmosphere") or {}).get("vvpq") or {}
    t,td,wind=_num(v.get("temperature_c")),_num(v.get("dewpoint_c")),_num(v.get("wind_speed_kmh"))
    rh=relative_humidity_percent(t,td);feels=heat_index_c(t,rh)
    status,age=_actual_status(t is not None,v.get("observed_at"),generated_at,v.get("qc"))
    return {"observation_status":status,"observed_at":v.get("observed_at"),"age_minutes":age,
            "spatial_scope":"ISLAND_ACTUAL_ANCHOR","temperature_c":t,"dewpoint_c":td,
            "humidity_percent":rh,"wind_kmh":wind,
            "data_class":"ACTUAL" if status=="ACTUAL" else ("ACTUAL_STALE" if t is not None else "UNAVAILABLE"),
            "derived":{"feels_like_c":feels,"comfort_label":_comfort_label(t,td,feels),
                       "comfort_reason":_comfort_reason(t,td,rh,feels,wind) if status in {"ACTUAL","LAST_OBSERVED"} else None,
                       "data_class":"DERIVED","method":"DEWPOINT_RH_PLUS_NOAA_HEAT_INDEX"}}

def build_point_interpretation(point_id:str,local_point:dict,groundtruth:dict,nowcast_point:dict,generated_at:datetime)->dict:
    name=POINT_NAMES.get(point_id,point_id)
    station=_rain_station_for_point(point_id,(groundtruth.get("rainfall") or {}).get("stations") or {})
    actual=None
    if station:
        observed=station.get("rain_observed");rate=_num(station.get("rain_intensity_mm_h"))
        status,age=_actual_status(observed is not None or rate is not None,station.get("observed_at"),generated_at,station.get("qc"))
        actual={"observation_status":status,"observed_at":station.get("observed_at"),"age_minutes":age,
                "rain_observed":observed,"rate_mm_h":rate,"intensity_label":rain_intensity_label(rate),
                "increment_mm":_num(station.get("increment_mm")),
                "increment_window_minutes":_num(station.get("increment_window_minutes")),
                "spatial_scope":"POINT_GAUGE","data_class":"ACTUAL" if status=="ACTUAL" else "ACTUAL_STALE"}
    lr=(local_point or {}).get("rain") or {};er=_num(lr.get("rain_rate_mm_h"));imm=lr.get("imminence") or {}
    estimate={"rate_mm_h":er,"intensity_label":rain_intensity_label(er),
              "imminence_level":imm.get("level"),"imminence_score":_num(imm.get("score")),
              "data_class":str(lr.get("data_class") or "UNAVAILABLE")}
    duration=None
    if actual and actual["observation_status"]=="ACTUAL" and actual.get("rain_observed") is True:
        headline=f"{name} đang có {actual.get('intensity_label') or 'mưa'}."
        duration=_exit_window(nowcast_point,generated_at)
        detail=duration["text"] if duration else "Mưa đang được ghi nhận tại điểm quan trắc trong khu vực."
        evidence="ACTUAL"
    elif actual and actual["observation_status"]=="ACTUAL" and actual.get("rain_observed") is False:
        headline=f"{name} hiện chưa ghi nhận mưa tại điểm quan trắc."
        detail="Mưa cục bộ vẫn có thể khác giữa các khu vực trên đảo.";evidence="ACTUAL"
    elif er is not None and er>0.05:
        headline=f"{name} có tín hiệu {rain_intensity_label(er) or 'mưa'}."
        detail="Khả năng xuất hiện mưa trong thời gian ngắn đang tăng." if str(imm.get("level") or "").upper() in {"HIGH","ELEVATED"} else "Đây là ước tính tại điểm, chưa phải số đo trực tiếp."
        evidence="DERIVED"
    else:
        headline=f"{name} chưa có tín hiệu mưa đáng kể."
        detail="Tiếp tục theo dõi nếu mây đối lưu thay đổi nhanh."
        evidence="DERIVED" if er is not None else "UNAVAILABLE"
    return {"point_id":point_id,"name":name,"rain":{"actual":actual,"estimate":estimate},
            "interpretation":{"headline":headline,"detail":detail,"evidence_class":evidence,"duration":duration}}

def build_human_weather(local:dict,groundtruth:dict,nowcast:dict,generated_at:datetime|str|None=None)->dict:
    generated=_time(generated_at) if not isinstance(generated_at,datetime) else generated_at.astimezone(timezone.utc)
    generated=generated or _time(groundtruth.get("generated_at")) or datetime.now(timezone.utc)
    lp=local.get("points") or {};np=nowcast.get("points") or {}
    points={pid:build_point_interpretation(pid,lp.get(pid) or {},groundtruth,np.get(pid) or {},generated)
            for pid in POINT_NAMES if pid!="rach_gia"}
    island=build_island_comfort(groundtruth,generated);comfort=island.get("derived") or {}
    if island.get("observation_status")=="ACTUAL" and island.get("temperature_c") is not None:
        t=island["temperature_c"];f=comfort.get("feels_like_c");label=comfort.get("comfort_label") or "Thời tiết hiện tại"
        summary=f"{label} - {t:.1f}°C, cảm giác khoảng {f:.0f}°C." if f is not None and abs(f-t)>=1 else f"{label} - {t:.1f}°C."
    else:
        summary="Chưa có quan trắc nhiệt độ đủ mới để mô tả cảm nhận ngoài trời."
    return {"schema_version":"jotrip-human-weather-v1","generated_at":generated.isoformat(),
            "island":{**island,"summary":summary},"points":points,
            "contract":{"actual_label":"ACTUAL","forecast_label":"FORECAST","derived_label":"DERIVED",
                        "rule":"Public wording may simplify meaning but must preserve evidence class, time and spatial scope."}}
