"""Live Copernicus Marine wave/current subset and numeric QC for Phu Quoc + Rach Gia."""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.collectors.copernicus import configuration_status, subset
from weather.processing.marine import current_from_uv

WAVE_DATASET = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
CURRENT_DATASET = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
BBOX = (9.70, 103.55, 10.55, 105.30)
REGIONAL_RADIUS_KM = 15.0
POINTS = {
    "duong_dong": (10.2172, 103.9593),
    "an_thoi": (10.0191, 104.0150),
    "ganh_dau": (10.3759, 103.9000),
    "rach_gia": (10.00677, 105.07845),
}


def _select_time(data, target_time: datetime):
    import numpy as np

    sampled_time = None
    if "time" in data.dims:
        times = np.asarray(data["time"].values).astype("datetime64[ns]")
        target64 = np.datetime64(target_time.astimezone(timezone.utc).replace(tzinfo=None), "ns")
        index = int(np.argmin(np.abs(times - target64)))
        data = data.isel(time=index)
        sampled_time = np.datetime_as_string(times[index], unit="s") + "Z"
    return data, sampled_time


def _surface(data):
    for dimension in ("depth",):
        if dimension in data.dims:
            data = data.isel({dimension: 0})
    return data


def _grid(data):
    import numpy as np

    lat_name = "latitude" if "latitude" in data.coords else "lat"
    lon_name = "longitude" if "longitude" in data.coords else "lon"
    values = np.asarray(data.values, dtype=float)
    lats = np.asarray(data[lat_name].values, dtype=float)
    lons = np.asarray(data[lon_name].values, dtype=float)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return values, lat_grid, lon_grid


def _nearest_valid(array, lat: float, lon: float, target_time: datetime) -> dict:
    import numpy as np

    data, sampled_time = _select_time(array, target_time)
    data = _surface(data)
    values, lat_grid, lon_grid = _grid(data)
    valid = np.isfinite(values)
    if not valid.any():
        return {"status": "REJECTED_QC", "reason": "NO_FINITE_SEA_GRID", "sampled_time": sampled_time}
    distance2 = (lat_grid - lat) ** 2 + ((lon_grid - lon) * math.cos(math.radians(lat))) ** 2
    distance2[~valid] = np.inf
    row, col = np.unravel_index(np.argmin(distance2), distance2.shape)
    sampled_lat, sampled_lon = float(lat_grid[row, col]), float(lon_grid[row, col])
    distance_km = math.sqrt(float(distance2[row, col])) * 111.2
    return {"status": "PASS", "value": float(values[row, col]), "sampled_lat": sampled_lat,
            "sampled_lon": sampled_lon, "distance_km": round(distance_km, 3), "sampled_time": sampled_time}


def _regional_max(array, lat: float, lon: float, target_time: datetime, radius_km: float) -> dict:
    import numpy as np

    data, sampled_time = _select_time(array, target_time)
    data = _surface(data)
    values, lat_grid, lon_grid = _grid(data)
    distance2 = (lat_grid - lat) ** 2 + ((lon_grid - lon) * math.cos(math.radians(lat))) ** 2
    distance_km = np.sqrt(distance2) * 111.2
    mask = np.isfinite(values) & (distance_km <= radius_km)
    if not mask.any():
        return {"status": "REJECTED_QC", "reason": "NO_FINITE_SEA_GRID_IN_RADIUS",
                "radius_km": radius_km, "sampled_time": sampled_time}
    masked = np.where(mask, values, -np.inf)
    row, col = np.unravel_index(np.argmax(masked), masked.shape)
    return {"status": "PASS", "value": float(values[row, col]),
            "sampled_lat": float(lat_grid[row, col]), "sampled_lon": float(lon_grid[row, col]),
            "distance_km": round(float(distance_km[row, col]), 3), "radius_km": radius_km,
            "sampled_time": sampled_time}


def _inspect(path: Path, requested: list[str], target_time: datetime) -> dict:
    import numpy as np
    import xarray as xr

    with xr.open_dataset(path) as dataset:
        available = [name for name in requested if name in dataset.data_vars]
        missing = [name for name in requested if name not in dataset.data_vars]
        variables = {}
        for name in available:
            values = np.asarray(dataset[name].values, dtype=float)
            finite = values[np.isfinite(values)]
            variable = {
                "unit": dataset[name].attrs.get("units"), "finite_count": int(finite.size),
                "minimum": float(finite.min()) if finite.size else None,
                "maximum": float(finite.max()) if finite.size else None,
                "points": {point: _nearest_valid(dataset[name], lat, lon, target_time)
                           for point, (lat, lon) in POINTS.items()},
            }
            if name == "VHM0":
                variable["regional_max_15km"] = {
                    point: _regional_max(dataset[name], lat, lon, target_time, REGIONAL_RADIUS_KM)
                    for point, (lat, lon) in POINTS.items()
                }
            variables[name] = variable
        return {"dataset_dimensions": dict(dataset.sizes), "available_variables": available,
                "missing_variables": missing, "variables": variables}


def run(output: Path | None = None) -> dict:
    auth = configuration_status()
    if auth["status"] != "READY":
        result = {"status": "AUTH_REQUIRED", "missing": auth["missing"]}
    else:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=6)
        end = now + timedelta(hours=24)
        with tempfile.TemporaryDirectory(prefix="jotrip-cmems-") as temp:
            work = Path(temp)
            wave_path = work / "regional-wave.nc"
            current_path = work / "regional-current.nc"
            wave_vars = ["VHM0", "VMDR", "VTM10", "VTPK"]
            current_vars = ["uo", "vo"]
            wave_download = subset(dataset_id=WAVE_DATASET, variables=wave_vars, start=start, end=end,
                                   bbox=BBOX, output=wave_path)
            current_download = subset(dataset_id=CURRENT_DATASET, variables=current_vars, start=start, end=end,
                                      bbox=BBOX, output=current_path, minimum_depth=0, maximum_depth=5)
            wave = _inspect(wave_path, wave_vars, now) if wave_path.exists() else {"error": wave_download}
            current = _inspect(current_path, current_vars, now) if current_path.exists() else {"error": current_download}
            if not current.get("missing_variables"):
                vectors = {}
                for point in POINTS:
                    u = current["variables"]["uo"]["points"][point]
                    v = current["variables"]["vo"]["points"][point]
                    if u.get("status") == "PASS" and v.get("status") == "PASS":
                        vectors[point] = {
                            **current_from_uv(u["value"], v["value"]),
                            "sampled_lat": u["sampled_lat"], "sampled_lon": u["sampled_lon"],
                            "distance_km": u["distance_km"], "depth_selection": "SHALLOWEST_0_TO_5M",
                            "sampled_time": u.get("sampled_time"),
                        }
                current["derived_vectors"] = vectors
            usable = not wave.get("missing_variables") and not current.get("missing_variables")
            result = {
                "status": "POINT_NUMERIC_READY" if usable else "PARTIAL_OR_FAILED",
                "readiness": "POINT_ROUTE_EXTRACTED" if usable else "OBJECT_RETRIEVED",
                "qc": "PASS" if usable else "FAIL", "bbox": BBOX,
                "target_time": now.isoformat(), "start": start.isoformat(), "end": end.isoformat(),
                "regional_radius_km": REGIONAL_RADIUS_KM,
                "wave_dataset": WAVE_DATASET, "current_dataset": CURRENT_DATASET,
                "wave": wave, "current": current,
            }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
