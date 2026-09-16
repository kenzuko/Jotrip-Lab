"""Air-quality helpers for the Weather Lab environmental layer.

The dashboard labels this as a CAMS model estimate, not an observed or regulatory
AQI. EPA 2024 particulate-matter breakpoints are used only to map modelled PM
concentrations onto the familiar US AQI scale.
"""
from __future__ import annotations

import math

PM25_BREAKPOINTS = (
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
)
PM10_BREAKPOINTS = (
    (0.0, 54.0, 0, 50),
    (55.0, 154.0, 51, 100),
    (155.0, 254.0, 101, 150),
    (255.0, 354.0, 151, 200),
    (355.0, 424.0, 201, 300),
    (425.0, 604.0, 301, 500),
)


def _truncate(value: float, places: int) -> float:
    factor = 10**places
    return math.floor(max(0.0, float(value)) * factor) / factor


def _subindex(concentration: float | None, pollutant: str) -> int | None:
    if concentration is None:
        return None
    value = float(concentration)
    if not math.isfinite(value) or value < 0:
        return None
    if pollutant == "PM2.5":
        value = _truncate(value, 1)
        table = PM25_BREAKPOINTS
    elif pollutant == "PM10":
        value = float(math.floor(value))
        table = PM10_BREAKPOINTS
    else:
        raise ValueError(f"Unsupported pollutant: {pollutant}")
    for c_lo, c_hi, i_lo, i_hi in table:
        if c_lo <= value <= c_hi:
            result = (i_hi - i_lo) / (c_hi - c_lo) * (value - c_lo) + i_lo
            return int(round(result))
    return 500


def category(aqi: int | None) -> str | None:
    if aqi is None:
        return None
    if aqi <= 50:
        return "GOOD"
    if aqi <= 100:
        return "MODERATE"
    if aqi <= 150:
        return "UNHEALTHY_FOR_SENSITIVE_GROUPS"
    if aqi <= 200:
        return "UNHEALTHY"
    if aqi <= 300:
        return "VERY_UNHEALTHY"
    return "HAZARDOUS"


def particulate_aqi(pm25_ugm3: float | None, pm10_ugm3: float | None) -> dict:
    """Return the dominant PM sub-index on the US AQI scale.

    This function does not claim an official AQI because CAMS input is modelled
    concentration and the collector uses the latest analysis field rather than a
    regulatory 24-hour monitor average.
    """
    pm25_index = _subindex(pm25_ugm3, "PM2.5")
    pm10_index = _subindex(pm10_ugm3, "PM10")
    pairs = [("PM2.5", pm25_index), ("PM10", pm10_index)]
    valid = [(name, value) for name, value in pairs if value is not None]
    if not valid:
        return {"aqi_us": None, "category": None, "dominant_pollutant": None, "subindices": {"PM2.5": pm25_index, "PM10": pm10_index}}
    dominant, index = max(valid, key=lambda item: item[1])
    return {
        "aqi_us": int(min(500, index)),
        "category": category(index),
        "dominant_pollutant": dominant,
        "subindices": {"PM2.5": pm25_index, "PM10": pm10_index},
    }
