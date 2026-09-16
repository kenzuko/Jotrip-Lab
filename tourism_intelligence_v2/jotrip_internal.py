from __future__ import annotations

from typing import Any

REQUIRED = {"lead_id", "created_at", "travel_date", "market", "language", "product", "party_size", "quoted_value", "booked", "cancelled", "lead_time_days"}


def validate_lead(row: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED - row.keys())
    if missing:
        raise ValueError(f"JoTrip lead missing keys: {', '.join(missing)}")
    if not isinstance(row["booked"], bool) or not isinstance(row["cancelled"], bool):
        raise ValueError("booked and cancelled must be boolean")
    if row.get("gross_margin") is not None and not isinstance(row["gross_margin"], (int, float)):
        raise ValueError("gross_margin must be numeric or null")
    return row
