"""Build the public Weather Lab dashboard snapshot from verified CI artifacts.

D0-D3 uses the freshest ECMWF operational cycle. D4-D10 is appended from the
latest 00/12 medium-range cycle. Long-range values remain trend guidance until
ensemble/model-consensus layers are complete; this module never issues GO/HOLD.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from weather.processing.units import speed_to_kmh

POINT_NAMES = {
    "an_thoi": "An Thới",
    "duong_dong": "Dương Đông",
    "ganh_dau": "Gành Dầu",
    "rach_gia": "Rạch Giá",
}
VN = ZoneInfo("Asia/Ho_Chi_Minh")
GUST_KEYS = ("10fg", "10fg3", "i10fg", "max_i10fg")
HMAX_KEYS = ("hmax", "max_wave_height")
HMAX_WINDOW_SECONDS = 20 * 60


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _tp_mm(value: float, unit: str) -> float:
    normalized = (unit or "").strip().lower()
    if normalized in {"m", "metre", "meter", "metres", "meters"}:
        return float(value) * 1000.0
    if "kg" in normalized and "m" in normalized:
        return float(value)
    if "mm" in normalized:
        return float(value)
    return float(value)


def _wind_kmh(bucket: dict) -> float | None:
    u = bucket.get("10u") or bucket.get("u10")
    v = bucket.get("10v") or bucket.get("v10")
    if not u or not v:
        return None
    speed = math.hypot(float(u["value"]), float(v["value"])) * 3.6
    return round(speed, 1) if 0 <= speed <= 200 else None


def _gust_kmh(bucket: dict) -> float | None:
    record = next((bucket.get(key) for key in GUST_KEYS if bucket.get(key)), None)
    if not record:
        return None
    try:
        if record.get("display_unit") == "km/h" and record.get("display_value") is not None:
            value = float(record["display_value"])
        else:
            value = speed_to_kmh(float(record["value"]), str(record.get("unit", "")))
    except (KeyError, TypeError, ValueError):
        return None
    return round(value, 1) if 0 <= value <= 250 else None


def _temperature_c(bucket: dict) -> float | None:
    record = bucket.get("2t") or bucket.get("t2m")
    if not record:
        return None
    try:
        value = float(record["value"])
        unit = str(record.get("unit", "")).strip().lower()
    except (KeyError, TypeError, ValueError):
        return None
    if unit in {"k", "kelvin"} or value > 150:
        value -= 273.15
    return round(value, 1) if -90 <= value <= 65 else None


def _wave_value(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        value = float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None
    return round(value, 2) if 0 <= value <= 30 else None


def _period_value(record: dict | None) -> float | None:
    if not record:
        return None
    try:
        value = float(record["value"])
    except (KeyError, TypeError, ValueError):
        return None
    return round(value, 1) if 0 < value <= 40 else None


def _hmax_proxy(hs: float | None, period: float | None) -> float | None:
    if hs is None or hs < 0:
        return None
    if period is not None and 0 < period <= 40:
        wave_count = max(3.0, HMAX_WINDOW_SECONDS / period)
        factor = math.sqrt(max(1.0, 0.5 * math.log(wave_count)))
    else:
        factor = 1.8
    value = max(hs, hs * factor)
    return round(value, 2) if value <= 40 else None


def _direct_hmax(bucket: dict) -> float | None:
    record = next((bucket.get(key) for key in HMAX_KEYS if bucket.get(key)), None)
    return _wave_value(record)


def _build_rows(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, dict[str, dict]] = {point: {} for point in POINT_NAMES}
    for record in records:
        point = record.get("point_id")
        if point not in grouped or record.get("qc") != "PASS":
            continue
        valid = record.get("valid_time")
        if not valid:
            continue
        grouped[point].setdefault(valid, {})[str(record.get("variable"))] = record

    rows_by_point: dict[str, list[dict]] = {}
    for point, time_map in grouped.items():
        ordered = sorted(time_map.items(), key=lambda item: _iso(item[0]))
        previous_tp_mm: float | None = None
        rows = []
        for valid, bucket in ordered:
            rain = None
            tp = bucket.get("tp")
            if tp is not None:
                current_tp_mm = _tp_mm(tp["value"], str(tp.get("unit", "")))
                rain = max(0.0, current_tp_mm if previous_tp_mm is None else current_tp_mm - previous_tp_mm)
                previous_tp_mm = current_tp_mm
                rain = round(rain, 2) if rain <= 500 else None

            wave = _wave_value(bucket.get("swh"))
            period = _period_value(bucket.get("pp1d") or bucket.get("mwp"))
            direct_hmax = _direct_hmax(bucket)
            wave_max = direct_hmax if direct_hmax is not None else _hmax_proxy(wave, period)
            if wave_max is not None and wave is not None:
                wave_max = max(wave_max, wave)

            valid_dt = _iso(valid).astimezone(VN)
            rows.append({
                "time": valid_dt.strftime("%d/%m %H:%M"),
                "time_iso": valid_dt.isoformat(),
                "temperature": _temperature_c(bucket),
                "wind": _wind_kmh(bucket),
                "gust": _gust_kmh(bucket),
                "rain": rain,
                "wave": wave,
                "wave_max": wave_max,
                "wave_max_method": "ECMWF_HMAX_20MIN" if direct_hmax is not None else ("RAYLEIGH_20MIN_PROXY" if wave_max is not None else None),
                "period": period,
            })
        rows_by_point[point] = rows
    return rows_by_point


def _merge_short_medium(short_rows: list[dict], medium_rows: list[dict]) -> list[dict]:
    if not short_rows:
        return medium_rows
    if not medium_rows:
        return short_rows
    short_end = max(_iso(row["time_iso"]) for row in short_rows)
    tail = [row for row in medium_rows if _iso(row["time_iso"]) > short_end]
    return sorted(short_rows + tail, key=lambda row: _iso(row["time_iso"]))


def _nearest_row(rows: list[dict], now: datetime) -> dict:
    if not rows:
        return {}
    return min(rows, key=lambda row: abs((_iso(row["time_iso"]) - now).total_seconds()))


def _safe_max(values: list[float | None]) -> float | None:
    valid = [float(v) for v in values if v is not None]
    return round(max(valid), 2) if valid else None


def _daily_outlook(rows: list[dict], now: datetime) -> list[dict]:
    start = now.timestamp() + 168 * 3600
    end = now.timestamp() + 240 * 3600
    groups: dict[str, list[dict]] = {}
    for row in rows:
        ts = _iso(row["time_iso"]).timestamp()
        if not (start < ts <= end):
            continue
        local = _iso(row["time_iso"]).astimezone(VN)
        groups.setdefault(local.strftime("%Y-%m-%d"), []).append(row)

    today = now.astimezone(VN).date()
    outlook = []
    for key in sorted(groups):
        bucket = groups[key]
        day = datetime.strptime(key, "%Y-%m-%d").date()
        rain_values = [float(r["rain"]) for r in bucket if r.get("rain") is not None]
        outlook.append({
            "date": day.strftime("%d/%m"),
            "day_offset": (day - today).days,
            "wind_max": _safe_max([r.get("wind") for r in bucket]),
            "gust_max": _safe_max([r.get("gust") for r in bucket]),
            "rain_total": round(sum(rain_values), 2) if rain_values else None,
            "hs_max": _safe_max([r.get("wave") for r in bucket]),
            "hmax_max": _safe_max([r.get("wave_max") for r in bucket]),
            "status": "TREND_ONLY",
            "confidence": "UNSCORED",
        })
    return outlook


def _current_speed(copernicus: dict, point: str) -> float | None:
    try:
        value = float(copernicus["current"]["derived_vectors"][point]["speed_kmh"])
        return round(value, 2) if 0 <= value <= 20 else None
    except (KeyError, TypeError, ValueError):
        return None


def _copernicus_wave(copernicus: dict, point: str) -> tuple[float | None, float | None, float | None, str | None]:
    try:
        point_record = copernicus["wave"]["variables"]["VHM0"]["points"][point]
        wave = float(point_record["value"])
        period = float(copernicus["wave"]["variables"]["VTPK"]["points"][point]["value"])
        regional_record = copernicus["wave"]["variables"]["VHM0"].get("regional_max_15km", {}).get(point, {})
        regional = float(regional_record["value"]) if regional_record.get("status") == "PASS" else None
        sampled_time = point_record.get("sampled_time")
    except (KeyError, TypeError, ValueError):
        return None, None, None, None
    wave_out = round(wave, 2) if 0 <= wave <= 20 else None
    period_out = round(period, 2) if 0 < period <= 40 else None
    regional_out = round(regional, 2) if regional is not None and 0 <= regional <= 20 else None
    return wave_out, period_out, regional_out, sampled_time


def _icon_cycle(field_url: str | None) -> str | None:
    if not field_url:
        return None
    match = re.search(r"_(\d{10})_000_U_10M\.grib2\.bz2", field_url, flags=re.I)
    if not match:
        return None
    parsed = datetime.strptime(match.group(1), "%Y%m%d%H").replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _source_cycles(ecmwf: dict, gefs: dict, icon: dict) -> dict[str, str | None]:
    return {
        "ECMWF": ecmwf.get("run_time"),
        "ECMWF_MEDIUM": ecmwf.get("medium_run_time"),
        "GEFS": gefs.get("atmosphere", {}).get("run_time"),
        "ICON": _icon_cycle(icon.get("field_url")),
    }


def build(ecmwf: dict, gefs: dict, icon: dict, copernicus: dict) -> dict:
    now = datetime.now(timezone.utc)
    short_by_point = _build_rows(ecmwf.get("records", []))
    medium_by_point = _build_rows(ecmwf.get("medium_records", []))
    rows_by_point = {
        point: _merge_short_medium(short_by_point.get(point, []), medium_by_point.get(point, []))
        for point in POINT_NAMES
    }

    points = {}
    present, expected = 0, len(POINT_NAMES) * 7
    for point, name in POINT_NAMES.items():
        rows = rows_by_point.get(point, [])
        nearest = _nearest_row(rows, now)
        current = _current_speed(copernicus, point)
        marine_wave, marine_period, regional_hs, marine_sampled_time = _copernicus_wave(copernicus, point)
        risk_hs_candidates = [value for value in (marine_wave, regional_hs) if value is not None]
        risk_hs = max(risk_hs_candidates) if risk_hs_candidates else nearest.get("wave")
        regional_proxy = _hmax_proxy(risk_hs, marine_period or nearest.get("period"))
        direct_current_hmax = nearest.get("wave_max") if nearest.get("wave_max_method") == "ECMWF_HMAX_20MIN" else None
        max_candidates = [value for value in (direct_current_hmax, regional_proxy) if value is not None]
        current_hmax = max(max_candidates) if max_candidates else nearest.get("wave_max")
        hmax_method = "ECMWF_HMAX_PLUS_REGIONAL_HS_ENVELOPE" if direct_current_hmax is not None and regional_proxy is not None else (
            "ECMWF_HMAX_20MIN" if direct_current_hmax is not None else (
                "RAYLEIGH_20MIN_PROXY_FROM_REGIONAL_HS" if regional_proxy is not None else nearest.get("wave_max_method")
            )
        )
        temperature = nearest.get("temperature")
        values = {
            "wind": nearest.get("wind"),
            "gust": nearest.get("gust"),
            "wave_max": current_hmax,
            "wave": marine_wave if marine_wave is not None else nearest.get("wave"),
            "period": marine_period if marine_period is not None else nearest.get("period"),
            "rain": nearest.get("rain"),
            "current": current,
        }
        present += sum(value is not None for value in values.values())
        points[point] = {
            "name": name,
            "status": "LIVE DIRECT MODEL",
            "temperature": temperature,
            **values,
            "wave_regional_hs": regional_hs,
            "wave_max_method": hmax_method,
            "marine_sampled_time": marine_sampled_time,
            "forecast_end": rows[-1]["time_iso"] if rows else None,
            "long_range_status": "CONTROL_TREND_ONLY",
            "caveat": "D0-D3 dùng cycle ECMWF mới nhất. D4-D10 nối từ cycle 00/12 có horizon 240 giờ. Hs và Hmax dùng để nhìn biển nền và biên rủi ro; D4-D10 hiện là xu hướng control forecast, chưa phải quyết định vận hành vì lớp ensemble consensus còn đang bổ sung.",
            "hours": rows,
            "daily_outlook": _daily_outlook(rows, now),
        }

    atmosphere_ready = ecmwf.get("readiness") == "POINT_ROUTE_EXTRACTED"
    medium_ready = bool(ecmwf.get("medium_records")) and ecmwf.get("horizon_hours") == 240
    gefs_ready = (
        gefs.get("atmosphere", {}).get("readiness") == "MEMBER_COMPLETE"
        and gefs.get("wave", {}).get("readiness") == "MEMBER_COMPLETE"
    )
    icon_ready = icon.get("status") == "POINT_NUMERIC_READY"
    copernicus_ready = copernicus.get("status") == "POINT_NUMERIC_READY"
    gust_available = any(row.get("gust") is not None for rows in rows_by_point.values() for row in rows)
    direct_hmax_available = any(row.get("wave_max_method") == "ECMWF_HMAX_20MIN" for rows in rows_by_point.values() for row in rows)

    gust_detail = ecmwf.get("gust_parameter") or "unavailable"
    medium_gust_detail = ecmwf.get("medium_gust_parameter") or "unavailable"
    hmax_detail = ecmwf.get("wave_max_parameter") or "proxy-only"
    sources = {
        "ECMWF": {
            "status": "PASS" if atmosphere_ready and medium_ready else "FAIL",
            "detail": f"IFS/Wave D0-D10 · short={len(ecmwf.get('steps', []))} bước · medium={len(ecmwf.get('medium_steps', []))} bước · {ecmwf.get('record_count', 0)} records · temp=2t · gust={gust_detail}/{medium_gust_detail} · hmax={hmax_detail}",
        },
        "GEFS": {
            "status": "PARTIAL" if gefs_ready else "FAIL",
            "detail": "Ensemble member gate hiện mới ở lead +3h; D4-D10 chưa có full consensus matrix",
        },
        "ICON": {
            "status": "PASS" if icon_ready else "FAIL",
            "detail": "DWD official remap point smoke; chưa dùng làm D4-D10 consensus",
        },
        "COPERNICUS": {
            "status": "PASS" if copernicus_ready else "FAIL",
            "detail": "Wave + current nearest-time; Hs regional max trong bán kính 15 km cho hiện tại",
        },
        "RADAR_LIGHTNING": {
            "status": "UNRESOLVED",
            "detail": "Chưa có coverage offshore ổn định",
        },
    }

    critical_ready = atmosphere_ready and medium_ready and icon_ready and copernicus_ready
    generated = now.astimezone(VN)
    completeness = round(100 * present / expected) if expected else 0
    sha = os.environ.get("GITHUB_SHA", "unknown")[:12]
    gaps = [
        {"name": "D4-D10 ensemble consensus", "detail": "ECMWF control đã có tới 240h; GEFS/ICON long-range consensus chưa hoàn tất nên D4-D10 chỉ được gắn TREND_ONLY"},
        {"name": "Nowcast offshore", "detail": "radar/lightning unresolved"},
    ]
    if not gust_available:
        gaps.insert(1, {"name": "Gió giật", "detail": ecmwf.get("gust_error") or "ECMWF gust chưa có ở cycle này; không nội suy"})
    if not direct_hmax_available:
        gaps.insert(1, {"name": "Hmax trực tiếp", "detail": ecmwf.get("wave_max_error") or "ECMWF hmax chưa có; dashboard đang dùng proxy Rayleigh 20 phút"})

    return {
        "snapshot_id": f"PQWX_LIVE_{generated.strftime('%Y%m%d_%H%M%S')}",
        "generated_at": generated.isoformat(),
        "data_mode": "B",
        "completeness": completeness,
        "confidence": None,
        "report_status": "LIVE" if critical_ready else "DEGRADED",
        "decision": "NOT_ISSUED",
        "headline": "Live D0-D10 snapshot đã được phát; D4-D10 là xu hướng, quyết định vận hành chưa được phát." if critical_ready else "Snapshot live thiếu một hoặc nhiều nguồn bắt buộc.",
        "next_review": "watch cycle mỗi 30 phút; rebuild khi short hoặc medium model cycle đổi",
        "git_commit_sha": sha,
        "forecast_horizon_hours": 240,
        "horizon_policy": {
            "D0_D3": "3-hour operational detail from freshest ECMWF cycle",
            "D4_D7": "6-hour display from ECMWF medium-range control; consensus pending",
            "D8_D10": "daily trend outlook only; ensemble confidence unscored",
        },
        "source_cycles": _source_cycles(ecmwf, gefs, icon),
        "sources": sources,
        "gaps": gaps,
        "points": points,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecmwf", type=Path, required=True)
    parser.add_argument("--gefs", type=Path, required=True)
    parser.add_argument("--icon", type=Path, required=True)
    parser.add_argument("--copernicus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = build(_load(args.ecmwf), _load(args.gefs), _load(args.icon), _load(args.copernicus))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "snapshot_id": result["snapshot_id"],
        "status": result["report_status"],
        "completeness": result["completeness"],
        "forecast_horizon_hours": result["forecast_horizon_hours"],
        "source_cycles": result["source_cycles"],
        "rows": {key: len(value["hours"]) for key, value in result["points"].items()},
        "daily_outlook": {key: len(value["daily_outlook"]) for key, value in result["points"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
