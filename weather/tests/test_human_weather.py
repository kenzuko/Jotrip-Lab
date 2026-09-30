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
        self.assertEqual(rain_intensity_label(1.0),"mưa nhẹ")
        self.assertEqual(rain_intensity_label(3.0),"mưa vừa")
        self.assertEqual(rain_intensity_label(8.0),"mưa lớn")

    def test_approved_sentence_requires_actual_and_fresh_track(self):
        now={"sampled_time":"2026-09-30T02:55:00Z","points":{"an_thoi":{"cloud_motion":{
            "tracking_confidence":"MEDIUM_HIGH","public_track_usable":True,
            "exit_time":"2026-09-30T03:37:00Z"}}}}
        item=build_human_weather(self.local,self.ground,now,self.generated)["rain"]["an_thoi"]
        self.assertEqual(item["headline"],"An Thới đang có mưa rào nhẹ.")
        self.assertEqual(item["detail"],"Dự kiến mưa sẽ giảm trong khoảng 30-45 phút.")
        self.assertEqual(item["evidence"],"ACTUAL")
        self.assertEqual(item["intensity_code"],"light_shower")
        self.assertEqual(item["duration_min"],[30,45])

    def test_stale_nowcast_cannot_claim_shower_or_duration(self):
        now={"sampled_time":"2026-09-30T02:00:00Z","points":{"an_thoi":{"cloud_motion":{
            "tracking_confidence":"HIGH","public_track_usable":True,
            "exit_time":"2026-09-30T03:37:00Z"}}}}
        item=build_human_weather(self.local,self.ground,now,self.generated)["rain"]["an_thoi"]
        self.assertEqual(item["headline"],"An Thới đang có mưa nhẹ.")
        self.assertEqual(item["intensity_code"],"light")
        self.assertNotIn("phút",item["detail"])
        self.assertNotIn("duration_min",item)

    def test_light_rain_is_not_called_shower_without_showery_signal(self):
        now={"sampled_time":"2026-09-30T02:55:00Z","points":{"an_thoi":{}}}
        item=build_human_weather(self.local,self.ground,now,self.generated)["rain"]["an_thoi"]
        self.assertEqual(item["headline"],"An Thới đang có mưa nhẹ.")

    def test_actual_and_derived_stay_separate_and_sources_do_not_leak(self):
        result=build_human_weather(self.local,self.ground,{"points":{}},self.generated)
        ref=result["reference"]
        self.assertEqual(ref["status"],"ACTUAL")
        self.assertAlmostEqual(ref["derived"]["humidity_pct"],79.3,places=1)
        self.assertEqual(ref["derived"]["comfort_code"],"very_hot_humid")
        self.assertIn("humidity_hotter",ref["derived"]["reason_codes"])
        self.assertEqual(ref["scope"],"REFERENCE_STATION_ACTUAL")
        self.assertEqual(ref["location"],"Sân bay Phú Quốc")
        self.assertEqual(ref["actual"]["temperature_c"],31.0)
        self.assertNotIn("INTERNAL_PROVIDER",str(result))

    def test_stale_observation_is_not_current_actual(self):
        ground={**self.ground,"atmosphere":{"vvpq":{**self.ground["atmosphere"]["vvpq"],
            "observed_at":"2026-09-29T23:00:00Z","qc":"STALE"}}}
        ref=build_human_weather(self.local,ground,{"points":{}},self.generated)["reference"]
        self.assertEqual(ref["status"],"LAST_OBSERVED")

    def test_estimated_rain_is_not_published_as_human_actual(self):
        ground={"atmosphere":{"vvpq":self.ground["atmosphere"]["vvpq"]},"rainfall":{"stations":{}}}
        result=build_human_weather(self.local,ground,{"points":{}},self.generated)
        self.assertNotIn("an_thoi",result["rain"])
        actual=build_human_weather(self.local,self.ground,{"points":{}},self.generated)["rain"]["an_thoi"]
        self.assertEqual(actual["evidence"],"ACTUAL")
        self.assertEqual(actual["derived_rate_mm_h"],1.8)

if __name__=="__main__":
    unittest.main()
