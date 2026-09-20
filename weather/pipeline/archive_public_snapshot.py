"""Compact archive of values actually exposed by the public Weather UI.

One row per local 30-minute bucket. This is an audit/backtest trail, not another
forecast source. It captures the public-facing Estimated Now values and their
source metadata without storing the full UI payload.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN=timezone(timedelta(hours=7))


def _dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:
        return None


def _row(bundle: dict) -> dict:
    generated=_dt(bundle.get("generated_at")) or datetime.now(timezone.utc)
    ln=bundle.get("local_now") or {}
    points={}
    for point_id,p in (ln.get("points") or {}).items():
        wind=p.get("wind") or {}
        rain=p.get("rain") or {}
        points[point_id]={
            "temperature_c":p.get("temperature_c"),
            "wind_kmh":p.get("wind_kmh"),
            "wind_method":wind.get("method"),
            "wind_confidence":wind.get("confidence"),
            "rain_rate_mm_h":rain.get("rain_rate_mm_h"),
            "rain_method":rain.get("method"),
            "rain_confidence":rain.get("confidence"),
            "wave_hs_m":p.get("wave_hs_m"),
            "convective_score":rain.get("convective_score"),
            "data_class":"ESTIMATED_NOW",
        }
    gt=bundle.get("groundtruth") or {}
    v=(gt.get("atmosphere") or {}).get("vvpq") or {}
    gauges=(gt.get("rainfall") or {}).get("stations") or {}
    return {
        "published_at":generated.isoformat(),
        "local_engine":ln.get("engine"),
        "points":points,
        "actual_refs":{
            "vvpq_observed_at":v.get("observed_at"),
            "vvpq_wind_kmh":v.get("wind_speed_kmh"),
            "vrain":{k:{
                "observed_at":s.get("observed_at"),
                "increment_mm":s.get("increment_mm"),
                "rain_observed":s.get("rain_observed"),
            } for k,s in gauges.items()},
        },
    }


def archive(bundle: dict, root: Path, cadence_minutes: int = 30) -> dict:
    row=_row(bundle)
    t=_dt(row["published_at"]) or datetime.now(timezone.utc)
    lt=t.astimezone(VN)
    bucket=lt.replace(minute=(lt.minute//cadence_minutes)*cadence_minutes,second=0,microsecond=0)
    day=lt.date().isoformat()
    path=root/f"{day}.jsonl"
    path.parent.mkdir(parents=True,exist_ok=True)

    rows=[]
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try: rows.append(json.loads(line))
            except Exception: pass

    def key(r):
        d=_dt(r.get("published_at"))
        if not d:return ""
        local=d.astimezone(VN)
        return local.replace(minute=(local.minute//cadence_minutes)*cadence_minutes,second=0,microsecond=0).isoformat()

    bucket_key=bucket.isoformat()
    rows=[r for r in rows if key(r)!=bucket_key]
    row["bucket_local"]=bucket_key
    rows.append(row)
    rows.sort(key=lambda r:r.get("published_at") or "")
    path.write_text("\n".join(json.dumps(r,ensure_ascii=False,separators=(",",":")) for r in rows)+"\n",encoding="utf-8")

    latest=root/"latest.json"
    latest.write_text(json.dumps(row,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"date":day,"bucket_local":bucket_key,"rows_today":len(rows),"path":str(path)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bundle",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--cadence-minutes",type=int,default=30)
    a=p.parse_args()
    bundle=json.loads(a.bundle.read_text(encoding="utf-8"))
    print(json.dumps(archive(bundle,a.root,a.cadence_minutes),ensure_ascii=False))


if __name__=="__main__":
    main()
