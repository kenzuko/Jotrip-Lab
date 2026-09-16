"""Collect CAMS PM2.5/PM10 for Weather Lab using the current ADS PAT client.

AQI is a model-derived US EPA particulate proxy, not an observed/regulatory AQI.
This layer is non-critical and never changes marine GO/HOLD logic.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

POINTS = {
    "duong_dong": (10.2172, 103.9593),
    "an_thoi": (10.0191, 104.0150),
    "ganh_dau": (10.3759, 103.9000),
    "rach_gia": (10.00677, 105.07845),
}
DATASET = "cams-global-atmospheric-composition-forecasts"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
AREA = [10.6, 103.5, 9.7, 105.4]  # north, west, south, east
VARIABLES = ["particulate_matter_2.5um", "particulate_matter_10um"]
TIMES = ["00:00", "06:00", "12:00", "18:00"]


def _write(output: Path, payload: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _empty(status: str, detail: str) -> dict:
    return {
        "status": status,
        "source": "CAMS_GLOBAL_ANALYSIS",
        "dataset": DATASET,
        "grid_resolution": "0.4deg",
        "method": "MODEL_ANALYSIS_INSTANT_PM_US_AQI_PROXY",
        "aqi_standard": "US EPA 2024 PM breakpoints applied to instantaneous CAMS model concentration; not observed/regulatory AQI",
        "sampled_time": None,
        "points": {},
        "detail": detail,
    }


def _find_var(dataset, names: tuple[str, ...]):
    normalized = {str(name).lower().replace(".", "").replace("_", ""): name for name in dataset.data_vars}
    for candidate in names:
        key = candidate.lower().replace(".", "").replace("_", "")
        if key in normalized:
            return dataset[normalized[key]]
    for name in dataset.data_vars:
        low = str(name).lower()
        if any(candidate in low for candidate in names):
            return dataset[name]
    return None


def _sample_time(array) -> str | None:
    import numpy as np
    for coord_name in ("valid_time", "time"):
        if coord_name not in array.coords:
            continue
        values = np.asarray(array.coords[coord_name].values).reshape(-1)
        if values.size:
            value = values[-1]
            if np.issubdtype(np.asarray(value).dtype, np.datetime64):
                return np.datetime_as_string(value, unit="s") + "Z"
            return str(value)
    return None


def _ugm3(value: float, unit: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    normalized = (unit or "").lower().replace(" ", "")
    if "kg" in normalized or normalized == "":
        number *= 1_000_000_000.0
    elif "mg" in normalized:
        number *= 1000.0
    return round(number, 1) if 0 <= number <= 5000 else None


def _point_value(array, lat: float, lon: float) -> tuple[float | None, float | None, float | None, str | None]:
    import numpy as np
    obj = array
    lat_name = next((x for x in ("latitude", "lat") if x in obj.coords), None)
    lon_name = next((x for x in ("longitude", "lon") if x in obj.coords), None)
    if lat_name and lon_name:
        obj = obj.sel({lat_name: lat, lon_name: lon}, method="nearest")
    sampled_time = _sample_time(obj)
    grid_lat = float(obj.coords[lat_name].values) if lat_name and np.asarray(obj.coords[lat_name].values).size == 1 else None
    grid_lon = float(obj.coords[lon_name].values) if lon_name and np.asarray(obj.coords[lon_name].values).size == 1 else None
    for dim in list(obj.dims):
        if obj.sizes.get(dim, 1) > 1:
            obj = obj.isel({dim: -1})
    value = float(np.asarray(obj.values).reshape(-1)[-1])
    return _ugm3(value, str(array.attrs.get("units", ""))), grid_lat, grid_lon, sampled_time


def _open_download(path: Path):
    import xarray as xr
    if zipfile.is_zipfile(path):
        extract_dir = path.parent / "netcdf"
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_dir)
        files = sorted(extract_dir.rglob("*.nc"))
        if not files:
            raise RuntimeError("CAMS archive did not contain NetCDF files")
        datasets = [xr.open_dataset(file) for file in files]
        return (datasets[0] if len(datasets) == 1 else xr.merge(datasets, compat="override", join="outer")), datasets
    dataset = xr.open_dataset(path)
    return dataset, [dataset]


def _client(api_key: str):
    """Use ECMWF's current Data Stores client so ADS Personal Access Tokens work directly."""
    from ecmwf.datastores import Client
    return Client(url=ADS_URL, key=api_key)


def collect(api_key: str) -> dict:
    from weather.processing.air_quality import particulate_aqi
    client = _client(api_key)
    now = datetime.now(timezone.utc)
    last_error = None
    with tempfile.TemporaryDirectory(prefix="jotrip-cams-") as tmp:
        tmpdir = Path(tmp)
        target = tmpdir / "cams-aq.zip"
        selected_date = None
        for days_back in range(0, 4):
            day = (now - timedelta(days=days_back)).date().isoformat()
            request = {
                "variable": VARIABLES,
                "date": [day],
                "time": TIMES,
                "type": "analysis",
                "leadtime_hour": ["0"],
                "area": [str(value) for value in AREA],
                "data_format": "netcdf_zip",
            }
            try:
                if target.exists():
                    target.unlink()
                client.retrieve(DATASET, request, target=str(target))
                selected_date = day
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        if selected_date is None:
            raise RuntimeError(last_error or "No recent CAMS analysis available")

        dataset, opened = _open_download(target)
        try:
            pm25 = _find_var(dataset, ("pm2p5", "particulate_matter_25um", "particulate_matter_2.5um"))
            pm10 = _find_var(dataset, ("pm10", "particulate_matter_10um"))
            if pm25 is None or pm10 is None:
                raise RuntimeError(f"PM variables unavailable: {list(dataset.data_vars)}")
            points, times = {}, []
            for point_id, (lat, lon) in POINTS.items():
                pm25_value, grid_lat, grid_lon, sampled25 = _point_value(pm25, lat, lon)
                pm10_value, _, _, sampled10 = _point_value(pm10, lat, lon)
                sampled = sampled25 or sampled10
                if sampled:
                    times.append(sampled)
                points[point_id] = {
                    "pm25_ugm3": pm25_value,
                    "pm10_ugm3": pm10_value,
                    **particulate_aqi(pm25_value, pm10_value),
                    "sampled_time": sampled,
                    "grid_lat": round(grid_lat, 4) if grid_lat is not None else None,
                    "grid_lon": round(grid_lon, 4) if grid_lon is not None else None,
                    "source_type": "MODEL",
                }
            if not all(points[p].get("aqi_us") is not None for p in POINTS):
                raise RuntimeError("One or more CAMS points do not have numeric PM/AQI values")
            return {
                "status": "POINT_NUMERIC_READY",
                "source": "CAMS_GLOBAL_ANALYSIS",
                "dataset": DATASET,
                "grid_resolution": "0.4deg",
                "method": "MODEL_ANALYSIS_INSTANT_PM_US_AQI_PROXY",
                "aqi_standard": "US EPA 2024 PM breakpoints applied to instantaneous CAMS model concentration; not observed/regulatory AQI",
                "requested_date": selected_date,
                "sampled_time": max(times) if times else None,
                "points": points,
                "detail": "CAMS global analysis PM2.5/PM10; coarse-grid model estimate",
            }
        finally:
            for item in opened:
                item.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("ADS_API_KEY", "").strip()
    if not key:
        payload = _empty("CREDENTIALS_MISSING", "Set GitHub Actions secret ADS_API_KEY after accepting the CAMS dataset licence")
    else:
        try:
            payload = collect(key)
        except Exception as exc:
            payload = _empty("UNAVAILABLE", f"{type(exc).__name__}: {exc}")
    _write(args.output, payload)
    print(json.dumps({"status": payload["status"], "sampled_time": payload.get("sampled_time"), "detail": payload.get("detail"), "points": payload.get("points", {})}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
