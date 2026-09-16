"""Canonical Weather Lab WGS84 reference points.

These are area reference coordinates for atmospheric, AQI and convective layers.
Marine/tide collectors must still select and report the nearest valid sea grid.
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent / "config" / "points.json"
_RAW = json.loads(_CONFIG.read_text(encoding="utf-8"))["points"]

POINTS: dict[str, tuple[float, float]] = {
    key: (float(value["lat"]), float(value["lon"]))
    for key, value in _RAW.items()
}

POINT_NAMES: dict[str, str] = {
    key: str(value["name"])
    for key, value in _RAW.items()
}

POINT_METADATA: dict[str, dict] = {
    key: dict(value)
    for key, value in _RAW.items()
}
