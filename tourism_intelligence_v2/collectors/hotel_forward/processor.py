from __future__ import annotations

import statistics
from typing import Any

from tourism_intelligence_v2.qa import coverage, gate


def summarize(observations: list[dict[str, Any]], eligible_hotel_ids: set[str], threshold: float = 0.65) -> dict[str, Any]:
    latest_by_hotel: dict[str, dict[str, Any]] = {}
    for row in observations:
        hotel_id = row.get("hotel_id")
        if hotel_id in eligible_hotel_ids:
            latest_by_hotel[hotel_id] = row
    successful = len(latest_by_hotel)
    eligible = len(eligible_hotel_ids)
    cov = coverage(successful, eligible)
    if not gate(cov, threshold):
        return {
            "state": "INSUFFICIENT_COVERAGE",
            "coverage": cov,
            "eligible": eligible,
            "successful": successful,
            "forward_compression": None,
        }
    rows = list(latest_by_hotel.values())
    unavailable = sum(1 for row in rows if row.get("available") is False)
    rates = [float(row["rate_all_in_vnd"]) for row in rows if row.get("available") is True and row.get("rate_all_in_vnd") is not None]
    refundable = [row for row in rows if row.get("available") is True and row.get("refundable") is True]
    breakfast = [row for row in rows if row.get("available") is True and row.get("breakfast") is True]
    restrictions = [row for row in rows if row.get("minimum_stay") not in (None, 0, 1)]
    return {
        "state": "REPORT_READY",
        "coverage": cov,
        "eligible": eligible,
        "successful": successful,
        "observed_unavailable_count": unavailable,
        "observed_unavailable_share": unavailable / successful if successful else None,
        "median_all_in_rate_vnd": statistics.median(rates) if rates else None,
        "rate_floor_vnd": min(rates) if rates else None,
        "refundable_share": len(refundable) / successful if successful else None,
        "breakfast_share": len(breakfast) / successful if successful else None,
        "restriction_share": len(restrictions) / successful if successful else None,
        "forward_compression": None,
        "note": "Observed OTA scarcity is not occupancy. Composite score requires comparable baseline pressure inputs.",
    }
