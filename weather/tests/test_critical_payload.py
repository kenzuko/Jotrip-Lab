import json
import unittest
from weather.pipeline.build_critical_payload import build

class CriticalPayloadTests(unittest.TestCase):
    def test_compact_payload_exposes_jotrip_forecast_without_raw_rows(self):
        dashboard={
            "generated_at":"2026-09-18T00:00:00+00:00",
            "report_status":"LIVE",
            "decision":"GO",
            "completeness":94,
            "confidence":81,
            "forecast_horizon_hours":240,
            "data_mode":"RISK_FIRST",
            "source_cycles":{"ECMWF":"2026-09-17T18:00:00+00:00"},
            "sources":{"ECMWF":{"status":"PASS","detail":"ok"}},
            "gaps":[{"name":"Lightning","detail":"not connected"}],
            "points":{}
        }
        for key in ("duong_dong","an_thoi","ganh_dau","rach_gia"):
            dashboard["points"][key]={
                "status":"LIVE",
                "temperature":27,"wind":10,"gust":20,"rain":1,"wave":0.5,"wave_max":0.9,
                "period":4,"current":0.3,"wave_regional_hs":0.6,
                "hours":[{"time_iso":"2026-09-18T03:00:00+00:00","temperature":28,"wind":12,"gust":22,"rain":2,"wave":0.6,"wave_max":1.0,"period":4.2}],
                "daily_outlook":[{"day_offset":8,"date":"2026-09-26","wind_max":20,"gust_max":30,"hs_max":1.0,"hmax_max":1.8,"rain_total":8}]
            }
        local={
            "generated_at":"2026-09-18T00:01:00+00:00",
            "engine":"PQ_LOCAL_NOW_V1",
            "points":{"duong_dong":{
                "temperature_c":26.5,"wind_kmh":9.5,"wave_hs_m":0.5,
                "rain":{"rain_rate_mm_h":0.2,"confidence":0.5,"convective_score":70,"data_class":"ESTIMATED_NOW"},
                "temperature":{"data_class":"ESTIMATED_NOW"},
                "wind":{"data_class":"ESTIMATED_NOW"},
                "marine":{"data_class":"MODEL_ONLY"}
            }}
        }
        gt={
            "atmosphere":{"vvpq":{"status":"FRESH","temperature_c":27,"wind_speed_kmh":9.2}},
            "rainfall":{"status":"FRESH","stations":{"c":{"station_name":"Cửa Cạn","accumulation_mm":21,"qc":"PASS"}}}
        }
        aqi={"status":"POINT_NUMERIC_READY","points":{"duong_dong":{"aqi_us":58,"category":"MODERATE","aqi_source":"IQAIR_COMMUNITY_REALTIME","pm25_ugm3":4,"pm10_ugm3":6,"model_aqi_us":22}}}
        tide={"status":"POINT_NUMERIC_READY","source":"COPERNICUS_MARINE_FES2014","generated_at":"2026-09-18T00:00:00Z","points":{"duong_dong":{"status":"POINT_NUMERIC_READY","current_height_m":0.1,"trend":"RISING","range_24h_m":0.5}}}
        nowcast={"status":"POINT_NUMERIC_READY","sampled_time":"2026-09-18T00:00:00Z","source":"HIMAWARI","points":{"duong_dong":{"regional_cold_cloud_top_temp_c":-60,"regional_high_cloud_top_height_m":13000,"cooling_c_per_20m_proxy":-2,"convective_signal":{"score":75,"level":"HIGH"}}}}
        ensemble={"status":"MEMBER_MATRIX_READY","readiness":"MEMBER_MATRIX_READY","source":"GEFS","run_time":"2026-09-18T00:00:00Z","completion_ratio":1,"calibration_status":"LEARNING","points":{"duong_dong":[{"lead_hours":6,"valid_time":"2026-09-18T06:00:00Z","member_count":31,"variables":{"wind":{"corrected":{"q50":12,"q90":20,"q95":22,"spread":5,"exceedance_probability":0.2,"exceedance_threshold":30,"member_count":31}},"rain":{"corrected":{"q50":1,"q90":5,"q95":7,"spread":2,"exceedance_probability":0.3,"exceedance_threshold":5,"member_count":31}},"temperature":{"corrected":{"q50":27,"q90":29,"q95":30,"spread":1,"member_count":31}}}}]}}

        p=build(dashboard,local,gt,aqi,tide,nowcast,ensemble)
        self.assertEqual(p["default_point"],"duong_dong")
        self.assertEqual(p["decision"],"GO")
        self.assertEqual(p["points"]["duong_dong"]["local"]["rain_class"],"ESTIMATED_NOW")
        self.assertEqual(p["points"]["duong_dong"]["aqi"]["aqi_us"],58.0)
        self.assertEqual(p["points"]["duong_dong"]["tide"]["trend"],"RISING")
        self.assertEqual(p["points"]["duong_dong"]["nowcast"]["convective_score"],75.0)
        self.assertEqual(p["points"]["duong_dong"]["ensemble"]["rows"][0]["wind"]["q90"],20.0)
        self.assertEqual(p["points"]["duong_dong"]["today"][0]["t"],"2026-09-18T03:00:00+00:00")
        self.assertNotIn("next24h",p["points"]["duong_dong"])
        self.assertNotIn("outlook",p["points"]["duong_dong"])
        self.assertEqual(p["public_forecast"],"JOTRIP_ENSEMBLE_LOCAL")
        self.assertEqual(p["sources"]["ECMWF"]["status"],"PASS")
        self.assertLess(len(json.dumps(p,ensure_ascii=False).encode()),30000)

if __name__=="__main__":
    unittest.main()
