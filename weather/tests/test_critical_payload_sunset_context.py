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
        self.assertEqual(out["cloud_motion"]["status"], "PASSING_BY")
        self.assertTrue(out["cloud_motion"]["public_track_usable"])
        self.assertFalse(out["cloud_motion"]["predicted_impact"])
        self.assertEqual(out["cloud_motion"]["closest_approach_km"], 36.1)
        self.assertEqual(out["cloud_motion"]["method"], "HIMAWARI_PATH_INTERSECTION_V2")


if __name__ == "__main__":
    unittest.main()
