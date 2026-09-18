"""Collect a free, non-critical Himawari-9 convective observation layer.

Source: NOAA Open Data / JMA Himawari-9 AHI L2 full-disk cloud-height product.
The collector intentionally publishes two separate concepts:
  * satellite convective signal: derived from observed cloud-top fields
  * lightning observation: NOT_CONNECTED unless a future direct strike feed exists

It never mutates or gates the existing Weather Lab backend.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.points import POINTS
from weather.processing.convective_proxy import convective_signal

BUCKET = "noaa-himawari9"
PREFIX_ROOT = "AHI-L2-FLDK-Clouds"
# Keep the signal local enough for operations. At the nominal 2 km nadir
# sampling this is about a 40 km radius-equivalent square. Himawari sampling is
# coarser away from nadir, so the label is intentionally approximate.
RADIUS_PIXELS = 20

# V5 spatial nowcast domain. This is a renderer sampling grid, not a claim that
# the satellite native resolution is 0.05°. The source remains Himawari AHI L2
# (~2 km at nadir, coarser away from nadir).
SPATIAL_BOUNDS = {
    "south": 9.70,
    "north": 10.55,
    "west": 103.65,
    "east": 104.30,
}
SPATIAL_STEP_DEG = 0.05


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _empty(status: str, detail: str) -> dict:
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "JMA_HIMAWARI9_VIA_NOAA_OPEN_DATA",
        "dataset": "AHI-L2-FLDK-Clouds/AHI-CHGT",
        "source_type": "OBSERVED_SATELLITE",
        "lightning_observed": {
            "status": "NOT_CONNECTED",
            "count_30m": None,
            "nearest_km": None,
            "detail": "Không có feed sét quan trắc trực tiếp miễn phí đã được xác minh quyền sử dụng. Không suy diễn proxy vệ tinh thành tia sét quan sát.",
        },
        "points": {},
        "detail": detail,
    }


def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")


def _recent_keys(client) -> list[dict]:
    now = datetime.now(timezone.utc)
    found: list[dict] = []
    for hours_back in range(0, 30):
        stamp = now - timedelta(hours=hours_back)
        hour_prefix = f"{PREFIX_ROOT}/{stamp:%Y/%m/%d/%H}"
        response = client.list_objects_v2(Bucket=BUCKET, Prefix=hour_prefix, MaxKeys=1000)
        for item in response.get("Contents", []):
            key = item.get("Key", "")
            if "/AHI-CHGT_" in key and key.endswith(".nc"):
                found.append({"key": key, "last_modified": item.get("LastModified")})
        if len(found) >= 4:
            break
    found.sort(key=lambda x: x.get("last_modified") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return found


def _pick_scans(items: list[dict]) -> tuple[dict | None, dict | None]:
    if not items:
        return None, None
    latest = items[0]
    t0 = latest.get("last_modified")
    previous = None
    if t0:
        for item in items[1:]:
            ti = item.get("last_modified")
            if ti and 10 * 60 <= (t0 - ti).total_seconds() <= 40 * 60:
                previous = item
                break
    return latest, previous


def _target_xy(ds, lat: float, lon: float) -> tuple[int, int]:
    import numpy as np
    from pyproj import CRS, Transformer

    crs = CRS.from_proj4(
        "+proj=geos +lon_0=140.7 +h=35785863 +a=6378137 +b=6356752.3 +units=m +no_defs"
    )
    x_m, y_m = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)

    x = np.asarray(ds["x"].values, dtype=float) if "x" in ds.variables else None
    y = np.asarray(ds["y"].values, dtype=float) if "y" in ds.variables else None
    if x is None or y is None or x.size != 5500 or y.size != 5500:
        ix = int(round(2749.5 + x_m / 2000.0))
        iy = int(round(2749.5 - y_m / 2000.0))
        return max(0, min(5499, ix)), max(0, min(5499, iy))

    x_target, y_target = x_m, y_m
    if float(np.nanmax(np.abs(x))) < 1.0:
        x_target = x_m / 35785863.0
    if float(np.nanmax(np.abs(y))) < 1.0:
        y_target = y_m / 35785863.0
    ix = int(np.nanargmin(np.abs(x - x_target)))
    iy = int(np.nanargmin(np.abs(y - y_target)))
    return ix, iy


def _temp_stats(array) -> tuple[float | None, float | None, float | None]:
    import numpy as np

    values = np.asarray(array, dtype=float)
    values = values[np.isfinite(values)]
    values = values[(values >= 180) & (values <= 340)]
    if not values.size:
        return None, None, None
    c = values - 273.15
    return float(np.min(c)), float(np.nanpercentile(c, 5)), float(np.nanmedian(c))


def _height_stats(array) -> tuple[float | None, float | None, float | None]:
    import numpy as np

    values = np.asarray(array, dtype=float)
    values = values[np.isfinite(values)]
    values = values[(values >= -300) & (values <= 20000)]
    if not values.size:
        return None, None, None
    return float(np.max(values)), float(np.nanpercentile(values, 95)), float(np.nanmedian(values))


def _sample(ds, lat: float, lon: float) -> dict:
    ix, iy = _target_xy(ds, lat, lon)
    y0, y1 = max(0, iy - RADIUS_PIXELS), min(5500, iy + RADIUS_PIXELS + 1)
    x0, x1 = max(0, ix - RADIUS_PIXELS), min(5500, ix + RADIUS_PIXELS + 1)

    temp_key = "CldTopTempAWIPS" if "CldTopTempAWIPS" in ds.variables else "CldTopTemp"
    height_key = "CldTopHghtAWIPS" if "CldTopHghtAWIPS" in ds.variables else "CldTopHght"
    temp = ds[temp_key].isel(y=slice(y0, y1), x=slice(x0, x1)) if "y" in ds[temp_key].dims else ds[temp_key].isel(Rows=slice(y0, y1), Columns=slice(x0, x1))
    height = ds[height_key].isel(y=slice(y0, y1), x=slice(x0, x1)) if "y" in ds[height_key].dims else ds[height_key].isel(Rows=slice(y0, y1), Columns=slice(x0, x1))

    min_temp_c, cold_temp_c, median_temp_c = _temp_stats(temp.values)
    max_height_m, high_height_m, median_height_m = _height_stats(height.values)
    return {
        "pixel_x": ix,
        "pixel_y": iy,
        "regional_min_cloud_top_temp_c": round(min_temp_c, 1) if min_temp_c is not None else None,
        "regional_cold_cloud_top_temp_c": round(cold_temp_c, 1) if cold_temp_c is not None else None,
        "regional_median_cloud_top_temp_c": round(median_temp_c, 1) if median_temp_c is not None else None,
        "regional_max_cloud_top_height_m": round(max_height_m) if max_height_m is not None else None,
        "regional_high_cloud_top_height_m": round(high_height_m) if high_height_m is not None else None,
        "regional_median_cloud_top_height_m": round(median_height_m) if median_height_m is not None else None,
    }



def _axis(start: float, end: float, step: float) -> list[float]:
    values = []
    value = start
    while value <= end + 1e-9:
        values.append(round(value, 4))
        value += step
    return values


def _spatial_sample(ds, lat: float, lon: float) -> dict:
    """Small local satellite sample used only to preserve spatial structure."""
    if ds is None:
        return {}
    ix, iy = _target_xy(ds, lat, lon)
    y0, y1 = max(0, iy - 1), min(5500, iy + 2)
    x0, x1 = max(0, ix - 1), min(5500, ix + 2)
    temp_key = "CldTopTempAWIPS" if "CldTopTempAWIPS" in ds.variables else "CldTopTemp"
    height_key = "CldTopHghtAWIPS" if "CldTopHghtAWIPS" in ds.variables else "CldTopHght"
    temp = ds[temp_key].isel(y=slice(y0, y1), x=slice(x0, x1)) if "y" in ds[temp_key].dims else ds[temp_key].isel(Rows=slice(y0, y1), Columns=slice(x0, x1))
    height = ds[height_key].isel(y=slice(y0, y1), x=slice(x0, x1)) if "y" in ds[height_key].dims else ds[height_key].isel(Rows=slice(y0, y1), Columns=slice(x0, x1))
    _, cold_c, median_c = _temp_stats(temp.values)
    _, high_m, median_m = _height_stats(height.values)
    return {
        "cloud_top_cold_c": round(cold_c, 1) if cold_c is not None else None,
        "cloud_top_median_c": round(median_c, 1) if median_c is not None else None,
        "cloud_top_high_m": round(high_m) if high_m is not None else None,
        "cloud_top_median_m": round(median_m) if median_m is not None else None,
    }


def _spatial_field(ds_now, ds_prev, now_time: str, prev_time: str | None) -> dict:
    lats = _axis(SPATIAL_BOUNDS["south"], SPATIAL_BOUNDS["north"], SPATIAL_STEP_DEG)
    lons = _axis(SPATIAL_BOUNDS["west"], SPATIAL_BOUNDS["east"], SPATIAL_STEP_DEG)
    current_cells = []
    previous_cells = []

    for lat in lats:
        for lon in lons:
            current = _spatial_sample(ds_now, lat, lon)
            earlier = _spatial_sample(ds_prev, lat, lon) if ds_prev is not None else {}
            cur = current.get("cloud_top_cold_c")
            old = earlier.get("cloud_top_cold_c")
            cooling = round(cur - old, 1) if cur is not None and old is not None else None
            signal = convective_signal(
                current.get("cloud_top_cold_c"),
                current.get("cloud_top_high_m"),
                cooling,
            )
            current_cells.append({
                "lat": lat,
                "lon": lon,
                **current,
                "cooling_c_per_20m_proxy": cooling,
                "convective_score": signal["score"],
                "convective_level": signal["level"],
            })
            if earlier:
                earlier_signal = convective_signal(
                    earlier.get("cloud_top_cold_c"),
                    earlier.get("cloud_top_high_m"),
                    None,
                )
                previous_cells.append({
                    "lat": lat,
                    "lon": lon,
                    **earlier,
                    "cooling_c_per_20m_proxy": None,
                    "convective_score": earlier_signal["score"],
                    "convective_level": earlier_signal["level"],
                })

    frames = []
    if previous_cells and prev_time:
        frames.append({"sampled_time": str(prev_time), "cells": previous_cells})
    frames.append({"sampled_time": str(now_time), "cells": current_cells})
    return {
        "status": "READY" if current_cells else "UNAVAILABLE",
        "bounds": SPATIAL_BOUNDS,
        "display_grid_deg": SPATIAL_STEP_DEG,
        "cell_count": len(current_cells),
        "source_native_resolution": "2 km at nadir; coarser away from nadir",
        "sampling_method": "REGULAR_LATLON_RENDER_GRID_FROM_HIMAWARI_AHI_L2_CLOUD_TOP",
        "display_interpolation": "RENDER_ONLY",
        "frames": frames,
        "note": "Observed satellite cloud-top field. It is not radar rainfall and not lightning observation.",
    }


def _open_s3_dataset(fs, key: str):
    import xarray as xr

    handle = fs.open(f"{BUCKET}/{key}", "rb", block_size=8 * 1024 * 1024)
    ds = xr.open_dataset(handle, engine="h5netcdf", decode_cf=True, mask_and_scale=True)
    return ds, handle


def collect() -> dict:
    import s3fs

    client = _s3_client()
    keys = _recent_keys(client)
    latest, previous = _pick_scans(keys)
    if not latest:
        return _empty("UNAVAILABLE", "Không tìm thấy AHI-CHGT gần đây trong NOAA Open Data")

    fs = s3fs.S3FileSystem(anon=True, default_fill_cache=False)
    ds_now = handle_now = ds_prev = handle_prev = None
    try:
        ds_now, handle_now = _open_s3_dataset(fs, latest["key"])
        if previous:
            ds_prev, handle_prev = _open_s3_dataset(fs, previous["key"])

        now_time = ds_now.attrs.get("time_coverage_start") or latest.get("last_modified")
        prev_time = ds_prev.attrs.get("time_coverage_start") if ds_prev is not None else None
        if isinstance(now_time, datetime):
            now_time = now_time.isoformat()
        if isinstance(prev_time, datetime):
            prev_time = prev_time.isoformat()

        spatial = _spatial_field(ds_now, ds_prev, str(now_time), str(prev_time) if prev_time else None)

        points = {}
        for point_id, (lat, lon) in POINTS.items():
            current = _sample(ds_now, lat, lon)
            earlier = _sample(ds_prev, lat, lon) if ds_prev is not None else {}
            cooling = None
            cur = current.get("regional_cold_cloud_top_temp_c")
            old = earlier.get("regional_cold_cloud_top_temp_c")
            if cur is not None and old is not None:
                cooling = round(cur - old, 1)
            signal = convective_signal(
                current.get("regional_cold_cloud_top_temp_c"),
                current.get("regional_high_cloud_top_height_m"),
                cooling,
            )
            points[point_id] = {
                "lat": lat,
                "lon": lon,
                **current,
                "cooling_c_per_20m_proxy": cooling,
                "convective_signal": signal,
                "lightning_observed": "NOT_CONNECTED",
            }

        return {
            "status": "POINT_NUMERIC_READY",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sampled_time": str(now_time),
            "previous_sampled_time": str(prev_time) if prev_time else None,
            "source": "JMA_HIMAWARI9_VIA_NOAA_OPEN_DATA",
            "dataset": "AHI-L2-FLDK-Clouds/AHI-CHGT",
            "source_type": "OBSERVED_SATELLITE",
            "observation_resolution": "2 km at nadir; full-disk ~10 minute cadence",
            "regional_envelope": "~40 km radius-equivalent local window around each point",
            "robust_signal_sampling": "cloud-top temperature p05 + height p95; absolute extrema retained for diagnostics",
            "lightning_observed": {
                "status": "NOT_CONNECTED",
                "count_30m": None,
                "nearest_km": None,
                "detail": "Chưa có feed sét quan trắc trực tiếp miễn phí với quyền sử dụng phù hợp. Convective signal bên dưới là proxy từ quan sát vệ tinh, không phải tia sét quan sát.",
            },
            "radar": {
                "status": "MANUAL_OFFICIAL_SOURCE",
                "source": "NCHMF",
                "detail": "Radar chính thức vẫn là lớp kiểm tra thủ công; không được dùng làm dependency của collector này.",
            },
            "points": points,
            "spatial": spatial,
            "method": "Observed Himawari cloud-top p05 temperature/p95 height + cooling heuristic; local ~40 km window; not lightning detection",
            "latest_object": latest["key"],
            "previous_object": previous["key"] if previous else None,
        }
    finally:
        for ds in (ds_now, ds_prev):
            try:
                if ds is not None:
                    ds.close()
            except Exception:
                pass
        for handle in (handle_now, handle_prev):
            try:
                if handle is not None:
                    handle.close()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = collect()
    except Exception as exc:
        payload = _empty("UNAVAILABLE", f"{type(exc).__name__}: {exc}")
    _write(args.output, payload)
    print(json.dumps({
        "status": payload.get("status"),
        "sampled_time": payload.get("sampled_time"),
        "points": {k: v.get("convective_signal") for k, v in payload.get("points", {}).items()},
        "spatial_cells": (payload.get("spatial") or {}).get("cell_count"),
        "spatial_frames": len((payload.get("spatial") or {}).get("frames") or []),
        "detail": payload.get("detail"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
