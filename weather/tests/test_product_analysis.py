from __future__ import annotations

import unittest

from weather.processing.product_analysis import build_product_analysis


class ProductAnalysisTests(unittest.TestCase):
    def _points(self):
        return {
            "an_thoi": {
                "wave": .6,
                "period": 4.0,
                "current": .5,
                "hours": [
                    {"time_iso": "2026-09-22T07:00:00+07:00", "wind": 30, "gust": 42, "wave": .7, "period": 4, "rain": 3},
                    {"time_iso": "2026-09-22T10:00:00+07:00", "wind": 25, "gust": 35, "wave": .6, "period": 4.2, "rain": 1},
                    {"time_iso": "2026-09-22T16:00:00+07:00", "wind": 15, "gust": 22, "wave": .5, "period": 4.3, "rain": 2},
                ],
            }
        }

    def test_completeness_does_not_turn_missing_analysis_into_weather_risk(self):
        marine = {"an_thoi": {"wave": {"direction_deg": 250}, "current": {"speed_kmh": .5}}}
        result = build_product_analysis(
            self._points(), marine, cutoff_time="2026-09-22T06:00:00+07:00"
        )
        cano = result["products"]["cano_south"]
        self.assertEqual(cano["status"], "PARTIAL")
        self.assertIn("convection", cano["analysis_gaps"])
        self.assertIn("visibility", cano["critical_data_gaps"])
        self.assertGreater(cano["completeness"], 0)
        self.assertNotEqual(cano["completeness"], 100)

    def test_fishing_windows_keep_morning_and_afternoon_separate(self):
        result = build_product_analysis(
            self._points(), {}, cutoff_time="2026-09-22T06:00:00+07:00"
        )
        morning = result["products"]["fishing_hon_dam_morning"]
        afternoon = result["products"]["fishing_hon_dam_afternoon"]
        self.assertTrue(all(5 <= datetime_hour(w["start_time"]) < 14 for w in morning["background_windows"]))
        self.assertTrue(all(datetime_hour(w["end_time"]) <= 14 for w in morning["background_windows"]))
        self.assertTrue(all(14 <= datetime_hour(w["start_time"]) < 21 for w in afternoon["background_windows"]))
        self.assertTrue(all(datetime_hour(w["end_time"]) <= 21 for w in afternoon["background_windows"]))


def datetime_hour(value: str) -> int:
    from datetime import datetime
    return datetime.fromisoformat(value).hour


if __name__ == "__main__":
    unittest.main()
