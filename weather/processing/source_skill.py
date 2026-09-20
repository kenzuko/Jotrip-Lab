"""Early source-skill diagnostics for JoTrip Weather.

This is intentionally separate from forecast bias calibration:
- VVPQ ACTUAL is compared against the deterministic anchor background and the
  nearest GEFS q50 that had already been available to Local Now.
- VRain contributes source continuity / QC reliability until enough immutable
  forecast-verification windows exist for true precipitation skill.
- Early skill may only nudge fusion weights. It never rewrites ACTUAL data and
  never applies full bias correction.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


def _num(v: Any) -> float | None:
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _load(path: Path) -> dict | None:
    try:
        v=json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v,dict) else None
    except Exception:
        return None


def _metrics(errors: list[float]) -> dict:
    if not errors:
        return {"sample_count":0,"mae":None,"rmse":None,"mean_error":None,"median_error":None}
    return {
        "sample_count":len(errors),
        "mae":round(mean(abs(x) for x in errors),3),
        "rmse":round(math.sqrt(mean(x*x for x in errors)),3),
        "mean_error":round(mean(errors),3),
        "median_error":round(median(errors),3),
    }


def _shrunken_multiplier(model_mae: float | None, ensemble_mae: float | None, n: int) -> float:
    if model_mae is None or ensemble_mae is None or n < 3:
        return 1.0
    # Positive skill when ensemble q50 beats deterministic anchor background.
    skill=(model_mae-ensemble_mae)/max(1.0,model_mae)
    shrink=n/(n+20.0)
    return round(max(0.90,min(1.10,1.0+0.10*skill*shrink)),4)


def build(raw_root: Path, analysis_root: Path) -> dict:
    raw_by_name={p.name:p for p in raw_root.rglob("*.json") if p.name not in {"latest.json","local-now.json","health.json"}}
    analysis_by_name={p.name:p for p in analysis_root.rglob("*.json") if p.name not in {"latest.json","local-now.json","health.json"}}

    # Dedupe METAR by observed_at so a single hourly METAR is not counted as ten
    # independent 10-minute samples.
    vvpq_cases={}
    station_cases=defaultdict(dict)

    for name,raw_path in raw_by_name.items():
        raw=_load(raw_path)
        ana=_load(analysis_by_name.get(name,Path("/nonexistent"))) if name in analysis_by_name else None
        if not raw:
            continue

        v=(raw.get("atmosphere") or {}).get("vvpq") or {}
        obs_key=str(v.get("observed_at") or "")
        if obs_key and v.get("data_class")=="ACTUAL" and v.get("qc")=="PASS" and ana:
            dd=(ana.get("points") or {}).get("duong_dong") or {}
            wind=dd.get("wind") or {}
            temp=dd.get("temperature") or {}
            actual_w=_num(v.get("wind_speed_kmh"))
            model_w=_num(wind.get("anchor_model_proxy_kmh"))
            ens_w=_num((wind.get("ensemble_context") or {}).get("q50_kmh"))
            actual_t=_num(v.get("temperature_c"))
            model_t=_num(temp.get("anchor_model_proxy"))
            candidate={
                "observed_at":obs_key,
                "age_minutes":_num(v.get("age_minutes")),
                "actual_wind_kmh":actual_w,
                "model_wind_kmh":model_w,
                "ensemble_wind_kmh":ens_w,
                "actual_temperature_c":actual_t,
                "model_temperature_c":model_t,
            }
            before=vvpq_cases.get(obs_key)
            # Prefer the cycle nearest to the observation.
            if before is None or (candidate["age_minutes"] or 999)<(before["age_minutes"] or 999):
                vvpq_cases[obs_key]=candidate

        for station_id,s in ((raw.get("rainfall") or {}).get("stations") or {}).items():
            obs=str(s.get("observed_at") or "")
            if not obs:
                continue
            station_cases[station_id][obs]={
                "qc_pass":s.get("qc")=="PASS",
                "increment_pass":s.get("increment_qc")=="PASS",
                "age_minutes":_num(s.get("age_minutes")),
                "rain_observed":s.get("rain_observed"),
            }

    wind_model_err=[]
    wind_ens_err=[]
    temp_model_err=[]
    for c in vvpq_cases.values():
        if c["actual_wind_kmh"] is not None and c["model_wind_kmh"] is not None:
            wind_model_err.append(c["actual_wind_kmh"]-c["model_wind_kmh"])
        if c["actual_wind_kmh"] is not None and c["ensemble_wind_kmh"] is not None:
            wind_ens_err.append(c["actual_wind_kmh"]-c["ensemble_wind_kmh"])
        if c["actual_temperature_c"] is not None and c["model_temperature_c"] is not None:
            temp_model_err.append(c["actual_temperature_c"]-c["model_temperature_c"])

    model_metrics=_metrics(wind_model_err)
    ens_metrics=_metrics(wind_ens_err)
    n=min(model_metrics["sample_count"],ens_metrics["sample_count"])
    gain_multiplier=_shrunken_multiplier(model_metrics["mae"],ens_metrics["mae"],n)

    rain_sources={}
    for station_id,rows_by_time in sorted(station_cases.items()):
        rows=list(rows_by_time.values())
        total=len(rows)
        qc=sum(1 for r in rows if r["qc_pass"])
        inc=sum(1 for r in rows if r["increment_pass"])
        fresh=sum(1 for r in rows if r["age_minutes"] is not None and r["age_minutes"]<=20)
        # Source reliability is about data quality/continuity, not agreement with
        # distant rain gauges. Rain can legitimately differ over short distances.
        q_ratio=qc/max(1,total)
        inc_ratio=inc/max(1,total)
        fresh_ratio=fresh/max(1,total)
        quality=max(0.80,min(1.05,0.80+0.10*q_ratio+0.05*inc_ratio+0.05*fresh_ratio))
        rain_sources[station_id]={
            "sample_count":total,
            "qc_pass_ratio":round(q_ratio,3),
            "increment_pass_ratio":round(inc_ratio,3),
            "fresh_ratio":round(fresh_ratio,3),
            "quality_factor":round(quality,3),
            "wet_samples":sum(1 for r in rows if r.get("rain_observed") is True),
            "dry_samples":sum(1 for r in rows if r.get("rain_observed") is False),
        }

    return {
        "schema_version":"weather-source-skill-v1",
        "policy":{
            "actual_only":True,
            "early_weight_adjustment_only":True,
            "full_bias_calibration_min_samples":30,
            "vvpq_deduplication":"unique observed_at",
            "vrain_cross_station_accuracy_comparison":False,
            "note":"Rain gauges are not scored against distant gauges; local rain variability is real. VRain early factors reflect QC/freshness only until forecast verification matures.",
        },
        "vvpq":{
            "unique_actual_samples":len(vvpq_cases),
            "wind":{
                "deterministic_background":model_metrics,
                "ensemble_q50":ens_metrics,
                "ensemble_gain_multiplier":gain_multiplier,
                "status":"PROVISIONAL" if n>=3 else "LEARNING",
            },
            "temperature":{"deterministic_background":_metrics(temp_model_err)},
        },
        "vrain":rain_sources,
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--raw-root",type=Path,required=True)
    p.add_argument("--analysis-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out=build(a.raw_root,a.analysis_root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))


if __name__=="__main__":
    main()
