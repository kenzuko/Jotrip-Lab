"""Copernicus Marine astronomical tide layer for Weather Lab.

Uses the merged hourly sea-level product's ocean_tide component. Values are modelled
astronomical tide relative to mean sea level, not harbour gauge/chart-datum readings.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from weather.collectors.copernicus import configuration_status, subset

DATASET = "cmems_mod_glo_phy_anfc_merged-sl_PT1H-i"
VARIABLE = "ocean_tide"
BBOX = (9.70, 103.55, 10.55, 105.30)
VN = ZoneInfo("Asia/Ho_Chi_Minh")
POINTS = {
    "duong_dong": (10.2172, 103.9593),
    "an_thoi": (10.0191, 104.0150),
    "ganh_dau": (10.3759, 103.9000),
    "rach_gia": (10.00677, 105.07845),
}
NAMES = {
    "duong_dong": "Dương Đông", "an_thoi": "An Thới",
    "ganh_dau": "Gành Dầu", "rach_gia": "Rạch Giá",
}


def _coord_name(data, options: tuple[str, ...]) -> str:
    for name in options:
        if name in data.coords:
            return name
    raise KeyError(f"Missing coordinate among {options}")


def _nearest_sea_index(array, lat: float, lon: float) -> tuple[int, int, float]:
    import numpy as np

    lat_name = _coord_name(array, ("latitude", "lat"))
    lon_name = _coord_name(array, ("longitude", "lon"))
    lats = np.asarray(array[lat_name].values, dtype=float)
    lons = np.asarray(array[lon_name].values, dtype=float)
    sample = array
    for dim in ("time", "depth"):
        if dim in sample.dims:
            sample = sample.isel({dim: 0})
    values = np.asarray(sample.values, dtype=float)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    valid = np.isfinite(values)
    if not valid.any():
        raise ValueError("NO_FINITE_TIDE_GRID")
    distance2 = (lat_grid - lat) ** 2 + ((lon_grid - lon) * math.cos(math.radians(lat))) ** 2
    distance2[~valid] = np.inf
    row, col = np.unravel_index(np.argmin(distance2), distance2.shape)
    return int(row), int(col), round(math.sqrt(float(distance2[row, col])) * 111.2, 3)


def _series(array, lat: float, lon: float) -> tuple[list[dict], dict]:
    import numpy as np

    lat_name = _coord_name(array, ("latitude", "lat"))
    lon_name = _coord_name(array, ("longitude", "lon"))
    row, col, distance_km = _nearest_sea_index(array, lat, lon)
    point = array.isel({lat_name: row, lon_name: col})
    if "depth" in point.dims:
        point = point.isel(depth=0)
    times = np.asarray(point["time"].values).astype("datetime64[ns]")
    vals = np.asarray(point.values, dtype=float).reshape(-1)
    rows = []
    for t, value in zip(times, vals):
        if not np.isfinite(value):
            continue
        stamp = datetime.fromisoformat(np.datetime_as_string(t, unit="s")).replace(tzinfo=timezone.utc)
        local = stamp.astimezone(VN)
        rows.append({"time_iso": local.isoformat(), "time": local.strftime("%d/%m %H:%M"), "height_m": round(float(value), 3)})
    sampled = {"sampled_lat": float(array[lat_name].values[row]), "sampled_lon": float(array[lon_name].values[col]), "distance_km": distance_km}
    return rows, sampled


def _extrema(rows: list[dict], now: datetime) -> list[dict]:
    turns = []
    for i in range(1, len(rows) - 1):
        a, b, c = rows[i - 1]["height_m"], rows[i]["height_m"], rows[i + 1]["height_m"]
        kind = None
        if b >= a and b > c:
            kind = "HIGH"
        elif b <= a and b < c:
            kind = "LOW"
        if kind:
            turns.append({"type": kind, "time_iso": rows[i]["time_iso"], "time": rows[i]["time"], "height_m": b})
    return [x for x in turns if datetime.fromisoformat(x["time_iso"]) >= now.astimezone(VN)]


def _summarize(rows: list[dict], now: datetime) -> dict:
    if not rows:
        return {"status": "UNAVAILABLE"}
    now_local = now.astimezone(VN)
    nearest_i = min(range(len(rows)), key=lambda i: abs((datetime.fromisoformat(rows[i]["time_iso"]) - now_local).total_seconds()))
    current = rows[nearest_i]
    next_i = min(nearest_i + 1, len(rows) - 1)
    delta = rows[next_i]["height_m"] - current["height_m"]
    trend = "RISING" if delta > 0.005 else "FALLING" if delta < -0.005 else "TURNING"
    turns = _extrema(rows, now)
    next_high = next((x for x in turns if x["type"] == "HIGH"), None)
    next_low = next((x for x in turns if x["type"] == "LOW"), None)
    next_turn = min((x for x in turns), key=lambda x: datetime.fromisoformat(x["time_iso"]), default=None)
    end24 = now_local + timedelta(hours=24)
    window = [r for r in rows if now_local <= datetime.fromisoformat(r["time_iso"]) <= end24]
    heights = [r["height_m"] for r in window]
    return {
        "status": "POINT_NUMERIC_READY",
        "current_height_m": current["height_m"],
        "current_time": current["time_iso"],
        "trend": trend,
        "next_high": next_high,
        "next_low": next_low,
        "next_turn": next_turn,
        "range_24h_m": round(max(heights) - min(heights), 3) if heights else None,
        "series": rows,
    }


def run(output: Path | None = None) -> dict:
    auth = configuration_status()
    if auth["status"] != "READY":
        result = {"status": "AUTH_REQUIRED", "source": "COPERNICUS_MARINE_FES2014", "missing": auth["missing"], "points": {}}
    else:
        now = datetime.now(timezone.utc)
        start, end = now - timedelta(hours=6), now + timedelta(hours=72)
        try:
            with tempfile.TemporaryDirectory(prefix="jotrip-tide-") as temp:
                path = Path(temp) / "tide.nc"
                download = subset(dataset_id=DATASET, variables=[VARIABLE], start=start, end=end, bbox=BBOX, output=path)
                if not path.exists():
                    raise RuntimeError(f"Tide subset missing: {download}")
                import xarray as xr
                with xr.open_dataset(path) as ds:
                    if VARIABLE not in ds.data_vars:
                        raise KeyError(f"{VARIABLE} not in {list(ds.data_vars)}")
                    points = {}
                    for key, (lat, lon) in POINTS.items():
                        rows, sampled = _series(ds[VARIABLE], lat, lon)
                        points[key] = {"name": NAMES[key], **sampled, **_summarize(rows, now)}
                ready = all(p.get("status") == "POINT_NUMERIC_READY" for p in points.values())
                result = {
                    "status": "POINT_NUMERIC_READY" if ready else "PARTIAL_OR_FAILED",
                    "source": "COPERNICUS_MARINE_FES2014",
                    "dataset": DATASET,
                    "variable": VARIABLE,
                    "generated_at": now.astimezone(VN).isoformat(),
                    "forecast_hours": 72,
                    "height_reference": "MODEL_MEAN_SEA_LEVEL",
                    "method": "HOURLY_OCEAN_TIDE_MODEL_EXTREMA",
                    "points": points,
                    "disclaimer": "Triều mô hình FES2014 qua Copernicus Marine, không phải số đo trạm hay mực nước theo hải đồ cảng.",
                }
        except Exception as exc:
            result = {"status": "UNAVAILABLE", "source": "COPERNICUS_MARINE_FES2014", "dataset": DATASET, "points": {}, "detail": str(exc)}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
