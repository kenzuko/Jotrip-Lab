"""Attach non-critical CAMS air-quality data to a Weather Lab dashboard snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

POINTS = ("an_thoi", "duong_dong", "ganh_dau", "rach_gia")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _empty(detail: str) -> dict:
    return {
        "status": "UNAVAILABLE",
        "aqi_us": None,
        "category": None,
        "dominant_pollutant": None,
        "pm25_ugm3": None,
        "pm10_ugm3": None,
        "sampled_time": None,
        "source_type": "MODEL",
        "method": "MODEL_ANALYSIS_INSTANT_PM_US_AQI_PROXY",
        "detail": detail,
    }


def attach(dashboard: dict, cams: dict) -> dict:
    ready = cams.get("status") == "POINT_NUMERIC_READY"
    detail = str(cams.get("detail") or cams.get("status") or "CAMS unavailable")
    for point_id in POINTS:
        target = dashboard.setdefault("points", {}).setdefault(point_id, {})
        if ready and point_id in cams.get("points", {}):
            source = cams["points"][point_id]
            target["air_quality"] = {
                "status": "MODEL_ESTIMATE",
                "aqi_us": source.get("aqi_us"),
                "category": source.get("category"),
                "dominant_pollutant": source.get("dominant_pollutant"),
                "pm25_ugm3": source.get("pm25_ugm3"),
                "pm10_ugm3": source.get("pm10_ugm3"),
                "sampled_time": source.get("sampled_time") or cams.get("sampled_time"),
                "source_type": "MODEL",
                "grid_lat": source.get("grid_lat"),
                "grid_lon": source.get("grid_lon"),
                "grid_resolution": cams.get("grid_resolution", "0.4deg"),
                "method": cams.get("method", "MODEL_ANALYSIS_INSTANT_PM_US_AQI_PROXY"),
                "detail": "CAMS global analysis - mô hình, không phải trạm đo",
            }
        else:
            target["air_quality"] = _empty(detail)

    dashboard["air_quality_policy"] = {
        "source": "CAMS global atmospheric composition analysis",
        "display_standard": "US AQI scale",
        "scope": "PM2.5 + PM10",
        "interpretation": "MODEL_ESTIMATE_ONLY",
        "method": "EPA 2024 PM breakpoints applied to instantaneous CAMS model concentrations",
        "warning": "Không phải AQI quan trắc/trạm đo hoặc AQI pháp quy. Không tham gia GO/HOLD biển.",
    }
    dashboard.setdefault("sources", {})["CAMS_AIR_QUALITY"] = {
        "status": "PASS" if ready else "UNRESOLVED",
        "detail": (
            f"PM2.5 + PM10 model analysis, grid {cams.get('grid_resolution', '0.4deg')}; AQI US proxy; sampled={cams.get('sampled_time') or 'n/a'}"
            if ready else detail
        ),
    }
    gaps = dashboard.setdefault("gaps", [])
    gaps[:] = [item for item in gaps if item.get("name") != "Air quality"]
    if not ready:
        gaps.append({"name": "Air quality", "detail": f"CAMS chưa live: {detail}. Lớp này không làm hạ report_status Weather/Marine."})
    return dashboard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--cams", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = attach(_load(args.dashboard), _load(args.cams))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "cams_status": result["sources"]["CAMS_AIR_QUALITY"]["status"],
        "points": {key: result["points"][key]["air_quality"]["aqi_us"] for key in POINTS},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
