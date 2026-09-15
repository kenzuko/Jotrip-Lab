"""Live Copernicus Marine wave/current subset and numeric QC for Phu Quoc."""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.collectors.copernicus import configuration_status, subset

WAVE_DATASET = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
CURRENT_DATASET = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
BBOX = (9.70, 103.55, 10.55, 104.45)
POINTS = {
    "duong_dong": (10.2172, 103.9593),
    "an_thoi": (10.0191, 104.0150),
    "ganh_dau": (10.3759, 103.9000),
}


def _nearest_valid(array, lat: float, lon: float) -> dict:
    import numpy as np

    data = array
    for dimension in ("time", "depth"):
        if dimension in data.dims:
            data = data.isel({dimension: 0})
    lat_name = "latitude" if "latitude" in data.coords else "lat"
    lon_name = "longitude" if "longitude" in data.coords else "lon"
    values = np.asarray(data.values, dtype=float)
    lats = np.asarray(data[lat_name].values, dtype=float)
    lons = np.asarray(data[lon_name].values, dtype=float)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    valid = np.isfinite(values)
    if not valid.any():
        return {"status": "REJECTED_QC", "reason": "NO_FINITE_SEA_GRID"}
    distance2 = (lat_grid - lat) ** 2 + ((lon_grid - lon) * math.cos(math.radians(lat))) ** 2
    distance2[~valid] = np.inf
    row, col = np.unravel_index(np.argmin(distance2), distance2.shape)
    sampled_lat, sampled_lon = float(lat_grid[row, col]), float(lon_grid[row, col])
    distance_km = math.sqrt(float(distance2[row, col])) * 111.2
    return {"status": "PASS", "value": float(values[row, col]), "sampled_lat": sampled_lat,
            "sampled_lon": sampled_lon, "distance_km": round(distance_km, 3)}


def _inspect(path: Path, requested: list[str]) -> dict:
    import numpy as np
    import xarray as xr

    with xr.open_dataset(path) as dataset:
        available = [name for name in requested if name in dataset.data_vars]
        missing = [name for name in requested if name not in dataset.data_vars]
        variables = {}
        for name in available:
            values = np.asarray(dataset[name].values, dtype=float)
            finite = values[np.isfinite(values)]
            variables[name] = {
                "unit": dataset[name].attrs.get("units"), "finite_count": int(finite.size),
                "minimum": float(finite.min()) if finite.size else None,
                "maximum": float(finite.max()) if finite.size else None,
                "points": {point: _nearest_valid(dataset[name], lat, lon) for point, (lat, lon) in POINTS.items()},
            }
        return {"dataset_dimensions": dict(dataset.sizes), "available_variables": available,
                "missing_variables": missing, "variables": variables}


def run(output: Path | None = None) -> dict:
    auth = configuration_status()
    if auth["status"] != "READY":
        result = {"status": "AUTH_REQUIRED", "missing": auth["missing"]}
    else:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=24)
        with tempfile.TemporaryDirectory(prefix="jotrip-cmems-") as temp:
            work = Path(temp)
            wave_path = work / "phu-quoc-wave.nc"
            current_path = work / "phu-quoc-current.nc"
            wave_vars = ["VHM0", "VMDR", "VTM10", "VTPK"]
            current_vars = ["uo", "vo"]
            wave_download = subset(dataset_id=WAVE_DATASET, variables=wave_vars, start=start, end=end,
                                   bbox=BBOX, output=wave_path)
            current_download = subset(dataset_id=CURRENT_DATASET, variables=current_vars, start=start, end=end,
                                      bbox=BBOX, output=current_path, minimum_depth=0, maximum_depth=5)
            wave = _inspect(wave_path, wave_vars) if wave_path.exists() else {"error": wave_download}
            current = _inspect(current_path, current_vars) if current_path.exists() else {"error": current_download}
            usable = not wave.get("missing_variables") and not current.get("missing_variables")
            result = {
                "status": "POINT_NUMERIC_READY" if usable else "PARTIAL_OR_FAILED",
                "readiness": "POINT_ROUTE_EXTRACTED" if usable else "OBJECT_RETRIEVED",
                "qc": "PASS" if usable else "FAIL", "bbox": BBOX,
                "start": start.isoformat(), "end": end.isoformat(),
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
