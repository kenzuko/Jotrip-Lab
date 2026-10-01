"""Build Weather Engine V3 shadow Observation Mesh from existing V2 evidence.

This adapter proves the V3 envelope on data we already trust. It does not fetch
external sources and does not alter Weather V2 or any public decision payload.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from weather.processing.observation_mesh_v3 import load_registry, shadow_summary


def _receipt(source_id: str, observed_at: str | None, variable: str, value: Any,
             unit: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "observed_at": observed_at,
        "received_at": extra.pop("received_at", None),
        "variable": variable,
        "value": value,
        "unit": unit,
        "numeric": isinstance(value, (int, float)) and not isinstance(value, bool),
        **extra,
    }


def receipts_from_groundtruth(gt: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    atmosphere = gt.get("atmosphere") or {}

    vvpq = atmosphere.get("vvpq") or {}
    if vvpq.get("data_class") == "ACTUAL" and vvpq.get("observed_at"):
        common = {
            "station_id": "VVPQ",
            "physical_site_id": "VVPQ_DUONG_TO",
            "lat": vvpq.get("lat"),
            "lon": vvpq.get("lon"),
            "qc_status": vvpq.get("qc") or "UNKNOWN",
            "freshness": vvpq.get("status") or "UNKNOWN",
            "raw_hash": vvpq.get("raw_payload_hash"),
            "raw_ref": vvpq.get("provenance_url"),
            "received_at": gt.get("generated_at"),
        }
        for variable, key, unit in (
            ("air_temperature", "temperature_c", "degC"),
            ("dewpoint", "dewpoint_c", "degC"),
            ("wind_direction", "wind_direction_deg", "degree"),
            ("wind_speed", "wind_speed_kmh", "km/h"),
            ("pressure", "pressure_hpa", "hPa"),
            ("visibility", "visibility_m", "m"),
        ):
            out.append(_receipt("vvpq_metar_speci", vvpq.get("observed_at"), variable, vvpq.get(key), unit, **common))
        out.append(_receipt(
            "vvpq_metar_speci", vvpq.get("observed_at"), "present_weather",
            vvpq.get("weather"), None, **common
        ))

    synop = atmosphere.get("synop_48917") or {}
    latest = synop.get("latest_numeric") or synop.get("latest") or {}
    decoded = latest.get("decoded_actual") or {}
    if latest.get("observed_at") and latest.get("data_class") == "ACTUAL":
        common = {
            "station_id": "WMO:48917",
            "physical_site_id": "WMO_48917_DUONG_DONG",
            "lat": synop.get("reference_lat") or latest.get("reference_lat"),
            "lon": synop.get("reference_lon") or latest.get("reference_lon"),
            "qc_status": latest.get("qc") or "UNKNOWN",
            "freshness": synop.get("numeric_status") or synop.get("status") or "UNKNOWN",
            "raw_hash": latest.get("raw_payload_hash"),
            "raw_ref": synop.get("provenance_url"),
            "received_at": gt.get("generated_at"),
        }
        wind = decoded.get("wind") or {}
        for variable, value, unit in (
            ("air_temperature", decoded.get("air_temperature_c"), "degC"),
            ("dewpoint", decoded.get("dewpoint_c"), "degC"),
            ("station_pressure", decoded.get("station_pressure_hpa"), "hPa"),
            ("sea_level_pressure", decoded.get("sea_level_pressure_hpa"), "hPa"),
            ("wind_direction", wind.get("direction_deg"), "degree"),
            ("wind_speed", wind.get("speed_kmh"), "km/h"),
        ):
            out.append(_receipt("wmo_48917_synop", latest.get("observed_at"), variable, value, unit, **common))

        marine = decoded.get("marine") or {}
        sst = marine.get("sea_surface_temperature") or {}
        if sst:
            out.append(_receipt("wmo_48917_synop", latest.get("observed_at"), "sea_surface_temperature", sst.get("temperature_c"), "degC", **common))

        for p in decoded.get("precipitation") or []:
            out.append(_receipt(
                "wmo_48917_synop", latest.get("observed_at"), "precipitation_accumulation",
                p.get("accumulation_mm"), "mm",
                notes=f"SYNOP accumulation window={p.get('window_hours')}h",
                **common,
            ))

    rainfall = gt.get("rainfall") or {}
    for key, station in (rainfall.get("stations") or {}).items():
        if station.get("data_class") != "ACTUAL":
            continue
        common = {
            "station_id": station.get("station_id"),
            "physical_site_id": station.get("station_id"),
            "lat": station.get("lat"),
            "lon": station.get("lon"),
            "qc_status": station.get("qc") or "UNKNOWN",
            "freshness": rainfall.get("status") or "UNKNOWN",
            "raw_hash": station.get("raw_payload_hash"),
            "raw_ref": station.get("provenance_url"),
            "received_at": station.get("fetched_at") or gt.get("generated_at"),
        }
        out.append(_receipt(
            "vrain_phu_quoc", station.get("observed_at"),
            "precipitation_accumulation", station.get("accumulation_mm"), "mm",
            notes=f"station={key}; timestamp_semantics={station.get('timestamp_semantics')}",
            **common,
        ))
        # Only emit a short increment when the V2 collector proved it is a
        # distinct-sample increment.
        if station.get("increment_qc") == "PASS":
            out.append(_receipt(
                "vrain_phu_quoc", station.get("observed_at"),
                "precipitation_increment", station.get("increment_mm"), "mm",
                notes=f"window_minutes={station.get('increment_window_minutes')}",
                **common,
            ))
    return out


def receipts_from_himawari(nowcast: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if nowcast.get("status") != "POINT_NUMERIC_READY":
        return out
    observed_at = nowcast.get("sampled_time")
    received_at = nowcast.get("generated_at")
    for point_id, point in (nowcast.get("points") or {}).items():
        common = {
            "station_id": f"HIMAWARI:{point_id}",
            "physical_site_id": point_id,
            "qc_status": "PASS",
            "freshness": "SOURCE_REPORTED",
            "received_at": received_at,
            "coverage_quality": "SATELLITE_PIXEL_SAMPLING",
        }
        for variable, key, unit in (
            ("convective_score", "score", "score"),
            ("cloud_top_temperature", "cold_cloud_top_temp_c", "degC"),
            ("cloud_top_height", "high_cloud_top_height_m", "m"),
            ("cloud_cooling_proxy", "cooling_c_per_20m_proxy", "degC/20m"),
        ):
            out.append(_receipt("himawari_existing", observed_at, variable, point.get(key), unit, **common))
    return out


def build(groundtruth: dict[str, Any], nowcast: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    registry = load_registry(registry_path)
    receipts = receipts_from_groundtruth(groundtruth)
    receipts.extend(receipts_from_himawari(nowcast))
    result = shadow_summary(receipts, registry)
    result["inputs"] = {
        "groundtruth_generated_at": groundtruth.get("generated_at"),
        "himawari_sampled_time": nowcast.get("sampled_time"),
        "himawari_generated_at": nowcast.get("generated_at"),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groundtruth", type=Path, required=True)
    parser.add_argument("--nowcast", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("weather/config/observation_sources_v3.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    gt = json.loads(args.groundtruth.read_text(encoding="utf-8"))
    nowcast = json.loads(args.nowcast.read_text(encoding="utf-8"))
    result = build(gt, nowcast, args.registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "receipt_count": result["receipt_count"],
        "independent_group_count": result["independent_group_count"],
        "counts_by_class": result["counts_by_class"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
