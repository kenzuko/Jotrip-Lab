"""Shadow-only CMAX component tracking and ETA candidate generation."""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Iterable

EARTH_KM = 6371.0088


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    q = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(q))


def _xy_km(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    y = (lat - origin_lat) * 111.32
    x = (lon - origin_lon) * 111.32 * math.cos(math.radians(origin_lat))
    return x, y


def _heading(dx: float, dy: float) -> float:
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def _cardinal(deg: float) -> str:
    labels = ("Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc")
    return labels[int((deg + 22.5) // 45) % 8]


def _components(receipt: dict[str, Any], threshold_dbz: int) -> list[dict[str, Any]]:
    return list(
        (((receipt.get("local_features") or {}).get("components_by_threshold") or {})
         .get(f"{threshold_dbz}dbz") or [])
    )


def match_components(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    threshold_dbz: int = 20,
    max_speed_kmh: float = 120.0,
) -> dict[str, Any]:
    t0, t1 = _dt(previous.get("observed_at")), _dt(current.get("observed_at"))
    if not t0 or not t1 or t1 <= t0:
        return {"status": "NO_VALID_TIME_PAIR", "tracks": []}
    dt_hours = (t1 - t0).total_seconds() / 3600.0
    if dt_hours > 0.75:
        return {"status": "PAIR_TOO_FAR_APART", "tracks": [], "dt_minutes": round(dt_hours * 60, 1)}

    prev = _components(previous, threshold_dbz)
    cur = _components(current, threshold_dbz)
    candidates: list[tuple[float, int, int]] = []
    for i, a in enumerate(prev):
        for j, b in enumerate(cur):
            d = haversine_km(
                float(a["centroid_lat"]), float(a["centroid_lon"]),
                float(b["centroid_lat"]), float(b["centroid_lon"]),
            )
            speed = d / dt_hours
            if speed <= max_speed_kmh:
                candidates.append((d, i, j))
    candidates.sort()

    used_prev: set[int] = set()
    used_cur: set[int] = set()
    tracks = []
    for distance, i, j in candidates:
        if i in used_prev or j in used_cur:
            continue
        a, b = prev[i], cur[j]
        ox, oy = _xy_km(
            float(b["centroid_lat"]), float(b["centroid_lon"]),
            float(a["centroid_lat"]), float(a["centroid_lon"]),
        )
        speed = math.hypot(ox, oy) / dt_hours
        heading = _heading(ox, oy)
        tracks.append({
            "track_id": f"{threshold_dbz}dbz-{i+1:03d}-{j+1:03d}",
            "threshold_dbz": threshold_dbz,
            "previous_component_id": a.get("component_id"),
            "current_component_id": b.get("component_id"),
            "previous_centroid": [a["centroid_lat"], a["centroid_lon"]],
            "current_centroid": [b["centroid_lat"], b["centroid_lon"]],
            "dt_minutes": round(dt_hours * 60, 1),
            "displacement_km": round(distance, 2),
            "speed_kmh": round(speed, 1),
            "heading_deg": round(heading, 1),
            "heading": _cardinal(heading),
            "max_dbz_previous": a.get("max_dbz"),
            "max_dbz_current": b.get("max_dbz"),
            "area_km2_previous": a.get("area_km2"),
            "area_km2_current": b.get("area_km2"),
            "touches_invalid_pixels": bool(a.get("touches_invalid_pixels") or b.get("touches_invalid_pixels")),
            "tracking_confidence": "LOW_TWO_FRAME_SHADOW",
        })
        used_prev.add(i)
        used_cur.add(j)
    return {
        "status": "TRACKS_READY" if tracks else "NO_MATCHED_COMPONENTS",
        "threshold_dbz": threshold_dbz,
        "dt_minutes": round(dt_hours * 60, 1),
        "tracks": tracks,
    }


def eta_candidates(
    tracking: dict[str, Any],
    points: dict[str, dict[str, Any]],
    *,
    impact_radius_km: float = 15.0,
    max_nowcast_minutes: int = 120,
) -> list[dict[str, Any]]:
    results = []
    for track in tracking.get("tracks") or []:
        if track.get("speed_kmh", 0) < 2:
            continue
        prev_lat, prev_lon = map(float, track["previous_centroid"])
        cur_lat, cur_lon = map(float, track["current_centroid"])
        vx, vy = _xy_km(cur_lat, cur_lon, prev_lat, prev_lon)
        dt_h = float(track["dt_minutes"]) / 60.0
        vx /= dt_h
        vy /= dt_h

        for point_id, point in points.items():
            px, py = _xy_km(float(point["lat"]), float(point["lon"]), cur_lat, cur_lon)
            vv = vx * vx + vy * vy
            if vv <= 0:
                continue
            t_h = (px * vx + py * vy) / vv
            if t_h < 0 or t_h * 60 > max_nowcast_minutes:
                continue
            closest_x, closest_y = vx * t_h, vy * t_h
            miss = math.hypot(px - closest_x, py - closest_y)
            if miss > impact_radius_km:
                continue
            eta = round(t_h * 60)
            if eta <= 30:
                window = "0_30_MIN"
            elif eta <= 60:
                window = "30_60_MIN"
            else:
                window = "60_120_MIN"
            results.append({
                "track_id": track["track_id"],
                "point_id": point_id,
                "eta_minutes": eta,
                "window": window,
                "closest_approach_km": round(miss, 1),
                "speed_kmh": track["speed_kmh"],
                "heading_deg": track["heading_deg"],
                "heading": track["heading"],
                "max_dbz_current": track["max_dbz_current"],
                "touches_invalid_pixels": track["touches_invalid_pixels"],
                "confidence": "LOW_TWO_FRAME_SHADOW",
                "public_usable": False,
                "meaning": "RADAR_ECHO_PATH_CANDIDATE_NOT_RAIN_START_TIME",
            })
    return sorted(results, key=lambda row: (row["eta_minutes"], row["point_id"]))
