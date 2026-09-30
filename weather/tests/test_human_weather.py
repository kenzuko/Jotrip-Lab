import unittest
from datetime import datetime, timezone
from weather.processing.human_weather import build_human_weather,heat_index_c,rain_intensity_label,relative_humidity_percent

class HumanWeatherTests(unittest.TestCase):
    def setUp(self):
        self.generated=datetime(2026,9,30,3,0,tzinfo=timezone.utc)
        self.ground={"atmosphere":{"vvpq":{"temperature_c":31.0,"dewpoint_c":27.0,"wind_speed_kmh":4.0,
            "observed_at":"2026-09-30T02:40:00Z","qc":"PASS","source":"INTERNAL_PROVIDER_NAME_MUST_NOT_LEAK"}},
            "rainfall":{"stations":{"an_thoi":{"location_id":"rain_an_thoi","rain_observed":True,
            "rain_intensity_mm_h":1.8,"increment_mm":0.45,"increment_window_minutes":15,
            "observed_at":"2026-09-30T02:50:00Z","qc":"PASS","source":"INTERNAL_RAIN_PROVIDER_MUST_NOT_LEAK"}}}}
        self.local={"points":{"an_thoi":{"rain":{"rain_rate_mm_h":2.1,"data_class":"ESTIMATED_NOW",
            "imminence":{"level":"ELEVATED","score":63}}}}}

    def test_humidity_and_heat_index_are_derived(self):
        rh=relative_humidity_percent(31.0,27.0)
        self.assertAlmostEqual(rh,79.3,places=1)
        self.assertGreater(heat_index_c(31.0,rh),31.0)

    def test_rain_language_thresholds(self):
        self.assertEqual(rain_intensity_label(1.0),"mưa rào nhẹ")
        self.assertEqual(rain_intensity_label(3.0),"mưa vừa")
        self.assertEqual(rain_intensity_label(8.0),"mưa lớn")

    def test_approved_sentence_requires_actual_and_exit(self):
        now={"points":{"an_thoi":{"cloud_motion":{"tracking_confidence":"MEDIUM_HIGH",
            "exit_time":"2026-09-30T03:37:00Z"}}}}
        item=build_human_weather(self.local,self.ground,now,self.generated)["points"]["an_thoi"]["interpretation"]
        self.assertEqual(item["headline"],"An Thới đang có mưa rào nhẹ.")
        self.assertEqual(item["detail"],"Dự kiến mưa sẽ giảm trong khoảng 30-45 phút.")
        self.assertEqual(item["evidence_class"],"ACTUAL")
        self.assertEqual(item["duration"]["data_class"],"DERIVED")

    def test_duration_not_invented_without_exit(self):
        item=build_human_weather(self.local,self.ground,{"points":{}},self.generated)["points"]["an_thoi"]["interpretation"]
        self.assertEqual(item["headline"],"An Thới đang có mưa rào nhẹ.")
        self.assertNotIn("phút",item["detail"])
        self.assertIsNone(item["duration"])

    def test_actual_and_derived_stay_separate_and_sources_do_not_leak(self):
        result=build_human_weather(self.local,self.ground,{"points":{}},self.generated)
        self.assertEqual(result["island"]["data_class"],"ACTUAL")
        self.assertEqual(result["island"]["derived"]["data_class"],"DERIVED")
        self.assertEqual(result["island"]["spatial_scope"],"ISLAND_ACTUAL_ANCHOR")
        self.assertIn("cảm giác",result["island"]["summary"])
        self.assertNotIn("INTERNAL_PROVIDER",str(result))

    def test_stale_observation_is_not_current_actual(self):
        ground={**self.ground,"atmosphere":{"vvpq":{**self.ground["atmosphere"]["vvpq"],
            "observed_at":"2026-09-29T23:00:00Z","qc":"STALE"}}}
        result=build_human_weather(self.local,ground,{"points":{}},self.generated)
        self.assertEqual(result["island"]["observation_status"],"LAST_OBSERVED")
        self.assertNotEqual(result["island"]["data_class"],"ACTUAL")

    def test_estimated_rain_is_never_relabeled_actual(self):
        ground={"atmosphere":{"vvpq":self.ground["atmosphere"]["vvpq"]},"rainfall":{"stations":{}}}
        item=build_human_weather(self.local,ground,{"points":{}},self.generated)["points"]["an_thoi"]
        self.assertIsNone(item["rain"]["actual"])
        self.assertEqual(item["interpretation"]["evidence_class"],"DERIVED")
        self.assertEqual(item["rain"]["estimate"]["data_class"],"ESTIMATED_NOW")

if __name__=="__main__":
    unittest.main()
