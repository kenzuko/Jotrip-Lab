from __future__ import annotations

from collections import defaultdict
from typing import Any


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_market: dict[str, dict[str, Any]] = defaultdict(lambda: {"routes": set(), "weekly_frequency": 0.0, "direct_records": 0})
    for row in records:
        market = row.get("market") or "UNKNOWN"
        route = row.get("route")
        if route:
            by_market[market]["routes"].add(route)
        freq = row.get("frequency_weekly")
        if isinstance(freq, (int, float)):
            by_market[market]["weekly_frequency"] += float(freq)
        if row.get("evidence_class") == "DIRECT":
            by_market[market]["direct_records"] += 1
    normalized = {
        market: {
            "route_count": len(values["routes"]),
            "routes": sorted(values["routes"]),
            "weekly_frequency": values["weekly_frequency"],
            "direct_records": values["direct_records"],
        }
        for market, values in by_market.items()
    }
    return {
        "state": "REPORT_READY" if records else "UNKNOWN",
        "markets": normalized,
        "forward_airlift_signal": None,
        "note": "No composite score until coverage >=65% and at least one direct schedule source is present.",
    }
