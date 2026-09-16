from __future__ import annotations

import statistics
from typing import Any

from tourism_intelligence_v2.qa import coverage, gate


def comparable_key(row: dict[str, Any]) -> tuple:
    return (
        row.get("route"), row.get("weekday"), row.get("lead_time_bucket"), row.get("fare_class"),
        row.get("bag_included"), row.get("tax_included"), row.get("refundable"), row.get("changeable"),
        row.get("currency", "VND"), row.get("member_state"),
    )


def summarize(observations: list[dict[str, Any]], eligible_routes: set[str], threshold: float = 0.65) -> dict[str, Any]:
    by_route: dict[str, list[dict[str, Any]]] = {route: [] for route in eligible_routes}
    for row in observations:
        route = row.get("route")
        if route in by_route and row.get("total_vnd") is not None:
            by_route[route].append(row)
    successful_routes = [route for route, rows in by_route.items() if rows]
    cov = coverage(len(successful_routes), len(eligible_routes))
    if not gate(cov, threshold):
        return {"state": "INSUFFICIENT_COVERAGE", "coverage": cov, "airfare_pressure": None}
    medians = {route: statistics.median(float(r["total_vnd"]) for r in rows) for route, rows in by_route.items() if rows}
    return {
        "state": "REPORT_READY",
        "coverage": cov,
        "median_by_route_vnd": medians,
        "airfare_pressure": None,
        "note": "Pressure score is withheld until comparable historical baselines exist for the same fare conditions.",
    }
