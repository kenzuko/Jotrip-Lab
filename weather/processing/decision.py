"""Evidence-based decision gate. Missing data changes confidence, not weather risk."""
from __future__ import annotations


def decide_product(*, restriction: str, windows: list[dict], critical_missing: list[str],
                   actual_hazard: bool = False) -> dict:
    if restriction in {"CLOSED", "SUSPENDED", "PROHIBITED"}:
        return {"decision": "CANCEL", "reason": "OFFICIAL_RESTRICTION"}
    if actual_hazard:
        return {"decision": "HOLD_WATCH", "reason": "ACTUAL_OR_NOWCAST_HAZARD"}
    best = [w for w in windows if w.get("window_class") == "BEST"]
    marginal = [w for w in windows if w.get("window_class") == "MARGINAL"]
    if critical_missing:
        return {"decision": "HOLD_WATCH", "reason": "CRITICAL_UNCERTAINTY",
                "critical_missing": critical_missing, "best_windows": best}
    if best:
        return {"decision": "GO" if not marginal else "GO_WITH_WATCH",
                "reason": "WINDOW_WITHIN_ENVELOPE", "best_windows": best}
    if marginal:
        return {"decision": "MODIFY", "reason": "MARGINAL_WINDOW_ONLY", "windows": marginal}
    return {"decision": "HOLD_WATCH", "reason": "NO_ACCEPTABLE_WINDOW"}
