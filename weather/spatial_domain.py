"""Shared spatial display domain for JoTrip Weather.

This is a processing/render coverage envelope, not a claim about native source
resolution. The public map stays Phu Quoc-first while source grids extend well
past the visible viewport so users never see an artificial rectangular edge.
"""
from __future__ import annotations

DISPLAY_BOUNDS = {
    "south": 9.00,
    "north": 11.00,
    "west": 102.75,
    "east": 105.50,
}

# Himawari is sampled more densely than deterministic model fields, but the
# wider envelope uses 0.075 degrees to keep the rolling archive/browser payload
# compact enough for mobile.
HIMAWARI_RENDER_STEP_DEG = 0.075

# D0-D3 is the interactive map horizon and gets the full Gulf envelope.
# Use a coarser display-sampling lattice over the wide envelope. The field is
# still direct ECMWF data and interpolation remains render-only. This keeps the
# wide D0-D3 ingest close to the previous 30-cell cost instead of multiplying
# nearest-neighbour extraction by ~4x.
ECMWF_RENDER_STEP_DEG = 0.50
ECMWF_SHORT_BOUNDS = dict(DISPLAY_BOUNDS)

# D4-D10 remains a trend product. Keep a compact core grid to avoid multiplying
# heavy ingest and published file size where the public map does not need it.
ECMWF_MEDIUM_BOUNDS = {
    "south": 9.50,
    "north": 10.75,
    "west": 103.50,
    "east": 104.50,
}

# Copernicus near-now wave/current uses the same wide envelope as the visible
# weather context so the marine field has buffer on every edge of the map.
COPERNICUS_BBOX = (
    DISPLAY_BOUNDS["south"],
    DISPLAY_BOUNDS["west"],
    DISPLAY_BOUNDS["north"],
    DISPLAY_BOUNDS["east"],
)


def axis(start: float, end: float, step: float) -> tuple[float, ...]:
    values = []
    value = float(start)
    while value <= float(end) + 1e-9:
        values.append(round(value, 4))
        value += float(step)
    return tuple(values)


def grid_requests(bounds: dict, step: float) -> tuple[tuple[float, float], ...]:
    return tuple(
        (lat, lon)
        for lat in axis(bounds["south"], bounds["north"], step)
        for lon in axis(bounds["west"], bounds["east"], step)
    )
