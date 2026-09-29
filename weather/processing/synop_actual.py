"""Decode only measurement fields needed from raw WMO FM-12 SYNOP.

Scope is intentionally narrow:
- station wind from YYGGiw + Nddff
- precipitation groups 6RRRtR, preserving section and accumulation window

Anything outside this tested subset remains in raw_observation.
"""
from __future__ import annotations

from typing import Any

PRECIP_WINDOW_HOURS = {
    1: 6,
    2: 12,
    3: 18,
    4: 24,
    5: 1,
    6: 2,
    7: 3,
    8: 9,
    9: 15,
}


def _precip_mm(rrr: str) -> float | None:
    if len(rrr) != 3 or not rrr.isdigit():
        return None
    code = int(rrr)
    if 1 <= code <= 989:
        return float(code)
    if code == 990:
        return 0.0  # trace; numeric 0 retained with trace flag separately
    if 991 <= code <= 999:
        return (code - 990) / 10.0
    return None


def decode_synop_actual(report: str) -> dict[str, Any]:
    tokens = report.strip().rstrip("=").split()
    out: dict[str, Any] = {
        "wind": None,
        "precipitation": [],
    }
    if len(tokens) < 5 or tokens[0] != "AAXX":
        return out

    yyggiw = tokens[1]
    nddff = tokens[4]

    if len(yyggiw) == 5 and yyggiw.isdigit() and len(nddff) == 5:
        iw = int(yyggiw[-1])
        dd = nddff[1:3]
        ff = nddff[3:5]
        if dd.isdigit() and ff.isdigit() and iw in {0, 1}:
            dd_code = int(dd)
            speed = int(ff)
            direction = None
            direction_class = "UNKNOWN"
            if dd_code == 0 and speed == 0:
                direction_class = "CALM"
            elif dd_code == 99:
                direction_class = "VARIABLE"
            elif 1 <= dd_code <= 36:
                direction = dd_code * 10
                direction_class = "DIRECTIONAL"

            out["wind"] = {
                "direction_deg": direction,
                "direction_class": direction_class,
                "speed_ms": float(speed),
                "measurement_origin": "ANEMOMETER" if iw == 1 else "ESTIMATED",
                "iw": iw,
                "raw_group": nddff,
            }

    section = 1
    # Section 1 starts after station identification; Section 2/3 markers change
    # the meaning of subsequent groups. Precipitation is decoded only in 1 or 3.
    for token in tokens[5:]:
        if token.startswith("222"):
            section = 2
            continue
        if token == "333":
            section = 3
            continue
        if token == "444":
            section = 4
            continue
        if token == "555":
            section = 5
            continue
        if section not in {1, 3}:
            continue
        if len(token) != 5 or not token.startswith("6"):
            continue
        rrr = token[1:4]
        tr = token[4]
        if not (rrr.isdigit() and tr.isdigit()):
            continue
        tr_code = int(tr)
        mm = _precip_mm(rrr)
        hours = PRECIP_WINDOW_HOURS.get(tr_code)
        if mm is None or hours is None:
            continue
        out["precipitation"].append(
            {
                "section": section,
                "accumulation_mm": mm,
                "window_hours": hours,
                "tR": tr_code,
                "trace": rrr == "990",
                "raw_group": token,
                "statistic": "ACCUMULATION",
                "data_class": "ACTUAL",
            }
        )

    return out
