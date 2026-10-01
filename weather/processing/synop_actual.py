"""Decode a narrow, auditable subset of raw WMO FM-12 SYNOP.

Production rules:
- Preserve the raw report and raw groups.
- Decode only fields whose code semantics are explicitly handled here.
- Never merge WMO 48917 with VVPQ or KTT book/60018 streams by identifier alone.
- Visual SYNOP wave height remains a coded visual observation, never Hm0/Hs.
"""
from __future__ import annotations

from typing import Any

PRECIP_WINDOW_HOURS = {
    1: 6, 2: 12, 3: 18, 4: 24, 5: 1, 6: 2, 7: 3, 8: 9, 9: 15,
}


def _precip_mm(rrr: str) -> float | None:
    if len(rrr) != 3 or not rrr.isdigit():
        return None
    code = int(rrr)
    if 1 <= code <= 989:
        return float(code)
    if code == 990:
        return 0.0
    if 991 <= code <= 999:
        return (code - 990) / 10.0
    return None


def _signed_tenths(token: str) -> float | None:
    if len(token) != 5 or token[1] not in {"0", "1"} or not token[2:].isdigit():
        return None
    value = int(token[2:]) / 10.0
    return -value if token[1] == "1" else value


def _pressure_hpa(token: str) -> float | None:
    if len(token) != 5 or not token[1:].isdigit():
        return None
    p = int(token[1:]) / 10.0
    return p + 1000.0 if p < 500.0 else p


def _sst(token: str) -> dict[str, Any] | None:
    if len(token) != 5 or token[0] != "0" or not token[1].isdigit() or not token[2:].isdigit():
        return None
    ss = int(token[1])
    value = int(token[2:]) / 10.0
    # WMO table 3850 encodes sign/method in ss. Keep ss raw for audit.
    if ss >= 5:
        value = -value
    return {
        "temperature_c": value,
        "ss": ss,
        "raw_group": token,
        "data_class": "ACTUAL",
        "observation_type": "SYNOP_SECTION2_SST",
    }


def _wind_wave(token: str) -> dict[str, Any] | None:
    if len(token) != 5 or token[0] != "2":
        return None
    period_raw = token[1:3]
    height_raw = token[3:5]
    period_s = int(period_raw) if period_raw.isdigit() else None
    if not height_raw.isdigit():
        return None
    code = int(height_raw)
    nominal = code * 0.5
    if code == 0:
        height_bin = [0.0, 0.25]
    else:
        height_bin = [max(0.0, nominal - 0.25), nominal + 0.25]
    return {
        "period_s": period_s,
        "period_code": period_raw,
        "height_code": code,
        "height_nominal_m": nominal,
        "height_bin_m": height_bin,
        "raw_group": token,
        "data_class": "ACTUAL",
        "observation_type": "VISUAL_WIND_WAVE_CODE",
        "instrument_hs": False,
    }


def decode_synop_actual(report: str) -> dict[str, Any]:
    tokens = report.strip().rstrip("=").split()
    out: dict[str, Any] = {
        "wind": None,
        "air_temperature_c": None,
        "dewpoint_c": None,
        "station_pressure_hpa": None,
        "sea_level_pressure_hpa": None,
        "precipitation": [],
        "marine": {"sea_surface_temperature": None, "wind_wave": None},
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
                "speed_kmh": round(float(speed) * 3.6, 2),
                "measurement_origin": "ANEMOMETER" if iw == 1 else "ESTIMATED",
                "iw": iw,
                "raw_group": nddff,
            }

    section = 1
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

        if section == 1:
            if token.startswith("1") and out["air_temperature_c"] is None:
                out["air_temperature_c"] = _signed_tenths(token)
            elif token.startswith("2") and out["dewpoint_c"] is None:
                # 29UUU is RH, not dew point. Only 20/21xxx is decoded here.
                if len(token) == 5 and token[1] in {"0", "1"}:
                    out["dewpoint_c"] = _signed_tenths(token)
            elif token.startswith("3") and out["station_pressure_hpa"] is None:
                out["station_pressure_hpa"] = _pressure_hpa(token)
            elif token.startswith("4") and out["sea_level_pressure_hpa"] is None:
                out["sea_level_pressure_hpa"] = _pressure_hpa(token)

        if section == 2:
            if token.startswith("0") and out["marine"]["sea_surface_temperature"] is None:
                out["marine"]["sea_surface_temperature"] = _sst(token)
            elif token.startswith("2") and out["marine"]["wind_wave"] is None:
                out["marine"]["wind_wave"] = _wind_wave(token)

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
        out["precipitation"].append({
            "section": section,
            "accumulation_mm": mm,
            "window_hours": hours,
            "tR": tr_code,
            "trace": rrr == "990",
            "raw_group": token,
            "statistic": "ACCUMULATION",
            "data_class": "ACTUAL",
        })

    return out
