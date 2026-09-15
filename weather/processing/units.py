"""Unit policy for operational weather output.

Raw source values and units remain unchanged for audit. Display fields are
added separately so every human-facing speed uses km/h.
"""
from __future__ import annotations


_MPS_UNITS = {"m/s", "m s**-1", "m s-1", "m s^-1", "ms-1"}
_KNOT_UNITS = {"kt", "kts", "knot", "knots"}


def speed_to_kmh(value: float, unit: str) -> float:
    normalized = unit.strip().lower()
    if normalized in _MPS_UNITS:
        return round(float(value) * 3.6, 2)
    if normalized in _KNOT_UNITS:
        return round(float(value) * 1.852, 2)
    if normalized in {"km/h", "km h-1", "km h**-1"}:
        return round(float(value), 2)
    raise ValueError(f"Unsupported speed unit: {unit}")


def add_speed_display(record: dict) -> dict:
    """Add audit-safe km/h display fields without rewriting raw evidence."""
    unit = str(record.get("unit", ""))
    try:
        display_value = speed_to_kmh(record["value"], unit)
    except (KeyError, TypeError, ValueError):
        return record
    return {**record, "display_value": display_value, "display_unit": "km/h"}
