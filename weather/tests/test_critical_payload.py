import unittest, json
from weather.pipeline.build_critical_payload import build

class CriticalPayloadTests(unittest.TestCase):
    def test_small_complete_payload(self):
        dashboard={"generated_at":"2026-09-18T00:00:00+00:00","report_status":"LIVE","points":{}}
        for key in ("duong_dong","an_thoi","ganh_dau","rach_gia"):
            dashboard["points"][key]={"temperature":27,"wind":10,"gust":20,"rain":1,"wave":0.5,"wave_max":0.9,"period":4,"current":0.3,
              "hours":[{"time_iso":"2026-09-18T03:00:00+00:00","temperature":28,"wind":12,"gust":22,"rain":2,"wave":0.6,"wave_max":1.0,"period":4.2}]}
        local={"generated_at":"2026-09-18T00:01:00+00:00","engine":"PQ_LOCAL_NOW_V1","points":{"duong_dong":{"temperature_c":26.5,"wind_kmh":9.5,"rain":{"rain_rate_mm_h":0.2,"confidence":0.5,"convective_score":70,"data_class":"ESTIMATED_NOW"},"temperature":{"data_class":"ESTIMATED_NOW"},"wind":{"data_class":"ESTIMATED_NOW"},"marine":{"data_class":"MODEL_ONLY"},"wave_hs_m":0.5}}}
        gt={"atmosphere":{"vvpq":{"status":"FRESH","temperature_c":27,"wind_speed_kmh":9.2}},"rainfall":{"status":"FRESH","stations":{"c":{"station_name":"Cửa Cạn","accumulation_mm":21,"qc":"PASS"}}}}
        p=build(dashboard,local,gt)
        self.assertEqual(p["default_point"],"duong_dong")
        self.assertEqual(p["points"]["duong_dong"]["local"]["rain_class"],"ESTIMATED_NOW")
        self.assertEqual(len(p["points"]["duong_dong"]["next24h"]),1)
        self.assertLess(len(json.dumps(p,ensure_ascii=False).encode()),20000)
if __name__=="__main__": unittest.main()
