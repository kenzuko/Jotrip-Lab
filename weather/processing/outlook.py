"""D4-D14 planning outlook with ranges, never hard operational decisions."""
from __future__ import annotations

from collections import defaultdict

from weather.processing.ensemble import _quantile


def daily_ensemble_outlook(records: list[dict], *, minimum_members: int = 20) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["date"], record["variable"])].append(float(record["value"]))
    output = []
    for (date, variable), values in sorted(grouped.items()):
        member_count = len(values)
        if member_count < minimum_members:
            output.append({"date": date, "variable": variable, "status": "NOT_COMPUTABLE",
                           "member_count": member_count})
            continue
        output.append({"date": date, "variable": variable, "status": "PLANNING_ONLY",
                       "member_count": member_count, "likely_range": [round(_quantile(values, .25), 2),
                                                                        round(_quantile(values, .75), 2)],
                       "possible_range": [round(_quantile(values, .1), 2),
                                          round(_quantile(values, .9), 2)]})
    return output
