"""Coherent-member operational-window probability."""
from __future__ import annotations

from collections import defaultdict


def operational_window_probability(records: list[dict], envelope: dict, *, expected_members: int,
                                   minimum_ratio: float = 0.75) -> dict:
    """A member passes only when every required value at every route/time stays inside its envelope."""
    by_member: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_member[str(record["member"])].append(record)
    ratio = len(by_member) / expected_members
    required = set(envelope)
    if ratio < minimum_ratio:
        return {"status": "NOT_COMPUTABLE", "reason": "MEMBER_COMPLETION_GATE",
                "member_count": len(by_member), "expected_members": expected_members}
    pass_count, incomplete = 0, 0
    for rows in by_member.values():
        variables = {r["variable"] for r in rows}
        if not required.issubset(variables):
            incomplete += 1
            continue
        failed = any(float(r["value"]) > float(envelope[r["variable"]]) for r in rows
                     if r["variable"] in required)
        pass_count += int(not failed)
    usable = len(by_member) - incomplete
    if usable / expected_members < minimum_ratio:
        return {"status": "NOT_COMPUTABLE", "reason": "COHERENT_VARIABLE_GATE",
                "usable_members": usable, "expected_members": expected_members}
    return {"status": "ELIGIBLE" if ratio >= .9 else "PARTIAL_ENSEMBLE",
            "member_count": len(by_member), "usable_members": usable,
            "expected_members": expected_members,
            "p_operational_window": round(pass_count / usable, 4)}
