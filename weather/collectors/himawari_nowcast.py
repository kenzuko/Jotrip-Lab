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
import math
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
    # Include the Gulf corridor through Rach Gia so short-range convective
    # evolution is visible on both ends of the Phu Quoc transport axis.
    "east": 105.40,
}
SPATIAL_STEP_DEG = 0.05

# Coastal corridor anchors are used only to describe where observed cloud fields
# are located. They do not become atmospheric ACTUAL stations or model points.
CORRIDOR_WATCH = {
    "ha_tien": {"name": "Hà Tiên", "lat": 10.3831, "lon": 104.487534},
    "rach_gia": {"name": "Rạch Giá", "lat": 10.00677, "lon": 105.07845},
}
MOTION_RADIUS_KM = 150.0
MOTION_SCORE_MIN = 70.0


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



def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _cardinal(deg: float | None) -> str | None:
    if deg is None:
        return None
    labels = ("Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc")
    return labels[int((deg + 22.5) // 45.0) % 8]


def _weighted_cloud_centroid(cells: list[dict], target_lat: float, target_lon: float) -> dict | None:
    selected = []
    for cell in cells:
        score = cell.get("convective_score")
        try:
            score = float(score)
            lat = float(cell.get("lat"))
            lon = float(cell.get("lon"))
        except (TypeError, ValueError):
            continue
        if score < MOTION_SCORE_MIN:
            continue
        dist = _haversine_km(target_lat, target_lon, lat, lon)
        if dist > MOTION_RADIUS_KM:
            continue
        # Stronger and nearer convective cloud gets more influence, while still
        # preserving broad spatial motion instead of chasing one noisy pixel.
        weight = max(1.0, score - 35.0) * math.exp(-dist / 110.0)
        selected.append((lat, lon, score, dist, weight))
    if not selected:
        return None
    total = sum(row[4] for row in selected)
    lat = sum(row[0] * row[4] for row in selected) / total
    lon = sum(row[1] * row[4] for row in selected) / total
    return {
        "lat": lat,
        "lon": lon,
        "support_cells": len(selected),
        "max_score": max(row[2] for row in selected),
        "mean_score": sum(row[2] * row[4] for row in selected) / total,
        "distance_to_target_km": _haversine_km(lat, lon, target_lat, target_lon),
    }


def _nearest_corridor(lat: float, lon: float) -> dict | None:
    candidates = []
    for key, anchor in CORRIDOR_WATCH.items():
        dist = _haversine_km(lat, lon, anchor["lat"], anchor["lon"])
        candidates.append((dist, key, anchor))
    if not candidates:
        return None
    dist, key, anchor = min(candidates, key=lambda row: row[0])
    # Do not attach a place-name to a cloud mass that is nowhere near it.
    if dist > 70.0:
        return None
    return {"id": key, "name": anchor["name"], "distance_km": round(dist, 1)}


def _cloud_motion_for_target(spatial: dict, target_lat: float, target_lon: float) -> dict:
    frames = list(spatial.get("frames") or [])
    if len(frames) < 2:
        return {
            "status": "INSUFFICIENT_FRAMES",
            "method": "HIMAWARI_TWO_FRAME_WEIGHTED_CENTROID_V1",
            "eta_minutes": None,
        }
    current = frames[-1]
    cur_t = _parse_iso(current.get("sampled_time"))
    previous = frames[-2]
    # Prefer a 20-40 minute baseline when the archive provides enough frames.
    # Ten-minute cloud-top fields can move less than one render-grid cell and
    # produce a noisy heading; the longer baseline improves direction/ETA.
    if cur_t:
        for candidate in reversed(frames[:-1]):
            candidate_t = _parse_iso(candidate.get("sampled_time"))
            if not candidate_t:
                continue
            gap_min = (cur_t - candidate_t).total_seconds() / 60.0
            if 20.0 <= gap_min <= 40.0:
                previous = candidate
                break
    prev_t = _parse_iso(previous.get("sampled_time"))
    if not prev_t or not cur_t:
        return {"status": "INVALID_TIME", "method": "HIMAWARI_TWO_FRAME_WEIGHTED_CENTROID_V1", "eta_minutes": None}
    dt_h = (cur_t - prev_t).total_seconds() / 3600.0
    if dt_h <= 0 or dt_h > 1.0:
        return {"status": "INVALID_INTERVAL", "method": "HIMAWARI_TWO_FRAME_WEIGHTED_CENTROID_V1", "eta_minutes": None}

    prev_c = _weighted_cloud_centroid(previous.get("cells") or [], target_lat, target_lon)
    cur_c = _weighted_cloud_centroid(current.get("cells") or [], target_lat, target_lon)
    if not prev_c or not cur_c:
        return {
            "status": "NO_TRACKABLE_CONVECTIVE_CLOUD",
            "method": "HIMAWARI_TWO_FRAME_WEIGHTED_CENTROID_V1",
            "eta_minutes": None,
        }

    displacement = _haversine_km(prev_c["lat"], prev_c["lon"], cur_c["lat"], cur_c["lon"])
    speed = displacement / dt_h
    heading = _bearing_deg(prev_c["lat"], prev_c["lon"], cur_c["lat"], cur_c["lon"]) if displacement >= 1.0 else None
    toward = _bearing_deg(cur_c["lat"], cur_c["lon"], target_lat, target_lon)
    source_bearing = _bearing_deg(target_lat, target_lon, cur_c["lat"], cur_c["lon"])
    alignment = _angle_diff(heading, toward) if heading is not None else None
    distance = cur_c["distance_to_target_km"]

    reliable_speed = 4.0 <= speed <= 100.0
    corridor = _nearest_corridor(cur_c["lat"], cur_c["lon"])
    confidence = "LOW"
    if cur_c["support_cells"] >= 4 and prev_c["support_cells"] >= 4 and reliable_speed:
        confidence = "MEDIUM"
    if cur_c["support_cells"] >= 8 and prev_c["support_cells"] >= 8 and reliable_speed and displacement >= 3.0:
        confidence = "MEDIUM_HIGH"

    # Public arrival guidance must be stricter than merely saying a cloud mass is
    # "approaching". Project the observed motion vector and ask whether it
    # intersects an 18 km operational radius around the target within 3 hours.
    # LOW-confidence tracks remain diagnostic only and never produce a public ETA.
    impact_radius_km = 18.0
    horizon_h = 3.0
    track_usable = confidence in {"MEDIUM", "MEDIUM_HIGH"} and reliable_speed and heading is not None
    predicted_impact = False
    eta = None
    exit_eta = None
    closest_approach_km = None
    closest_approach_minutes = None
    state = "NEARBY" if distance <= impact_radius_km else ("TRACK_UNCERTAIN" if not track_usable else "TRACKED")

    if distance <= impact_radius_km:
        predicted_impact = True
        eta = 0
        closest_approach_km = round(distance, 1)
        closest_approach_minutes = 0
    elif track_usable:
        # Local tangent-plane approximation is sufficient over this <=150 km domain.
        mean_lat = math.radians((cur_c["lat"] + target_lat) / 2.0)
        east_km = math.radians(target_lon - cur_c["lon"]) * 6371.0088 * math.cos(mean_lat)
        north_km = math.radians(target_lat - cur_c["lat"]) * 6371.0088
        hrad = math.radians(heading)
        vx = speed * math.sin(hrad)
        vy = speed * math.cos(hrad)
        speed2 = vx * vx + vy * vy
        dot = east_km * vx + north_km * vy
        t_closest = dot / speed2 if speed2 > 0 else -1.0

        if t_closest >= 0:
            cx = east_km - vx * t_closest
            cy = north_km - vy * t_closest
            closest = math.sqrt(cx * cx + cy * cy)
            closest_approach_km = round(closest, 1)
            closest_approach_minutes = round(t_closest * 60.0)

            if t_closest <= horizon_h and closest <= impact_radius_km:
                # Solve entry/exit times for the impact-radius circle.
                c = east_km * east_km + north_km * north_km - impact_radius_km * impact_radius_km
                disc = max(0.0, dot * dot - speed2 * c)
                root = math.sqrt(disc)
                t_enter = max(0.0, (dot - root) / speed2)
                t_exit = max(t_enter, (dot + root) / speed2)
                if t_enter <= horizon_h:
                    predicted_impact = True
                    eta = round(t_enter * 60.0)
                    exit_eta = round(min(t_exit, horizon_h) * 60.0)
                    state = "IMPACT_EXPECTED"
                else:
                    state = "BEYOND_HORIZON"
            elif t_closest > horizon_h:
                state = "BEYOND_HORIZON"
            else:
                state = "PASSING_BY"
        else:
            state = "MOVING_AWAY"

    approaching = bool(predicted_impact and eta is not None and eta > 0)
    arrival_time = (cur_t + timedelta(minutes=eta)).isoformat() if eta is not None and cur_t else None
    exit_time = (cur_t + timedelta(minutes=exit_eta)).isoformat() if exit_eta is not None and cur_t else None

    return {
        "status": state,
        "sampled_time": current.get("sampled_time"),
        "previous_sampled_time": previous.get("sampled_time"),
        "cloud_center_lat": round(cur_c["lat"], 4),
        "cloud_center_lon": round(cur_c["lon"], 4),
        "distance_to_target_km": round(distance, 1),
        "source_bearing_deg": round(source_bearing, 1),
        "source_sector": _cardinal(source_bearing),
        "nearest_corridor": corridor,
        "motion_heading_deg": round(heading, 1) if heading is not None else None,
        "motion_heading": _cardinal(heading),
        "motion_speed_kmh": round(speed, 1) if reliable_speed else None,
        "alignment_to_target_deg": round(alignment, 1) if alignment is not None else None,
        "approaching": approaching,
        "predicted_impact": predicted_impact,
        "impact_radius_km": impact_radius_km,
        "eta_minutes": eta,
        "arrival_time": arrival_time,
        "exit_eta_minutes": exit_eta,
        "exit_time": exit_time,
        "closest_approach_km": closest_approach_km,
        "closest_approach_minutes": closest_approach_minutes,
        "support_cells": cur_c["support_cells"],
        "max_convective_score": round(cur_c["max_score"], 1),
        "tracking_confidence": confidence,
        "public_track_usable": track_usable,
        "method": "HIMAWARI_PATH_INTERSECTION_V2",
        "note": "ETA chỉ phát khi đường đi đủ ổn định và quỹ đạo ngoại suy cắt bán kính 18 km quanh điểm trong 3 giờ; đây không phải cam kết thời điểm bắt đầu mưa.",
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
    payload = {
        "status": "READY" if current_cells else "UNAVAILABLE",
        "bounds": SPATIAL_BOUNDS,
        "display_grid_deg": SPATIAL_STEP_DEG,
        "cell_count": len(current_cells),
        "source_native_resolution": "2 km at nadir; coarser away from nadir",
        "sampling_method": "REGULAR_LATLON_RENDER_GRID_FROM_HIMAWARI_AHI_L2_CLOUD_TOP",
        "display_interpolation": "RENDER_ONLY",
        "frames": frames,
        "corridor_watch": CORRIDOR_WATCH,
        "note": "Observed satellite cloud-top field. It is not radar rainfall and not lightning observation.",
    }
    payload["corridor_motion"] = {
        key: _cloud_motion_for_target(payload, anchor["lat"], anchor["lon"])
        for key, anchor in CORRIDOR_WATCH.items()
    }
    return payload


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
                "cloud_motion": _cloud_motion_for_target(spatial, lat, lon),
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
