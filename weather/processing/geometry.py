"""Route geometry helpers without false sub-grid precision."""
from __future__ import annotations

import math


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def heading_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1)


def sample_route(points: list[list[float]], native_grid_km: float, maximum_spacing_km: float = 5.0) -> list[dict]:
    if len(points) < 2:
        raise ValueError("route needs at least two points")
    spacing = max(1.0, min(float(maximum_spacing_km), float(native_grid_km)))
    samples = []
    for segment, (start_raw, end_raw) in enumerate(zip(points, points[1:])):
        start, end = tuple(start_raw), tuple(end_raw)
        distance = haversine_km(start, end)
        divisions = max(1, math.ceil(distance / spacing))
        for index in range(divisions + 1):
            if segment and index == 0:
                continue
            fraction = index / divisions
            coordinate = [round(start[0] + (end[0] - start[0]) * fraction, 6),
                          round(start[1] + (end[1] - start[1]) * fraction, 6)]
            samples.append({"segment_id": f"s{segment + 1}", "coordinate": coordinate,
                            "heading_deg": heading_deg(start, end), "native_grid_km": native_grid_km,
                            "requested_spacing_km": maximum_spacing_km, "effective_spacing_km": round(distance / divisions, 3)})
    return samples
