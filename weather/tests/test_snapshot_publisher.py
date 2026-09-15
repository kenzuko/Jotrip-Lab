from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weather.pipeline.publish_snapshot import build_canonical_snapshot, publish, validate_snapshot
from weather.processing.snapshot import verify_snapshot


class SnapshotPublisherTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = {
            "snapshot_id": "PQWX_LIVE_TEST",
            "generated_at": "2026-09-16T05:33:48+07:00",
            "data_mode": "B",
            "report_status": "LIVE",
            "source_cycles": {"ECMWF": "2026-09-15T12:00:00+00:00"},
            "gaps": [{"name": "Nowcast offshore", "detail": "unresolved"}],
            "points": {
                "duong_dong": {"name": "Dương Đông"},
                "an_thoi": {"name": "An Thới"},
                "ganh_dau": {"name": "Gành Dầu"},
                "rach_gia": {"name": "Rạch Giá"},
            },
        }
        self.ecmwf = {"readiness": "POINT_ROUTE_EXTRACTED", "run_time": "2026-09-15T12:00:00+00:00", "horizon_hours": 240, "record_count": 2100}
        summary = {"status": "ELIGIBLE", "member_count": 31, "expected_members": 31, "completion_ratio": 1.0, "q50": 1.0, "q90": 2.0, "q95": 2.5}
        self.gefs = {
            "atmosphere": {"readiness": "MEMBER_COMPLETE", "run_time": "2026-09-15T18:00:00+00:00", "summary": summary},
            "wave": {"readiness": "MEMBER_COMPLETE", "run_time": "2026-09-15T18:00:00+00:00", "summary": summary},
        }
        self.icon = {"status": "POINT_NUMERIC_READY", "field_url": "official"}
        self.copernicus = {"status": "POINT_NUMERIC_READY", "wave": {"available_variables": ["VHM0"]}, "current": {"available_variables": ["uo", "vo"]}}

    def test_build_is_sealed_and_keeps_mode_b(self):
        snapshot = build_canonical_snapshot(self.dashboard, self.ecmwf, self.gefs, self.icon, self.copernicus)
        validate_snapshot(snapshot, self.dashboard)
        self.assertTrue(verify_snapshot(snapshot))
        self.assertEqual(snapshot["data_mode"], "B")
        self.assertFalse(snapshot["ensemble"]["gefs_atmosphere_member_gate"]["full_matrix_complete"])
        self.assertEqual(snapshot["ensemble"]["p_operational_window"]["status"], "NOT_COMPUTABLE")

    def test_publish_writes_archive_latest_and_pointer(self):
        snapshot = build_canonical_snapshot(self.dashboard, self.ecmwf, self.gefs, self.icon, self.copernicus)
        with tempfile.TemporaryDirectory() as temp:
            archive, latest, pointer = publish(snapshot, Path(temp))
            self.assertTrue(archive.exists())
            self.assertTrue(latest.exists())
            self.assertTrue(pointer.exists())

    def test_missing_required_point_fails(self):
        broken = dict(self.dashboard)
        broken["points"] = {"an_thoi": {}, "duong_dong": {}}
        with self.assertRaises(ValueError):
            build_canonical_snapshot(broken, self.ecmwf, self.gefs, self.icon, self.copernicus)


if __name__ == "__main__":
    unittest.main()
