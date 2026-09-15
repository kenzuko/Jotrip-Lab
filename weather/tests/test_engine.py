from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from weather.collectors.catalog import default_manifests, latest_completed_cycle
from weather.collectors.probe import probe_source
from weather.pipeline.build_snapshot import build_snapshot
from weather.processing.drift import compare_runs
from weather.processing.ensemble import summarize_members
from weather.processing.marine import current_from_uv, summarize_route
from weather.processing.quality import assert_numeric_source, completeness, critical_gaps, numeric_weight
from weather.processing.snapshot import verify_snapshot
from weather.storage import WeatherStore

ROOT = Path(__file__).resolve().parents[1]


class QualityTests(unittest.TestCase):
    def test_no_news_numerics(self):
        self.assertEqual(numeric_weight("NEWS"), 0)
        with self.assertRaises(ValueError):
            assert_numeric_source("CONSUMER_AGGREGATOR")
        assert_numeric_source("ECMWF_DIRECT")

    def test_weighted_completeness_and_critical_gap(self):
        products = json.loads((ROOT / "config/products.json").read_text(encoding="utf-8"))
        availability = {"restriction": 1, "hs": 1, "gust": 1, "convection": 1, "visibility": 0, "wave_direction": .75, "wave_period": .5, "local_truth": .9}
        score = completeness(products["cano_south"], availability)
        self.assertGreater(score, 75)
        self.assertIn("visibility", critical_gaps(products["cano_south"], availability))


class SourceFailoverTests(unittest.TestCase):
    @patch("weather.collectors.probe.probe_url")
    def test_primary_timeout_uses_official_mirror(self, mocked):
        mocked.side_effect = [
            {"status": "RETRIEVAL_FAILED", "checked_at": "t1", "error": "timeout"},
            {"status": "REACHABLE", "checked_at": "t2", "http_status": 200},
        ]
        result = probe_source({"endpoints": [
            {"name": "primary", "url": "https://primary.invalid"},
            {"name": "official_mirror", "url": "https://mirror.invalid"},
        ]})
        self.assertEqual(result["status"], "REACHABLE")
        self.assertEqual(result["selected_endpoint"], "official_mirror")
        self.assertEqual(result["fallback_level"], 1)
        self.assertEqual(len(result["attempts"]), 2)


class EnsembleTests(unittest.TestCase):
    def test_member_gate(self):
        self.assertEqual(summarize_members(list(range(7)), 10)["status"], "NOT_ELIGIBLE")
        partial = summarize_members(list(range(8)), 10, threshold=5)
        self.assertEqual(partial["status"], "PARTIAL_ENSEMBLE")
        self.assertAlmostEqual(partial["exceedance_probability"], .25)


class MarineTests(unittest.TestCase):
    def test_current_vector_convention(self):
        self.assertEqual(current_from_uv(1, 0)["direction_toward_deg"], 90.0)

    def test_land_grid_rejected(self):
        samples = [
            {"segment_id": "land", "hs_m": 9, "gust_mps": 30, "sea_land_status": "LAND", "qc": "REJECTED_LAND_GRID", "sampled_coordinate": [104, 10]},
            {"segment_id": "sea-1", "hs_m": 1.1, "gust_mps": 8, "sea_land_status": "SEA", "qc": "PASS", "sampled_coordinate": [104.1, 9.9]},
            {"segment_id": "sea-2", "hs_m": 1.3, "gust_mps": 9, "sea_land_status": "SEA", "qc": "PASS", "sampled_coordinate": [104.2, 9.8]}
        ]
        result = summarize_route(samples)
        self.assertEqual(result["route_max_hs_m"], 1.3)
        self.assertEqual(result["worst_segment"], "sea-2")


class DriftTests(unittest.TestCase):
    def test_pushback_only_comparable_runs(self):
        base = {"model": "GEFS", "system": "ens", "variable": "hs", "location_id": "route", "valid_window": "D1_AM", "extraction_method": "route_v1", "value": 1.8, "onset_hour": 6}
        current = dict(base, value=1.2, onset_hour=18)
        self.assertEqual(compare_runs(base, current)["trend"], "RECEDING")
        self.assertEqual(compare_runs(base, dict(current, model="ECMWF"))["status"], "NOT_COMPARABLE")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_sealed_and_archived(self):
        fixture = json.loads((ROOT / "tests/fixtures/an_thoi_2026_09_14.json").read_text(encoding="utf-8"))
        health = {"ECMWF_DIRECT": {"status": "REACHABLE"}, "NOAA_GEFS_DIRECT": {"status": "RETRIEVAL_FAILED"}}
        snapshot = build_snapshot(fixture, datetime(2026, 9, 14, 22, 45, tzinfo=timezone.utc), health)
        self.assertTrue(verify_snapshot(snapshot))
        self.assertEqual(snapshot["points"]["an_thoi"]["base_state"]["sea_state"], "NORMAL")
        self.assertEqual(snapshot["points"]["an_thoi"]["decision"], "GO_WITH_WATCH")
        with tempfile.TemporaryDirectory() as folder:
            store = WeatherStore(Path(folder) / "weather.db")
            store.save_snapshot(snapshot)
            self.assertEqual(store.get_snapshot(snapshot["snapshot_id"])["payload_hash"], snapshot["payload_hash"])
            store.close()

    def test_manifest_has_direct_provenance_and_bbox(self):
        manifests = default_manifests(datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
        self.assertTrue(all(m["provenance"] == "DIRECT" for m in manifests))
        self.assertTrue(all(len(m["bounding_box"]) == 4 for m in manifests))

    def test_latest_completed_run_never_future(self):
        now = datetime(2026, 9, 15, 2, tzinfo=timezone.utc)
        run = latest_completed_cycle(now, (0, 6, 12, 18), 6)
        self.assertLess(run, now)


if __name__ == "__main__":
    unittest.main()
