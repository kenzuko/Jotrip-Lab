"""Transparent satellite convective signal for Weather Lab.

This is deliberately NOT a lightning-observation algorithm. It converts
Himawari cloud-top observations into an interpretable convective signal that
can sit beside a future direct lightning feed without pretending to be one.
"""
from __future__ import annotations


def convective_signal(cloud_top_temp_c: float | None, cloud_top_height_m: float | None,
                      cooling_c_per_20m: float | None) -> dict:
    """Return a 0-100 heuristic signal and level from observed cloud-top fields.

    - The -52 C threshold is treated as a deep-convection marker, not proof of
      lightning.
    - Cooling and cloud-top-height increments are intentionally conservative
      heuristic weights and are exposed in the output method string.
    """
    score = 0
    reasons: list[str] = []

    if cloud_top_temp_c is not None:
        if cloud_top_temp_c <= -60:
            score += 60
            reasons.append("cloud_top_very_cold")
        elif cloud_top_temp_c <= -52:
            score += 45
            reasons.append("cloud_top_deep_convection")
        elif cloud_top_temp_c <= -45:
            score += 30
            reasons.append("cloud_top_cold")
        elif cloud_top_temp_c <= -35:
            score += 15
            reasons.append("cloud_top_developing")

    if cooling_c_per_20m is not None:
        if cooling_c_per_20m <= -6:
            score += 25
            reasons.append("rapid_cloud_top_cooling")
        elif cooling_c_per_20m <= -3:
            score += 15
            reasons.append("cloud_top_cooling")
        elif cooling_c_per_20m <= -1:
            score += 5
            reasons.append("weak_cloud_top_cooling")

    if cloud_top_height_m is not None:
        if cloud_top_height_m >= 12000:
            score += 15
            reasons.append("very_high_cloud_top")
        elif cloud_top_height_m >= 10000:
            score += 10
            reasons.append("high_cloud_top")
        elif cloud_top_height_m >= 8000:
            score += 5
            reasons.append("elevated_cloud_top")

    score = max(0, min(100, score))
    if score >= 75:
        level = "HIGH"
    elif score >= 50:
        level = "ELEVATED"
    elif score >= 25:
        level = "WATCH"
    else:
        level = "LOW"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "method": "HIMAWARI_CLOUD_TOP_HEURISTIC_V1_NOT_LIGHTNING_OBSERVATION",
    }
