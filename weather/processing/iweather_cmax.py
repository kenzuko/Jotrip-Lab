"""Deterministic decoder for iWeather public COM/CMAX rendered radar frames.

Shadow/research use only.

The current public iWeather map bundle decodes the normal
`image-overlay-radar` product by reading the red channel as the scalar value.
The UI labels CMAX in dBZ. Pixels with large sentinel-like red values are not
meteorological reflectivity and are excluded here.

This module does not fetch anything. Callers supply in-memory PNG bytes and
explicit geographic bounds. No source image needs to be persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Any, Mapping

from PIL import Image


@dataclass(frozen=True)
class GeoBounds:
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float


# CMAX UI is displayed on a 0..60 dBZ legend. Keep a small headroom for raw
# values while rejecting 254/255 sentinel/background values seen in the public
# product. We deliberately do not turn rejected pixels into zero.
MAX_PLAUSIBLE_DBZ = 100.0


LOCAL_DOMAIN = GeoBounds(
    lon_min=103.25,
    lon_max=104.65,
    lat_min=9.65,
    lat_max=10.70,
)
ECHO_THRESHOLDS_DBZ = (10.0, 20.0, 35.0)
MIN_COMPONENT_PIXELS = 3


def _latlon_from_pixel(x: float, y: float, bounds: GeoBounds, width: int, height: int) -> tuple[float, float]:
    lon = bounds.lon_min + ((x + 0.5) / width) * (bounds.lon_max - bounds.lon_min)
    lat = bounds.lat_max - ((y + 0.5) / height) * (bounds.lat_max - bounds.lat_min)
    return lat, lon


def _crop_indices(domain: GeoBounds, bounds: GeoBounds, width: int, height: int) -> tuple[int, int, int, int]:
    # Clip the requested local domain to the source raster.
    lon0 = max(domain.lon_min, bounds.lon_min)
    lon1 = min(domain.lon_max, bounds.lon_max)
    lat0 = max(domain.lat_min, bounds.lat_min)
    lat1 = min(domain.lat_max, bounds.lat_max)
    if lon0 >= lon1 or lat0 >= lat1:
        raise ValueError("local radar domain does not intersect source bounds")
    x0, y1f = _pixel_xy(lat0, lon0, bounds, width, height)
    x1f, y0 = _pixel_xy(lat1, lon1, bounds, width, height)
    return (
        max(0, int(math.floor(min(x0, x1f)))),
        min(width - 1, int(math.ceil(max(x0, x1f)))),
        max(0, int(math.floor(min(y0, y1f)))),
        min(height - 1, int(math.ceil(max(y0, y1f)))),
    )


def _extract_local_components(
    img: Image.Image,
    *,
    bounds: GeoBounds,
    domain: GeoBounds = LOCAL_DOMAIN,
    thresholds: tuple[float, ...] = ECHO_THRESHOLDS_DBZ,
) -> dict[str, Any]:
    """Extract small connected echo objects without persisting the source raster.

    The resulting components are intended for shadow tracking. They are not
    calibrated rainfall objects and must not be presented as surface rain.
    """
    width, height = img.size
    x0, x1, y0, y1 = _crop_indices(domain, bounds, width, height)
    px = img.load()

    decoded: dict[tuple[int, int], float | None] = {}
    valid = 0
    invalid = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            v = _decode_rgb(px[x, y])
            decoded[(x, y)] = v
            if v is None:
                invalid += 1
            else:
                valid += 1

    center_lat = (domain.lat_min + domain.lat_max) / 2.0
    km_x, km_y = _km_per_pixel(center_lat, bounds, width, height)
    pixel_area_km2 = km_x * km_y

    components_by_threshold: dict[str, list[dict[str, Any]]] = {}
    echo_fraction_by_threshold: dict[str, float | None] = {}

    for threshold in thresholds:
        active = {
            coord for coord, value in decoded.items()
            if value is not None and value >= threshold
        }
        echo_fraction_by_threshold[f"{int(threshold)}dbz"] = (
            round(len(active) / valid, 6) if valid else None
        )
        visited: set[tuple[int, int]] = set()
        components: list[dict[str, Any]] = []

        for seed in active:
            if seed in visited:
                continue
            stack = [seed]
            visited.add(seed)
            cells: list[tuple[int, int, float]] = []
            touches_invalid = False
            while stack:
                x, y = stack.pop()
                value = decoded[(x, y)]
                if value is None:
                    continue
                cells.append((x, y, float(value)))
                for dx, dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
                    n = (x + dx, y + dy)
                    if n not in decoded:
                        continue
                    nv = decoded[n]
                    if nv is None:
                        touches_invalid = True
                    elif nv >= threshold and n not in visited:
                        visited.add(n)
                        stack.append(n)

            if len(cells) < MIN_COMPONENT_PIXELS:
                continue

            weights = [max(1.0, v) for _, _, v in cells]
            sw = sum(weights)
            cx = sum((x + 0.5) * w for (x, _, _), w in zip(cells, weights)) / sw
            cy = sum((y + 0.5) * w for (_, y, _), w in zip(cells, weights)) / sw
            centroid_lat, centroid_lon = _latlon_from_pixel(cx - 0.5, cy - 0.5, bounds, width, height)
            xs = [x for x, _, _ in cells]
            ys = [y for _, y, _ in cells]
            values = [v for _, _, v in cells]
            bbox_nw = _latlon_from_pixel(min(xs), min(ys), bounds, width, height)
            bbox_se = _latlon_from_pixel(max(xs), max(ys), bounds, width, height)

            components.append({
                "threshold_dbz": threshold,
                "pixel_count": len(cells),
                "area_km2": round(len(cells) * pixel_area_km2, 2),
                "centroid_lat": round(centroid_lat, 5),
                "centroid_lon": round(centroid_lon, 5),
                "bbox": {
                    "north": round(max(bbox_nw[0], bbox_se[0]), 5),
                    "south": round(min(bbox_nw[0], bbox_se[0]), 5),
                    "west": round(min(bbox_nw[1], bbox_se[1]), 5),
                    "east": round(max(bbox_nw[1], bbox_se[1]), 5),
                },
                "max_dbz": round(max(values), 1),
                "p90_dbz": round(_percentile(values, 0.90), 1),
                "mean_dbz": round(sum(values) / len(values), 1),
                "touches_invalid_pixels": touches_invalid,
            })

        components.sort(key=lambda row: (row["max_dbz"], row["area_km2"]), reverse=True)
        for idx, component in enumerate(components, start=1):
            component["component_id"] = f"{int(threshold)}dbz-{idx:03d}"
        components_by_threshold[f"{int(threshold)}dbz"] = components[:100]

    total = valid + invalid
    return {
        "domain": {
            "lon_min": domain.lon_min,
            "lon_max": domain.lon_max,
            "lat_min": domain.lat_min,
            "lat_max": domain.lat_max,
        },
        "pixel_window": {"x0": x0, "x1": x1, "y0": y0, "y1": y1},
        "valid_pixel_count": valid,
        "invalid_pixel_count": invalid,
        "valid_fraction": round(valid / total, 6) if total else None,
        "pixel_area_km2_approx": round(pixel_area_km2, 4),
        "echo_pixel_fraction_by_threshold": echo_fraction_by_threshold,
        "components_by_threshold": components_by_threshold,
        "tracking_policy": "SHADOW_COMPONENTS_ONLY_NOT_SURFACE_RAIN",
    }


def _decode_rgb(pixel: tuple[int, ...]) -> float | None:
    r = int(pixel[0])
    # The normal public CMAX renderer uses R as the scalar value. Values in the
    # 200s are source sentinel/background pixels, not plausible dBZ.
    if 0 <= r <= MAX_PLAUSIBLE_DBZ:
        return float(r)
    return None


def _pixel_xy(lat: float, lon: float, bounds: GeoBounds, width: int, height: int) -> tuple[float, float]:
    if not (bounds.lon_min <= lon <= bounds.lon_max and bounds.lat_min <= lat <= bounds.lat_max):
        raise ValueError("point is outside radar bounds")
    x = (lon - bounds.lon_min) / (bounds.lon_max - bounds.lon_min) * width
    y = (bounds.lat_max - lat) / (bounds.lat_max - bounds.lat_min) * height
    # Coordinates land on cell edges at extrema; clamp into valid pixels.
    return min(width - 1, max(0.0, x)), min(height - 1, max(0.0, y))


def _km_per_pixel(lat: float, bounds: GeoBounds, width: int, height: int) -> tuple[float, float]:
    # Sufficient for local sampling radii around Phu Quoc. We are not using
    # these values as navigation coordinates.
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(lat))
    return (
        abs(bounds.lon_max - bounds.lon_min) / width * km_per_deg_lon,
        abs(bounds.lat_max - bounds.lat_min) / height * km_per_deg_lat,
    )


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return data[lo]
    frac = pos - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def _circle_values(
    img: Image.Image,
    *,
    lat: float,
    lon: float,
    bounds: GeoBounds,
    radius_km: float,
) -> tuple[list[float], int, int]:
    width, height = img.size
    cx, cy = _pixel_xy(lat, lon, bounds, width, height)
    km_x, km_y = _km_per_pixel(lat, bounds, width, height)
    rx = max(1, int(math.ceil(radius_km / max(km_x, 1e-6))))
    ry = max(1, int(math.ceil(radius_km / max(km_y, 1e-6))))

    x0 = max(0, int(math.floor(cx)) - rx)
    x1 = min(width - 1, int(math.floor(cx)) + rx)
    y0 = max(0, int(math.floor(cy)) - ry)
    y1 = min(height - 1, int(math.floor(cy)) + ry)

    px = img.load()
    values: list[float] = []
    sampled = 0
    rejected = 0
    for y in range(y0, y1 + 1):
        dy_km = (y - cy) * km_y
        for x in range(x0, x1 + 1):
            dx_km = (x - cx) * km_x
            if dx_km * dx_km + dy_km * dy_km > radius_km * radius_km:
                continue
            sampled += 1
            value = _decode_rgb(px[x, y])
            if value is None:
                rejected += 1
                continue
            values.append(value)
    return values, sampled, rejected


def decode_point(
    img: Image.Image,
    *,
    point_id: str,
    name: str,
    lat: float,
    lon: float,
    bounds: GeoBounds,
) -> dict[str, Any]:
    width, height = img.size
    x, y = _pixel_xy(lat, lon, bounds, width, height)
    center = _decode_rgb(img.getpixel((int(round(x)), int(round(y)))))

    rings: dict[str, Any] = {}
    for radius in (5.0, 15.0, 30.0):
        values, sampled, rejected = _circle_values(
            img,
            lat=lat,
            lon=lon,
            bounds=bounds,
            radius_km=radius,
        )
        rings[f"{int(radius)}km"] = {
            "valid_pixel_count": len(values),
            "sampled_pixel_count": sampled,
            "rejected_sentinel_count": rejected,
            "valid_fraction": round(len(values) / sampled, 4) if sampled else None,
            "max_dbz": round(max(values), 1) if values else None,
            "p90_dbz": round(_percentile(values, 0.90), 1) if values else None,
            "median_dbz": round(_percentile(values, 0.50), 1) if values else None,
        }

    return {
        "point_id": point_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "pixel_x": round(x, 2),
        "pixel_y": round(y, 2),
        "center_dbz": center,
        "rings": rings,
    }


def decode_cmax_png(
    raw_png: bytes,
    *,
    bounds: GeoBounds,
    points: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Decode selected Phu Quoc point neighborhoods from an in-memory PNG."""
    with Image.open(BytesIO(raw_png)) as source:
        img = source.convert("RGB")
        width, height = img.size
        decoded_points = {}
        local_features = _extract_local_components(img, bounds=bounds)
        for point_id, point in points.items():
            lat = float(point["lat"])
            lon = float(point["lon"])
            if not (bounds.lon_min <= lon <= bounds.lon_max and bounds.lat_min <= lat <= bounds.lat_max):
                continue
            decoded_points[point_id] = decode_point(
                img,
                point_id=point_id,
                name=str(point.get("name") or point_id),
                lat=lat,
                lon=lon,
                bounds=bounds,
            )

    return {
        "decoder": "IWEATHER_CMAX_RED_CHANNEL_V1",
        "source_product": "COM_CMAX_RENDERED_PNG",
        "unit": "dBZ",
        "image_width": width,
        "image_height": height,
        "bounds": {
            "lon_min": bounds.lon_min,
            "lon_max": bounds.lon_max,
            "lat_min": bounds.lat_min,
            "lat_max": bounds.lat_max,
        },
        "sentinel_policy": "R>100_IS_NOT_METEOROLOGICAL_DBZ",
        "negative_evidence_policy": "NO_ECHO_OR_ZERO_DBZ_MUST_NOT_BE_TREATED_AS_PROOF_OF_NO_RAIN_AT_PHU_QUOC",
        "points": decoded_points,
        "local_features": local_features,
    }
