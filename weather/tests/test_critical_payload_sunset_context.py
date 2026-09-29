import unittest

from weather.pipeline.build_critical_payload import compact_nowcast


class CriticalPayloadSunsetContextTests(unittest.TestCase):
    def test_cloud_motion_is_preserved_for_public_consumers(self):
        payload = {
            "status": "POINT_NUMERIC_READY",
            "sampled_time": "2026-09-29T00:20:20Z",
            "source": "JMA_HIMAWARI9_VIA_NOAA_OPEN_DATA",
            "points": {
                "duong_dong": {
                    "regional_cold_cloud_top_temp_c": -49.7,
                    "regional_high_cloud_top_height_m": 12172,
                    "cooling_c_per_20m_proxy": 0.5,
                    "convective_signal": {"score": 45, "level": "WATCH"},
                    "horizon_cloud": {
                        "status": "CLOUD_RISK",
                        "obscuration_score": 58.4,
                        "sector_cloud_fraction": 0.51,
                        "core_cloud_fraction": 0.61,
                        "sunset_azimuth_deg": 267.2,
                        "trend": "INCREASING",
                        "score_change": 14.2,
                        "dominant_layer": "LOW",
                        "confidence": "HIGH",
                        "support_cells": 18,
                        "core_support_cells": 7,
                        "method": "HIMAWARI_SUNSET_HORIZON_OCCUPANCY_V1_NOT_OPTICAL_DEPTH",
                    },
                    "cloud_motion": {
                        "status": "PASSING_BY",
                        "source_sector": "Đông Bắc",
                        "motion_heading": "Tây Bắc",
                        "motion_heading_deg": 316.5,
                        "motion_speed_kmh": 24.9,
                        "distance_to_target_km": 38.2,
                        "predicted_impact": False,
                        "approaching": False,
                        "public_track_usable": True,
                        "eta_minutes": None,
                        "closest_approach_km": 36.1,
                        "closest_approach_minutes": 30,
                        "tracking_confidence": "MEDIUM_HIGH",
                        "method": "HIMAWARI_PATH_INTERSECTION_V2",
                    },
                    "lightning_observed": "NOT_CONNECTED",
                }
            },
        }

        out = compact_nowcast(payload, "duong_dong")
        self.assertEqual(out["convective_level"], "WATCH")
        self.assertEqual(out["horizon_cloud"]["status"], "CLOUD_RISK")
        self.assertEqual(out["horizon_cloud"]["obscuration_score"], 58.4)
        self.assertEqual(out["horizon_cloud"]["dominant_layer"], "LOW")
        self.assertEqual(out["horizon_cloud"]["confidence"], "HIGH")
        self.assertNotIn("method", out["horizon_cloud"])
        self.assertNotIn("support_cells", out["horizon_cloud"])
        self.assertEqual(out["cloud_motion"]["status"], "PASSING_BY")
        self.assertTrue(out["cloud_motion"]["public_track_usable"])
        self.assertFalse(out["cloud_motion"]["predicted_impact"])
        self.assertEqual(out["cloud_motion"]["closest_approach_km"], 36.1)
        self.assertEqual(out["cloud_motion"]["method"], "HIMAWARI_PATH_INTERSECTION_V2")


if __name__ == "__main__":
    unittest.main()
