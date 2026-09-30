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
        self.assertEqual(human["schema_version"],"jotrip-human-weather-v1")
        self.assertEqual(human["reference"]["actual"]["class"],"ACTUAL")
        self.assertEqual(human["reference"]["scope"],"REFERENCE_STATION_ACTUAL")
        self.assertEqual(human["reference"]["location"],"Sân bay Phú Quốc")
        self.assertEqual(human["reference"]["derived"]["class"],"DERIVED_FROM_ACTUAL")
        self.assertEqual(human["points"]["an_thoi"]["message"]["headline"],
                         "An Thới đang có mưa rào nhẹ.")
        self.assertEqual(human["points"]["an_thoi"]["message"]["detail"],
                         "Dự kiến mưa sẽ giảm trong khoảng 30-45 phút.")
        self.assertEqual(payload["actual"]["vvpq"]["dewpoint_c"],27.0)

if __name__=="__main__":
    unittest.main()
