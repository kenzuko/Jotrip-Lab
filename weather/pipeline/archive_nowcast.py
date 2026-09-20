"""Compact history archive for the isolated Himawari nowcast layer.

Storage model intentionally mirrors Airport Live rather than retaining every poll:
- latest.json: current valid observation
- raw/YYYY-MM-DD.json: latest full observation for the day (overwritten)
- history/YYYY-MM-DD/events.jsonl: only first-seen + material changes
- summary/YYYY-MM-DD.json: tiny running aggregates for later comparison
- catalog.json: searchable day index

This module does not import, mutate, or gate the existing weather/marine backend.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from weather.points import POINTS
from weather.collectors.himawari_nowcast import CORRIDOR_WATCH, _cloud_motion_for_target

VN_TZ = timezone(timedelta(hours=7))
POINT_ORDER = tuple(POINTS)
LEVEL_RANK = {"LOW": 0, "WATCH": 1, "ELEVATED": 2, "HIGH": 3}

# Event thresholds deliberately ignore tiny scan-to-scan noise. Daily summary still
# sees every successful sample, so long-range comparison does not depend on events.
THRESHOLDS = {
    "score": 10.0,
    "cold_cloud_top_temp_c": 3.0,
    "high_cloud_top_height_m": 500.0,
    "cooling_c_per_20m_proxy": 3.0,
}

# V5 visual layer keeps a small rolling satellite-frame ring. This is not a
# full snapshot history. It exists only so the public Cloud layer can animate
# recent observed spatial evolution without reopening many large NOAA files.
SPATIAL_HISTORY_LIMIT = 12


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _merge_spatial_frames(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    spatial = deepcopy(current.get("spatial") or {})
    current_frames = list(spatial.get("frames") or [])
    previous_frames = list(((previous or {}).get("spatial") or {}).get("frames") or [])

    merged: dict[str, dict[str, Any]] = {}
    for frame in previous_frames + current_frames:
        sampled = str(frame.get("sampled_time") or "")
        if not sampled:
            continue
        merged[sampled] = frame

    ordered = sorted(
        merged.values(),
        key=lambda frame: _parse_time(str(frame.get("sampled_time") or "")),
    )
    spatial["frames"] = ordered[-SPATIAL_HISTORY_LIMIT:]
    spatial["frame_history_limit"] = SPATIAL_HISTORY_LIMIT
    spatial["frame_history_mode"] = "ROLLING_RECENT_OBSERVED_FRAMES"
    spatial["cell_count"] = spatial.get("cell_count") or (
        len(spatial["frames"][-1].get("cells") or []) if spatial["frames"] else 0
    )
    return spatial


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _day_for(snapshot: dict[str, Any]) -> str:
    return _parse_time(snapshot.get("sampled_time") or snapshot.get("generated_at")).astimezone(VN_TZ).date().isoformat()


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v


def _compact_point(point: dict[str, Any]) -> dict[str, Any]:
    signal = point.get("convective_signal") or {}
    motion = point.get("cloud_motion") or {}
    return {
        "score": _num(signal.get("score")),
        "level": str(signal.get("level") or "").upper() or None,
        "cold_cloud_top_temp_c": _num(
            point.get("regional_cold_cloud_top_temp_c", point.get("regional_min_cloud_top_temp_c"))
        ),
        "high_cloud_top_height_m": _num(
            point.get("regional_high_cloud_top_height_m", point.get("regional_max_cloud_top_height_m"))
        ),
        "cooling_c_per_20m_proxy": _num(point.get("cooling_c_per_20m_proxy")),
        "cloud_motion": {
            "status": motion.get("status"),
            "source_sector": motion.get("source_sector"),
            "nearest_corridor": motion.get("nearest_corridor"),
            "motion_heading_deg": _num(motion.get("motion_heading_deg")),
            "motion_heading": motion.get("motion_heading"),
            "motion_speed_kmh": _num(motion.get("motion_speed_kmh")),
            "distance_to_target_km": _num(motion.get("distance_to_target_km")),
            "approaching": bool(motion.get("approaching")),
            "predicted_impact": bool(motion.get("predicted_impact")),
            "public_track_usable": bool(motion.get("public_track_usable")),
            "impact_radius_km": _num(motion.get("impact_radius_km")),
            "eta_minutes": _num(motion.get("eta_minutes")),
            "arrival_time": motion.get("arrival_time"),
            "exit_eta_minutes": _num(motion.get("exit_eta_minutes")),
            "exit_time": motion.get("exit_time"),
            "closest_approach_km": _num(motion.get("closest_approach_km")),
            "closest_approach_minutes": _num(motion.get("closest_approach_minutes")),
            "tracking_confidence": motion.get("tracking_confidence"),
            "method": motion.get("method"),
        },
        "lightning_observed": point.get("lightning_observed"),
    }


def _changes(before: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if before is None:
        return {"first_seen": {"from": None, "to": current}}

    changes: dict[str, Any] = {}
    if before.get("level") != current.get("level"):
        changes["level"] = {"from": before.get("level"), "to": current.get("level")}
    if before.get("lightning_observed") != current.get("lightning_observed"):
        changes["lightning_observed"] = {
            "from": before.get("lightning_observed"),
            "to": current.get("lightning_observed"),
        }

    numeric = {
        "score": THRESHOLDS["score"],
        "cold_cloud_top_temp_c": THRESHOLDS["cold_cloud_top_temp_c"],
        "high_cloud_top_height_m": THRESHOLDS["high_cloud_top_height_m"],
        "cooling_c_per_20m_proxy": THRESHOLDS["cooling_c_per_20m_proxy"],
    }
    for field, threshold in numeric.items():
        a, b = _num(before.get(field)), _num(current.get(field))
        if a is None and b is None:
            continue
        if a is None or b is None or abs(b - a) >= threshold:
            changes[field] = {"from": a, "to": b}
    return changes


def _summary_point(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(previous) if previous else {
        "sample_count": 0,
        "score_sum": 0.0,
        "score_count": 0,
        "min_score": None,
        "max_score": None,
        "level_counts": {"LOW": 0, "WATCH": 0, "ELEVATED": 0, "HIGH": 0},
        "levels_seen": [],
        "min_cold_cloud_top_temp_c": None,
        "max_cold_cloud_top_temp_c": None,
        "min_high_cloud_top_height_m": None,
        "max_high_cloud_top_height_m": None,
        "min_cooling_c_per_20m_proxy": None,
        "max_cooling_c_per_20m_proxy": None,
    }
    out["sample_count"] = int(out.get("sample_count", 0)) + 1

    score = _num(current.get("score"))
    if score is not None:
        out["score_sum"] = float(out.get("score_sum", 0.0)) + score
        out["score_count"] = int(out.get("score_count", 0)) + 1
        out["min_score"] = score if out.get("min_score") is None else min(float(out["min_score"]), score)
        out["max_score"] = score if out.get("max_score") is None else max(float(out["max_score"]), score)
        out["avg_score"] = round(out["score_sum"] / out["score_count"], 1)

    level = current.get("level")
    if level in LEVEL_RANK:
        counts = out.setdefault("level_counts", {k: 0 for k in LEVEL_RANK})
        counts[level] = int(counts.get(level, 0)) + 1
        seen = set(out.get("levels_seen", []))
        seen.add(level)
        out["levels_seen"] = sorted(seen, key=lambda x: LEVEL_RANK.get(x, 99))
        peak = out.get("peak_level")
        if peak not in LEVEL_RANK or LEVEL_RANK[level] > LEVEL_RANK[peak]:
            out["peak_level"] = level

    pairs = (
        ("cold_cloud_top_temp_c", "min_cold_cloud_top_temp_c", "max_cold_cloud_top_temp_c"),
        ("high_cloud_top_height_m", "min_high_cloud_top_height_m", "max_high_cloud_top_height_m"),
        ("cooling_c_per_20m_proxy", "min_cooling_c_per_20m_proxy", "max_cooling_c_per_20m_proxy"),
    )
    for source, lo_key, hi_key in pairs:
        value = _num(current.get(source))
        if value is None:
            continue
        out[lo_key] = value if out.get(lo_key) is None else min(float(out[lo_key]), value)
        out[hi_key] = value if out.get(hi_key) is None else max(float(out[hi_key]), value)
    return out


def _count_events(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def archive(snapshot: dict[str, Any], root: Path) -> dict[str, Any]:
    if snapshot.get("status") != "POINT_NUMERIC_READY":
        raise ValueError("Only POINT_NUMERIC_READY snapshots may enter the persistent archive")
    points = snapshot.get("points") or {}
    if set(points) != set(POINT_ORDER):
        raise ValueError(f"Unexpected point set: {sorted(points)}")

    day = _day_for(snapshot)
    sampled_time = snapshot.get("sampled_time") or snapshot.get("generated_at")
    raw_path = root / "raw" / f"{day}.json"
    events_path = root / "history" / day / "events.jsonl"
    summary_path = root / "summary" / f"{day}.json"
    catalog_path = root / "catalog.json"
    latest_path = root / "latest.json"
    compact_latest_path = root / "compact-latest.json"
    health_path = root / "health.json"

    previous_raw = _read_json(raw_path)
    previous_latest = _read_json(latest_path)
    previous_points = (previous_raw or {}).get("points") or {}
    events: list[dict[str, Any]] = []
    for point_id in POINT_ORDER:
        current = _compact_point(points[point_id])
        before = _compact_point(previous_points[point_id]) if point_id in previous_points else None
        changed = _changes(before, current)
        if not changed:
            continue
        events.append({
            "at": snapshot.get("generated_at"),
            "sampled_time": sampled_time,
            "type": "FIRST_SEEN" if before is None else "MATERIAL_CHANGE",
            "point": point_id,
            "changes": changed,
            "current": current,
            "source": snapshot.get("source"),
        })

    _append_jsonl(events_path, events)

    summary = _read_json(summary_path) or {
        "schema_version": "weather-nowcast-daily-summary-v1",
        "date": day,
        "archive_mode": "DAILY_RAW_PLUS_MATERIAL_EVENTS_PLUS_DAILY_SUMMARY",
        "sample_count": 0,
        "first_sampled_time": sampled_time,
        "last_sampled_time": sampled_time,
        "points": {},
    }
    summary["sample_count"] = int(summary.get("sample_count", 0)) + 1
    summary["first_sampled_time"] = summary.get("first_sampled_time") or sampled_time
    summary["last_sampled_time"] = sampled_time
    summary["last_generated_at"] = snapshot.get("generated_at")
    for point_id in POINT_ORDER:
        summary["points"][point_id] = _summary_point(
            summary["points"].get(point_id), _compact_point(points[point_id])
        )
    summary["material_event_count"] = _count_events(events_path)
    _write_json(summary_path, summary)

    # Keep only a compact rolling spatial-frame ring for the animated Cloud layer.
    # Point observations / metadata remain the newest snapshot.
    persisted_snapshot = deepcopy(snapshot)
    persisted_snapshot["spatial"] = _merge_spatial_frames(previous_latest, snapshot)
    # Recompute cloud motion after merging the rolling frame history. This lets
    # the tracker prefer a 20-40 minute baseline instead of being limited to the
    # collector's newest two scans.
    for point_id, (lat, lon) in POINTS.items():
        if point_id in (persisted_snapshot.get("points") or {}):
            persisted_snapshot["points"][point_id]["cloud_motion"] = _cloud_motion_for_target(
                persisted_snapshot["spatial"], lat, lon
            )
    persisted_snapshot["spatial"]["corridor_watch"] = CORRIDOR_WATCH
    persisted_snapshot["spatial"]["corridor_motion"] = {
        key: _cloud_motion_for_target(persisted_snapshot["spatial"], anchor["lat"], anchor["lon"])
        for key, anchor in CORRIDOR_WATCH.items()
    }

    # Airport-style daily raw: overwrite today's exact latest observation rather
    # than accumulating per-poll files. Git history lives on the isolated branch.
    _write_json(raw_path, persisted_snapshot)
    _write_json(latest_path, persisted_snapshot)

    compact_latest = {
        "schema_version": "weather-nowcast-compact-v1",
        "status": snapshot.get("status"),
        "source": snapshot.get("source"),
        "sampled_time": sampled_time,
        "generated_at": snapshot.get("generated_at"),
        "lightning_observed": snapshot.get("lightning_observed"),
        "corridor_watch": ((persisted_snapshot.get("spatial") or {}).get("corridor_watch") or {}),
        "corridor_motion": ((persisted_snapshot.get("spatial") or {}).get("corridor_motion") or {}),
        "points": {
            point_id: _compact_point(persisted_snapshot["points"][point_id])
            for point_id in POINT_ORDER
        },
    }
    _write_json(compact_latest_path, compact_latest)

    catalog = _read_json(catalog_path) or {
        "schema_version": "weather-nowcast-catalog-v1",
        "archive_mode": "DAILY_RAW_PLUS_MATERIAL_EVENTS_PLUS_DAILY_SUMMARY",
        "dates": [],
    }
    entry = {
        "date": day,
        "sample_count": summary["sample_count"],
        "material_event_count": summary["material_event_count"],
        "first_sampled_time": summary.get("first_sampled_time"),
        "last_sampled_time": summary.get("last_sampled_time"),
        "raw": f"raw/{day}.json",
        "events": f"history/{day}/events.jsonl",
        "summary": f"summary/{day}.json",
        "peak_levels": {pid: summary["points"][pid].get("peak_level") for pid in POINT_ORDER},
        "max_scores": {pid: summary["points"][pid].get("max_score") for pid in POINT_ORDER},
    }
    dates = [row for row in catalog.get("dates", []) if row.get("date") != day]
    dates.append(entry)
    dates.sort(key=lambda row: row.get("date", ""), reverse=True)
    catalog["dates"] = dates
    catalog["latest_date"] = day
    catalog["updated_at"] = snapshot.get("generated_at")
    _write_json(catalog_path, catalog)

    health = {
        "module": "JoTrip Weather Nowcast Archive",
        "state": "READY",
        "archive_mode": "DAILY_RAW_PLUS_MATERIAL_EVENTS_PLUS_DAILY_SUMMARY",
        "full_snapshot_history": False,
        "spatial_frame_history": SPATIAL_HISTORY_LIMIT,
        "spatial_frames_available": len((persisted_snapshot.get("spatial") or {}).get("frames") or []),
        "source": snapshot.get("source"),
        "date": day,
        "sampled_time": sampled_time,
        "generated_at": snapshot.get("generated_at"),
        "samples_today": summary["sample_count"],
        "material_events_today": summary["material_event_count"],
        "event_thresholds": THRESHOLDS,
    }
    _write_json(health_path, health)
    return {
        "date": day,
        "samples_today": summary["sample_count"],
        "events_written": len(events),
        "material_events_today": summary["material_event_count"],
        "root": str(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    result = archive(snapshot, args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
