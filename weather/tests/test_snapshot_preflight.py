from __future__ import annotations

import unittest
from datetime import datetime, timezone

from weather.pipeline.preflight_snapshot import infer_cycle, preflight
from weather.processing.snapshot import seal_snapshot


class SnapshotPreflightTests(unittest.TestCase):
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

    def test_cycle_inference(self):
        self.assertEqual(infer_cycle("2026-09-16T05:33:00+07:00"), "0600")
        self.assertEqual(infer_cycle("2026-09-16T17:30:00+07:00"), "1800")

    def test_valid_mode_b_snapshot_passes(self):
        snapshot = self._snapshot()
        result = preflight(
            snapshot,
            max_age_minutes=120,
            expected_cycle="0600",
            now=datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(result["snapshot_valid"])
        self.assertEqual(result["recommended_mode"], "B")
        self.assertEqual(result["report_status"], "FULL")

    def test_stale_snapshot_forces_mode_c(self):
        snapshot = self._snapshot()
        result = preflight(
            snapshot,
            max_age_minutes=30,
            expected_cycle="0600",
            now=datetime(2026, 9, 16, 1, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["snapshot_valid"])
        self.assertEqual(result["recommended_mode"], "C")
        self.assertEqual(result["report_status"], "DEGRADED")

    def test_tampered_snapshot_fails_hash(self):
        snapshot = self._snapshot()
        snapshot["points"]["an_thoi"] = {"wind": 999}
        result = preflight(
            snapshot,
            max_age_minutes=120,
            expected_cycle="0600",
            now=datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["snapshot_valid"])
        self.assertIn("PAYLOAD_HASH_MISMATCH", result["failures"])

    def test_probability_cannot_escape_coherence_gate(self):
        snapshot = self._snapshot()
        snapshot["ensemble"]["p_operational_window"] = {"status": "ELIGIBLE", "value": 0.9}
        snapshot = seal_snapshot({k: v for k, v in snapshot.items() if k != "payload_hash"})
        result = preflight(
            snapshot,
            max_age_minutes=120,
            expected_cycle="0600",
            now=datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["snapshot_valid"])
        self.assertIn("ENSEMBLE_COHERENCE_GATE_VIOLATION", result["failures"])


if __name__ == "__main__":
    unittest.main()
