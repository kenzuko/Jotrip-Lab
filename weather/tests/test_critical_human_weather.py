import unittest
from weather.pipeline.build_critical_payload import build

class CriticalHumanWeatherTests(unittest.TestCase):
    def test_critical_payload_exposes_shared_human_weather(self):
        dashboard={
            "generated_at":"2026-09-30T03:00:00+00:00",
            "points":{"duong_dong":{},"an_thoi":{},"ganh_dau":{},"rach_gia":{}},
            "sources":{},"gaps":[]
        }
        local={"generated_at":"2026-09-30T03:00:00+00:00","points":{
            "an_thoi":{"rain":{"rain_rate_mm_h":2.1,"data_class":"ESTIMATED_NOW",
                "imminence":{"level":"ELEVATED","score":63}}}
        }}
        ground={"generated_at":"2026-09-30T03:00:00+00:00",
            "atmosphere":{"vvpq":{"status":"FRESH","temperature_c":31.0,"dewpoint_c":27.0,
                "wind_speed_kmh":4.0,"observed_at":"2026-09-30T02:40:00+00:00","qc":"PASS"}},
            "rainfall":{"status":"FRESH","stations":{"an_thoi":{"station_name":"An Thới",
                "location_id":"rain_an_thoi","rain_observed":True,"rain_intensity_mm_h":1.8,
                "increment_mm":0.45,"increment_window_minutes":15,
                "observed_at":"2026-09-30T02:50:00+00:00","qc":"PASS"}}}}
        nowcast={"status":"POINT_NUMERIC_READY","sampled_time":"2026-09-30T02:55:00+00:00",
            "points":{"an_thoi":{"cloud_motion":{"tracking_confidence":"MEDIUM_HIGH",
            "public_track_usable":True,"exit_time":"2026-09-30T03:37:00+00:00"}}}}
        payload=build(dashboard,local,ground,nowcast=nowcast)
        human=payload["human_weather"]
        self.assertEqual(human["schema_version"],"jotrip-human-weather-v2")
        self.assertEqual(human["reference"]["status"],"ACTUAL")
        self.assertEqual(human["reference"]["scope"],"REFERENCE_STATION_ACTUAL")
        self.assertEqual(human["reference"]["location"],"Sân bay Phú Quốc")
        self.assertEqual(human["reference"]["derived"]["comfort_code"],"very_hot_humid")
        self.assertIn("humidity_hotter",human["reference"]["derived"]["reason_codes"])
        self.assertEqual(human["rain"]["an_thoi"]["headline"],"An Thới đang có mưa rào nhẹ.")
        self.assertEqual(human["rain"]["an_thoi"]["intensity_code"],"light_shower")
        self.assertEqual(human["rain"]["an_thoi"]["detail"],"Dự kiến mưa sẽ giảm trong khoảng 30-45 phút.")
        self.assertEqual(payload["actual"]["vvpq"]["dewpoint_c"],27.0)
        self.assertEqual(human["evidence_status"]["status"],"CURRENT")
        self.assertEqual(human["evidence_status"]["observed_remote"]["himawari"]["data_class"],"OBSERVED_REMOTE")

    def test_critical_ensemble_stays_first_paint_compact(self):
        dashboard={"generated_at":"2026-09-30T03:00:00+00:00",
                   "points":{"duong_dong":{},"an_thoi":{},"ganh_dau":{},"rach_gia":{}},
                   "sources":{},"gaps":[]}
        ensemble={"status":"READY","readiness":"MEMBER_MATRIX_READY","completion_ratio":1,
                  "calibration_status":"LEARNING","points":{"duong_dong":[{
                      "lead_hours":3,"valid_time":"2026-09-30T06:00:00+00:00","member_count":31,
                      "variables":{"wind":{"raw":{"q50":12,"q90":20,"q95":24,"spread":8,
                          "exceedance_probability":0.1,"exceedance_threshold":30,"member_count":31}},
                                   "rain":{"raw":{"q50":1,"q90":4,"q95":6,"spread":3,
                          "exceedance_probability":0.2,"exceedance_threshold":5,"member_count":31}},
                                   "temperature":{"raw":{"q50":30,"q90":32,"q95":33,"spread":2,
                          "exceedance_probability":0.0,"exceedance_threshold":35,"member_count":31}}}
                  }]}}
        payload=build(dashboard,{},{"atmosphere":{"vvpq":{}}},ensemble=ensemble)
        row=payload["points"]["duong_dong"]["ensemble"]["rows"][0]
        self.assertEqual(set(row),{"lead_hours","valid_time","wind","rain","temperature"})
        for name in ("wind","rain","temperature"):
            self.assertEqual(set(row[name]),{"q50","q90","spread","prob"})

if __name__=="__main__":
    unittest.main()
