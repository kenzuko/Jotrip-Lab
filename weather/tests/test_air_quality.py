import unittest

from weather.pipeline.attach_air_quality import attach
from weather.processing.air_quality import category, particulate_aqi


class AirQualityTests(unittest.TestCase):
    def test_pm25_2024_breakpoints(self):
        self.assertEqual(particulate_aqi(9.0, None)["aqi_us"], 50)
        self.assertEqual(particulate_aqi(9.1, None)["aqi_us"], 51)
        self.assertEqual(particulate_aqi(35.5, None)["aqi_us"], 101)
        self.assertEqual(category(151), "UNHEALTHY")

    def test_dominant_pollutant(self):
        result = particulate_aqi(20.0, 300.0)
        self.assertEqual(result["dominant_pollutant"], "PM10")
        self.assertGreater(result["aqi_us"], 150)

    def test_attach_is_non_critical_when_cams_missing(self):
        dashboard = {
            "report_status": "LIVE",
            "sources": {},
            "gaps": [],
            "points": {key: {} for key in ("an_thoi", "duong_dong", "ganh_dau", "rach_gia")},
        }
        result = attach(dashboard, {"status": "CREDENTIALS_MISSING", "detail": "token missing"})
        self.assertEqual(result["report_status"], "LIVE")
        self.assertEqual(result["sources"]["CAMS_AIR_QUALITY"]["status"], "UNRESOLVED")
        self.assertTrue(all(result["points"][key]["air_quality"]["aqi_us"] is None for key in result["points"]))

    def test_attach_ready_values(self):
        points = {
            key: {
                "aqi_us": 74,
                "category": "MODERATE",
                "dominant_pollutant": "PM2.5",
                "pm25_ugm3": 22.0,
                "pm10_ugm3": 35.0,
                "sampled_time": "2026-09-16T00:00:00Z",
                "grid_lat": 10.0,
                "grid_lon": 104.0,
            }
            for key in ("an_thoi", "duong_dong", "ganh_dau", "rach_gia")
        }
        dashboard = {"report_status": "LIVE", "sources": {}, "gaps": [], "points": {key: {} for key in points}}
        result = attach(dashboard, {"status": "POINT_NUMERIC_READY", "points": points, "grid_resolution": "0.4deg", "sampled_time": "2026-09-16T00:00:00Z"})
        self.assertEqual(result["sources"]["CAMS_AIR_QUALITY"]["status"], "PASS")
        self.assertEqual(result["points"]["an_thoi"]["air_quality"]["aqi_us"], 74)
        self.assertEqual(result["report_status"], "LIVE")


if __name__ == "__main__":
    unittest.main()
