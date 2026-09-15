"""Build the public Weather Lab dashboard snapshot from verified CI artifacts.

This module deliberately does not issue an operational GO/HOLD decision.  It
only publishes a live, auditable direct-model snapshot after upstream CI gates
have passed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

POINT_NAMES = {
    "an_thoi": "An Thới",
    "duong_dong": "Dương Đông",
    "ganh_dau": "Gành Dầu",
}
VN = ZoneInfo("Asia/Ho_Chi_Minh")


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
    # ECMWF total precipitation is normally metres. Unknown units stay raw
    # rather than being silently re-scaled.
    return float(value)


def _wind_kmh(bucket: dict) -> float | None:
    u = bucket.get("10u") or bucket.get("u10")
    v = bucket.get("10v") or bucket.get("v10")
    if not u or not v:
        return None
    return round(math.hypot(float(u["value"]), float(v["value"])) * 3.6, 1)


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
                rain = round(rain, 2)

            wave = bucket.get("swh")
            period = bucket.get("pp1d") or bucket.get("mwp")
            valid_dt = _iso(valid).astimezone(VN)
            rows.append({
                "time": valid_dt.strftime("%d/%m %H:%M"),
                "time_iso": valid_dt.isoformat(),
                "wind": _wind_kmh(bucket),
                "gust": None,
                "rain": rain,
                "wave": round(float(wave["value"]), 2) if wave else None,
                "period": round(float(period["value"]), 1) if period else None,
            })
        rows_by_point[point] = rows
    return rows_by_point


def _nearest_row(rows: list[dict], now: datetime) -> dict:
    if not rows:
        return {}
    return min(rows, key=lambda row: abs((_iso(row["time_iso"]) - now).total_seconds()))


def _current_speed(copernicus: dict, point: str) -> float | None:
    try:
        return round(float(copernicus["current"]["derived_vectors"][point]["speed_kmh"]), 2)
    except (KeyError, TypeError, ValueError):
        return None


def build(ecmwf: dict, gefs: dict, icon: dict, copernicus: dict) -> dict:
    now = datetime.now(timezone.utc)
    rows_by_point = _build_ecmwf_rows(ecmwf)
    points = {}
    present, expected = 0, len(POINT_NAMES) * 6

    for point, name in POINT_NAMES.items():
        rows = rows_by_point.get(point, [])
        nearest = _nearest_row(rows, now)
        current = _current_speed(copernicus, point)
        values = {
            "wind": nearest.get("wind"),
            "gust": nearest.get("gust"),
            "wave": nearest.get("wave"),
            "period": nearest.get("period"),
            "rain": nearest.get("rain"),
            "current": current,
        }
        present += sum(value is not None for value in values.values())
        points[point] = {
            "name": name,
            "status": "LIVE DIRECT MODEL",
            **values,
            "caveat": "Gió, mưa và sóng lấy từ valid time ECMWF gần thời điểm phát snapshot; dòng chảy lấy từ Copernicus Marine. Đây là dữ liệu mô hình trực tiếp, không phải quan trắc tại chỗ.",
            "hours": rows,
        }

    atmosphere_ready = ecmwf.get("readiness") == "POINT_ROUTE_EXTRACTED"
    gefs_ready = (
        gefs.get("atmosphere", {}).get("readiness") == "MEMBER_COMPLETE"
        and gefs.get("wave", {}).get("readiness") == "MEMBER_COMPLETE"
    )
    icon_ready = icon.get("status") == "POINT_NUMERIC_READY"
    copernicus_ready = copernicus.get("status") == "POINT_NUMERIC_READY"

    sources = {
        "ECMWF": {
            "status": "PASS" if atmosphere_ready else "FAIL",
            "detail": f"IFS/Wave 0-72h · {len(ecmwf.get('steps', []))} bước · {ecmwf.get('record_count', 0)} point-records",
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

    return {
        "snapshot_id": f"PQWX_LIVE_{generated.strftime('%Y%m%d_%H%M%S')}",
        "generated_at": generated.isoformat(),
        "data_mode": "B",
        "completeness": completeness,
        "confidence": None,
        "report_status": "LIVE" if critical_ready else "DEGRADED",
        "decision": "NOT_ISSUED",
        "headline": "Live direct-model snapshot đã được phát; quyết định vận hành chưa được phát." if critical_ready else "Snapshot live thiếu một hoặc nhiều nguồn bắt buộc.",
        "next_review": "sau cycle CI kế tiếp",
        "git_commit_sha": sha,
        "sources": sources,
        "gaps": [
            {"name": "GEFS full matrix", "detail": "member x biến x 0-72h chưa được ghép vào dashboard production"},
            {"name": "Gió giật", "detail": "ECMWF collector hiện chưa tải trường gust nên dashboard để trống, không nội suy"},
            {"name": "Nowcast offshore", "detail": "radar/lightning unresolved"},
        ],
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
        "rows": {key: len(value["hours"]) for key, value in result["points"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
