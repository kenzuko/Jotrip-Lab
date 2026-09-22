from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weather.pipeline.production_contract import build_manifest, freeze_report_input
from weather.processing.point_drift import compare_point_snapshots
from weather.processing.snapshot import seal_snapshot


class ProductionContractTests(unittest.TestCase):
    def _snapshot(self, snapshot_id="S1", wind=10.0):
        payload = {
            "snapshot_id": snapshot_id,
            "schema_version": "1.0",
            "cutoff_time": "2026-09-22T06:00:00+07:00",
            "generated_at": "2026-09-21T23:00:01+00:00",
            "data_mode": "B",
            "direct_ingest_status": {},
            "git_commit_sha": "abc",
            "formula_bundle_version": "weather-lab-0.2.0",
            "critical_data_gaps": [],
            "points": {
                "an_thoi": {"reference_point": {"lat": 10.0191, "lon": 104.015, "type": "AREA_REFERENCE"}, "hours": [
                    {"time_iso": "2026-09-22T07:00:00+07:00", "wind": wind, "gust": 20, "wave": .5, "rain": 1},
                    {"time_iso": "2026-09-22T10:00:00+07:00", "wind": wind + 5, "gust": 25, "wave": .6, "rain": 2},
                ]}
            },
            "routes": {},
            "ensemble": {},
            "data_gaps": [],
            "unit_policy": {},
            "audit": {"source_cycles": {"ECMWF": "2026-09-21T12:00:00+00:00"}},
            "point_authority": {"an_thoi": {"lat": 10.0191, "lon": 104.015}},
            "analysis_status": {"drift": "AVAILABLE"},
        }
        return seal_snapshot(payload)

    def test_manifest_verifies_pointer_lineage(self):
        snapshot = self._snapshot()
        pointer = {k: snapshot[k] for k in ("snapshot_id", "payload_hash", "cutoff_time", "schema_version")}
        pointer["path"] = "weather/snapshots/2026/09/22/060000/LAB_SNAPSHOT_V1.json"
        manifest = build_manifest(snapshot, pointer)
        self.assertEqual(manifest["production_reference"], "weather.openphuquoc.com")
        self.assertEqual(manifest["snapshot"]["snapshot_id"], "S1")
        self.assertEqual(manifest["report_cycle"], "0600")

    def test_report_freeze_is_immutable(self):
        snapshot = self._snapshot()
        with tempfile.TemporaryDirectory() as temp:
            first = freeze_report_input(snapshot, root=Path(temp), cycle="0600")
            second = freeze_report_input(snapshot, root=Path(temp), cycle="0600")
            self.assertEqual(first, second)

    def test_point_drift_same_valid_time(self):
        previous = self._snapshot("OLD", 10.0)
        current = self._snapshot("NEW", 15.0)
        result = compare_point_snapshots(previous, current["points"], cutoff_time=current["cutoff_time"])
        self.assertEqual(result["status"], "AVAILABLE")
        wind = result["points"]["an_thoi"]["variables"]["wind"]
        self.assertEqual(wind["mean_delta"], 5.0)
        self.assertEqual(wind["peak_amplitude_drift"], 5.0)
        self.assertEqual(result["trend_classification"]["status"], "NOT_COMPUTABLE")

    def test_point_drift_rejects_authority_change(self):
        previous = self._snapshot("OLD", 10.0)
        current = self._snapshot("NEW", 15.0)
        previous["points"]["an_thoi"]["reference_point"] = {"lat": 9.905, "lon": 104.005, "type": "AREA_REFERENCE"}
        previous = seal_snapshot({k: v for k, v in previous.items() if k != "payload_hash"})
        result = compare_point_snapshots(previous, current["points"], cutoff_time=current["cutoff_time"])
        self.assertEqual(result["status"], "NOT_COMPUTABLE")
        self.assertEqual(
            result["points"]["an_thoi"]["reason"],
            "POINT_AUTHORITY_CHANGED_OR_UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
