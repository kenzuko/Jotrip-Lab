from __future__ import annotations

import unittest

from weather.processing.evidence_bridge import build_evidence_bridge


AUTH = {
    "duong_dong": {"lat": 10.2172, "lon": 103.9593},
    "an_thoi": {"lat": 10.0191, "lon": 104.015},
    "ganh_dau": {"lat": 10.3759, "lon": 103.9},
    "rach_gia": {"lat": 10.00677, "lon": 105.07845},
}


class EvidenceBridgeTests(unittest.TestCase):
    def test_actual_stays_actual_and_local_now_stays_estimated(self):
        current = {
            "groundtruth": {
                "status": "READY",
                "generated_at": "2026-09-22T01:00:00+00:00",
                "actual_policy": "actual only",
                "atmosphere": {"vvpq": {"data_class": "ACTUAL", "qc": "PASS"}},
                "rainfall": {"status": "FRESH", "stations": {"an_thoi": {"data_class": "ACTUAL"}}},
            },
            "local_now": {
                "engine": "PQ_LOCAL_NOW_V2",
                "generated_at": "2026-09-22T01:00:00+00:00",
                "data_class": "ESTIMATED_NOW",
                "points": {
                    "an_thoi": {"lat": 10.0191, "lon": 104.015, "analysis_time": "t", "wind_kmh": 10}
                },
            },
        }
        out = build_evidence_bridge(
            current_bundle=current, nowcast={}, local_ensemble={}, tide={},
            point_authority=AUTH, cutoff_time="2026-09-22T06:00:00+07:00",
        )
        self.assertEqual(out["actual"]["vvpq"]["data_class"], "ACTUAL")
        self.assertEqual(out["local_now"]["data_class"], "ESTIMATED_NOW")
        self.assertEqual(out["local_now"]["points"]["an_thoi"]["status"], "AVAILABLE")

    def test_local_now_rejects_old_an_thoi_reference(self):
        current = {"local_now": {"points": {
            "an_thoi": {"lat": 9.905, "lon": 104.005, "wind_kmh": 30}
        }}}
        out = build_evidence_bridge(
            current_bundle=current, nowcast={}, local_ensemble={}, tide={},
            point_authority=AUTH, cutoff_time="2026-09-22T06:00:00+07:00",
        )
        self.assertEqual(out["local_now"]["points"]["an_thoi"]["status"], "NOT_COMPARABLE")

    def test_partial_local_ensemble_does_not_unlock_probability(self):
        ensemble = {
            "status": "PARTIAL_ENSEMBLE",
            "readiness": "PARTIAL_ENSEMBLE",
            "completion_ratio": 0.6258,
            "horizon_hours": 240,
            "points": {"an_thoi": []},
        }
        out = build_evidence_bridge(
            current_bundle={}, nowcast={}, local_ensemble=ensemble, tide={},
            point_authority=AUTH, cutoff_time="2026-09-22T06:00:00+07:00",
        )
        self.assertEqual(out["ensemble_local"]["coherence_gate_75pct"], "FAIL")

    def test_nowcast_and_tide_keep_rach_gia_comparison(self):
        nowcast = {
            "status": "POINT_NUMERIC_READY",
            "points": {
                "rach_gia": {"score": 50, "level": "ELEVATED"},
                "an_thoi": {"score": 75, "level": "HIGH"},
            },
        }
        tide = {
            "status": "POINT_NUMERIC_READY",
            "points": {
                "an_thoi": {"status": "POINT_NUMERIC_READY", "current_height_m": 0.18},
                "rach_gia": {"status": "POINT_NUMERIC_READY", "current_height_m": 0.12},
            },
        }
        out = build_evidence_bridge(
            current_bundle={}, nowcast=nowcast, local_ensemble={}, tide=tide,
            point_authority=AUTH, cutoff_time="2026-09-22T06:00:00+07:00",
        )
        self.assertIn("rach_gia", out["nowcast"]["points"])
        self.assertIn("rach_gia", out["tide"]["points"])
        self.assertEqual(out["nowcast"]["points"]["rach_gia"]["level"], "ELEVATED")


if __name__ == "__main__":
    unittest.main()
