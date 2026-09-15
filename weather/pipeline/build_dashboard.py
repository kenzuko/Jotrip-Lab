"""Build the public Weather Lab dashboard snapshot from verified CI artifacts.

This module deliberately does not issue an operational GO/HOLD decision. It
only publishes a live, auditable direct-model snapshot after upstream CI gates
have passed.
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
}
VN = ZoneInfo("Asia/Ho_Chi_Minh")
GUST_KEYS = ("10fg", "10fg3", "i10fg", "max_i10fg")


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


def _wave_value(record: dict | None) -> float | None:
    if not record:
        return None
    value = float(record["value"])
    return round(value, 2) if 0 <= value <= 20 else None


def _period_value(record: dict | None) -> float | None:
    if not record:
        return None
    value = float(record["value"])
    return round(value, 1) if 0 < value <= 40 else None


def _build_ecmwf_rows(payload: dict) -> dict[str, list[dict]]:
    grouped: dict[str, dict[str, dict]] = {point: {} for point in POINT_NAMES}
    for record in payload.get("records", []):
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
                if previous_tp_mm is None:
                    rain = max(0.0, current_tp_mm)
                else:
                    rain = max(0.0, current_tp_mm - previous_tp_mm)
                previous_tp_mm = current_tp_mm
                rain = round(rain, 2) if rain <= 500 else None

            valid_dt = _iso(valid).astimezone(VN)
            rows.append({
                "time": valid_dt.strftime("%d/%m %H:%M"),
                "time_iso": valid_dt.isoformat(),
                "wind": _wind_kmh(bucket),
                "gust": _gust_kmh(bucket),
                "rain": rain,
                "wave": _wave_value(bucket.get("swh")),
                "period": _period_value(bucket.get("pp1d") or bucket.get("mwp")),
            })
        rows_by_point[point] = rows
    return rows_by_point


def _nearest_row(rows: list[dict], now: datetime) -> dict:
    if not rows:
        return {}
    return min(rows, key=lambda row: abs((_iso(row["time_iso"]) - now).total_seconds()))


def _current_speed(copernicus: dict, point: str) -> float | None:
    try:
        value = float(copernicus["current"]["derived_vectors"][point]["speed_kmh"])
        return round(value, 2) if 0 <= value <= 20 else None
    except (KeyError, TypeError, ValueError):
        return None


def _copernicus_wave(copernicus: dict, point: str) -> tuple[float | None, float | None]:
    try:
        wave = float(copernicus["wave"]["variables"]["VHM0"]["points"][point]["value"])
        period = float(copernicus["wave"]["variables"]["VTPK"]["points"][point]["value"])
    except (KeyError, TypeError, ValueError):
        return None, None
    wave_out = round(wave, 2) if 0 <= wave <= 20 else None
    period_out = round(period, 2) if 0 < period <= 40 else None
    return wave_out, period_out


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
        "GEFS": gefs.get("atmosphere", {}).get("run_time"),
        "ICON": _icon_cycle(icon.get("field_url")),
    }


def build(ecmwf: dict, gefs: dict, icon: dict, copernicus: dict) -> dict:
    now = datetime.now(timezone.utc)
    rows_by_point = _build_ecmwf_rows(ecmwf)
    points = {}
    present, expected = 0, len(POINT_NAMES) * 6

    for point, name in POINT_NAMES.items():
        rows = rows_by_point.get(point, [])
        nearest = _nearest_row(rows, now)
        current = _current_speed(copernicus, point)
        marine_wave, marine_period = _copernicus_wave(copernicus, point)
        values = {
            "wind": nearest.get("wind"),
            "gust": nearest.get("gust"),
            "wave": marine_wave if marine_wave is not None else nearest.get("wave"),
            "period": marine_period if marine_period is not None else nearest.get("period"),
            "rain": nearest.get("rain"),
            "current": current,
        }
        present += sum(value is not None for value in values.values())
        points[point] = {
            "name": name,
            "status": "LIVE DIRECT MODEL",
            **values,
            "caveat": "Gió nền và mưa lấy từ ECMWF gần valid time của snapshot. Gió giật là trường ECMWF trực tiếp - cực đại 10 m kể từ lần hậu xử lý trước, không suy từ gió nền. Sóng và dòng chảy ở thẻ hiện tại lấy từ Copernicus Marine; chuỗi 72 giờ lấy từ ECMWF khi grid biển hợp lệ. Đây là dữ liệu mô hình, không phải quan trắc tại chỗ.",
            "hours": rows,
        }

    atmosphere_ready = ecmwf.get("readiness") == "POINT_ROUTE_EXTRACTED"
    gefs_ready = (
        gefs.get("atmosphere", {}).get("readiness") == "MEMBER_COMPLETE"
        and gefs.get("wave", {}).get("readiness") == "MEMBER_COMPLETE"
    )
    icon_ready = icon.get("status") == "POINT_NUMERIC_READY"
    copernicus_ready = copernicus.get("status") == "POINT_NUMERIC_READY"
    gust_available = any(row.get("gust") is not None for rows in rows_by_point.values() for row in rows)

    gust_detail = ecmwf.get("gust_parameter") or "unavailable"
    sources = {
        "ECMWF": {
            "status": "PASS" if atmosphere_ready else "FAIL",
            "detail": f"IFS/Wave 0-72h · {len(ecmwf.get('steps', []))} bước · {ecmwf.get('record_count', 0)} point-records · gust={gust_detail}",
        },
        "GEFS": {
            "status": "PARTIAL" if gefs_ready else "FAIL",
            "detail": "Ensemble member gate đạt tại lead +3h; full matrix 0-72h chưa publish vào dashboard",
        },
        "ICON": {
            "status": "PASS" if icon_ready else "FAIL",
            "detail": "DWD official remap point smoke",
        },
        "COPERNICUS": {
            "status": "PASS" if copernicus_ready else "FAIL",
            "detail": "Wave + current subset cho 3 điểm",
        },
        "RADAR_LIGHTNING": {
            "status": "UNRESOLVED",
            "detail": "Chưa có coverage offshore ổn định",
        },
    }

    critical_ready = atmosphere_ready and icon_ready and copernicus_ready
    generated = now.astimezone(VN)
    completeness = round(100 * present / expected) if expected else 0
    sha = os.environ.get("GITHUB_SHA", "unknown")[:12]
    gaps = [
        {"name": "GEFS full matrix", "detail": "member x biến x 0-72h chưa được ghép vào dashboard production"},
        {"name": "Nowcast offshore", "detail": "radar/lightning unresolved"},
    ]
    if not gust_available:
        gaps.insert(1, {"name": "Gió giật", "detail": ecmwf.get("gust_error") or "ECMWF gust chưa có ở cycle này; không nội suy"})

    return {
        "snapshot_id": f"PQWX_LIVE_{generated.strftime('%Y%m%d_%H%M%S')}",
        "generated_at": generated.isoformat(),
        "data_mode": "B",
        "completeness": completeness,
        "confidence": None,
        "report_status": "LIVE" if critical_ready else "DEGRADED",
        "decision": "NOT_ISSUED",
        "headline": "Live direct-model snapshot đã được phát; quyết định vận hành chưa được phát." if critical_ready else "Snapshot live thiếu một hoặc nhiều nguồn bắt buộc.",
        "next_review": "watch cycle mỗi 30 phút; rebuild khi có model cycle mới",
        "git_commit_sha": sha,
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
        "source_cycles": result["source_cycles"],
        "rows": {key: len(value["hours"]) for key, value in result["points"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
