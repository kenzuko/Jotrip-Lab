from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weather.pipeline.master_snapshot import consumer_status, load_validated_snapshot
from weather.processing.snapshot import seal_snapshot


class MasterSnapshotTests(unittest.TestCase):
    def _snapshot(self):
        payload = {
            "snapshot_id": "PQWX_CANONICAL_TEST_V1",
            "schema_version": "1.0",
            "cutoff_time": "2026-09-16T05:33:00+07:00",
            "generated_at": "2026-09-15T22:34:00+00:00",
            "data_mode": "B",
            "direct_ingest_status": {},
            "git_commit_sha": "abc",
            "formula_bundle_version": "weather-lab-0.2.0",
            "critical_data_gaps": [],
            "points": {"duong_dong": {}, "an_thoi": {}, "ganh_dau": {}},
            "routes": {},
            "ensemble": {
                "gefs_atmosphere_member_gate": {"full_matrix_complete": False},
                "gefs_wave_member_gate": {"full_matrix_complete": False},
                "p_operational_window": {"status": "NOT_COMPUTABLE"},
            },
            "observations": {},
            "official_status": {},
            "drift": {},
            "data_gaps": [],
            "unit_policy": {"operational_speed": "km/h", "raw_units_preserved": True},
            "audit": {},
        }
        return seal_snapshot(payload)

    def _write(self, payload):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "LAB_SNAPSHOT_V1.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return tmp, path

    def test_master_receives_exact_valid_snapshot(self):
        snapshot = self._snapshot()
        tmp, path = self._write(snapshot)
        self.addCleanup(tmp.cleanup)
        loaded, pre = load_validated_snapshot(
            path,
            max_age_minutes=120,
            expected_cycle="0600",
            now=datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(loaded, snapshot)
        self.assertTrue(pre["snapshot_valid"])

    def test_invalid_snapshot_removes_numerical_layer(self):
        snapshot = self._snapshot()
        snapshot["points"]["an_thoi"] = {"wind": 999}
        tmp, path = self._write(snapshot)
        self.addCleanup(tmp.cleanup)
        status = consumer_status(
            path,
            max_age_minutes=120,
            expected_cycle="0600",
            now=datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(status["consumer_status"], "LAB_DATA_PLANE_DEGRADED")
        self.assertEqual(status["recommended_mode"], "C")
        self.assertEqual(status["numerical_model_layer"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
