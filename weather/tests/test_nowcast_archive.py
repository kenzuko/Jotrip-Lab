from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from weather.pipeline.archive_nowcast import archive
from weather.points import POINTS


def snapshot(sampled: str, score_delta: int = 0, temp_delta: float = 0.0, level: str = "WATCH") -> dict:
    points = {}
    for i, point_id in enumerate(POINTS):
        points[point_id] = {
            "lat": 10 + i / 10,
            "lon": 104 + i / 10,
            "regional_min_cloud_top_temp_c": -70.0,
            "regional_cold_cloud_top_temp_c": -60.0 + temp_delta,
            "regional_max_cloud_top_height_m": 15000,
            "regional_high_cloud_top_height_m": 13000,
            "cooling_c_per_20m_proxy": -2.0,
            "convective_signal": {
                "score": 40 + score_delta,
                "level": level,
                "method": "HIMAWARI_CLOUD_TOP_HEURISTIC_V1_NOT_LIGHTNING_OBSERVATION",
            },
            "lightning_observed": "NOT_CONNECTED",
        }
    return {
        "status": "POINT_NUMERIC_READY",
        "generated_at": sampled,
        "sampled_time": sampled,
        "source": "JMA_HIMAWARI9_VIA_NOAA_OPEN_DATA",
        "points": points,
        "spatial": {
            "status": "READY",
            "cell_count": 1,
            "frames": [{
                "sampled_time": sampled,
                "cells": [{
                    "lat": 10.0,
                    "lon": 104.0,
                    "cloud_top_cold_c": -60.0 + temp_delta,
                    "convective_score": 40 + score_delta,
                    "convective_level": level,
                }],
            }],
        },
    }


class NowcastArchiveTests(unittest.TestCase):
    def test_daily_raw_plus_material_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = archive(snapshot("2026-09-16T01:00:00Z"), root)
            self.assertEqual(first["events_written"], len(POINTS))

            # Tiny scan noise should update daily raw/summary, but not append events.
            second = archive(snapshot("2026-09-16T01:30:00Z", score_delta=4, temp_delta=1.0), root)
            self.assertEqual(second["events_written"], 0)

            # Material score + level change should append one event per point.
            third = archive(snapshot("2026-09-16T02:00:00Z", score_delta=15, level="ELEVATED"), root)
            self.assertEqual(third["events_written"], len(POINTS))

            day = "2026-09-16"
            events = (root / "history" / day / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 2 * len(POINTS))
            self.assertTrue(all(json.loads(line)["type"] in {"FIRST_SEEN", "MATERIAL_CHANGE"} for line in events))

            summary = json.loads((root / "summary" / f"{day}.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sample_count"], 3)
            self.assertEqual(summary["material_event_count"], 2 * len(POINTS))
            self.assertEqual(summary["points"]["an_thoi"]["peak_level"], "ELEVATED")
            self.assertEqual(summary["points"]["an_thoi"]["max_score"], 55.0)

            raw = json.loads((root / "raw" / f"{day}.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["sampled_time"], "2026-09-16T02:00:00Z")
            self.assertEqual(len(raw["spatial"]["frames"]), 3)
            self.assertEqual(raw["spatial"]["frames"][0]["sampled_time"], "2026-09-16T01:00:00Z")
            self.assertEqual(raw["spatial"]["frames"][-1]["sampled_time"], "2026-09-16T02:00:00Z")
            self.assertEqual(raw["spatial"]["frame_history_limit"], 12)

            catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["latest_date"], day)
            self.assertEqual(catalog["dates"][0]["sample_count"], 3)
            health = json.loads((root / "health.json").read_text(encoding="utf-8"))
            self.assertFalse(health["full_snapshot_history"])
            self.assertEqual(health["spatial_frame_history"], 12)
            self.assertEqual(health["spatial_frames_available"], 3)

    def test_rejects_invalid_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = snapshot("2026-09-16T01:00:00Z")
            bad["status"] = "UNAVAILABLE"
            with self.assertRaises(ValueError):
                archive(bad, Path(tmp))


if __name__ == "__main__":
    unittest.main()
