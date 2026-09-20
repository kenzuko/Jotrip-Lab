import unittest

from weather.collectors.phuquoc_ground_truth import _latest_vvpq, _vrain
from weather.processing.local_now import build
from datetime import datetime, timezone


class GroundTruthTests(unittest.TestCase):
    def test_vrain_increment_same_window(self):
        now = datetime(2026, 9, 18, 0, 20, tzinfo=timezone.utc)
        previous = {
            "rainfall": {"stations": {
                "cua_can": {
                    "accumulation_mm": 20.0,
                    "period_start": "2026-09-17T12:00:00+00:00",
                    "period_end": "2026-09-18T00:00:00+00:00",
                }
            }}
        }
        rows = [{"sn": "Cửa Cạn", "lt": 10.292693, "lg": 103.914799, "d": 21.0, "l": "Mưa vừa"}]
        timing = {"fr": 1789646400, "n": 1789690800}
        out = _vrain(rows, timing, previous, now)
        s = out["stations"]["cua_can"]
        self.assertEqual(s["increment_qc"], "PASS")
        self.assertEqual(s["increment_mm"], 1.0)
        self.assertEqual(s["increment_window_minutes"], 20.0)
        self.assertTrue(s["rain_observed"])
        self.assertEqual(s["rain_intensity_mm_h"], 3.0)

    def test_vrain_rejects_too_short_window_for_current_rain(self):
        now = datetime(2026, 9, 18, 0, 20, tzinfo=timezone.utc)
        previous = {
            "rainfall": {"stations": {
                "cua_can": {
                    "accumulation_mm": 20.0,
                    "period_start": "2026-09-17T12:00:00+00:00",
                    "period_end": "2026-09-18T00:19:48+00:00",
                }
            }}
        }
        rows = [{"sn": "Cửa Cạn", "lt": 10.292693, "lg": 103.914799, "d": 20.2, "l": "Mưa vừa"}]
        timing = {"fr": 1789646400, "n": 1789690800}
        out = _vrain(rows, timing, previous, now)
        s = out["stations"]["cua_can"]
        self.assertEqual(s["increment_qc"], "WINDOW_TOO_SHORT")
        self.assertIsNone(s["rain_observed"])
        self.assertIsNone(s["rain_intensity_mm_h"])

    def test_vvpq_units_and_convective_flag(self):
        now = datetime(2026, 9, 18, 0, 10, tzinfo=timezone.utc)
        rows = [{
            "icaoId": "VVPQ", "obsTime": 1789689600, "temp": 27, "dewp": 25,
            "wdir": 300, "wspd": 5, "visib": 5.59, "altim": 1011,
            "rawOb": "METAR VVPQ 180000Z 30005KT 9000 SCT015 FEW017CB 27/25 Q1011",
            "clouds": [{"cover": "FEW", "base": 1700}], "fltCat": "VFR",
        }]
        out = _latest_vvpq(rows, now)
        self.assertEqual(out["status"], "FRESH")
        self.assertAlmostEqual(out["wind_speed_kmh"], 9.26, places=2)
        self.assertTrue(out["convective_cloud"])

    def test_local_now_never_calls_marine_actual(self):
        gt = {
            "generated_at": "2026-09-18T00:10:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 10,
                "temperature_c": 27, "wind_speed_kmh": 10, "wind_direction_deg": 300,
                "weather": "-TSRA", "observed_at": "2026-09-18T00:00:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {
                "cua_can": {"station_name": "Cửa Cạn", "lat": 10.292693, "lon": 103.914799,
                            "age_minutes": 10, "accumulation_mm": 21, "increment_mm": 1.0,
                            "increment_window_minutes": 20, "increment_qc": "PASS"},
                "an_thoi": {"station_name": "An Thới", "lat": 10.018482, "lon": 104.0149,
                            "age_minutes": 10, "accumulation_mm": 14.8, "increment_mm": 0.4,
                            "increment_window_minutes": 20, "increment_qc": "PASS"},
            }},
            "station_status": {},
        }
        rows = [{"time_iso": "2026-09-18T07:00:00+07:00", "temperature": 28, "wind": 20, "rain": 3,
                 "wave": 0.6, "wave_max": 1.0, "period": 4, "current": 0.5}]
        dashboard = {
            "generated_at": "2026-09-18T07:00:00+07:00",
            "points": {k: {"temperature": 28, "wind": 20, "rain": 3, "wave": 0.6,
                            "wave_max": 1.0, "period": 4, "current": 0.5, "hours": rows}
                       for k in ("duong_dong", "an_thoi", "ganh_dau")}
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            k: {"convective_signal": {"score": 75}} for k in ("duong_dong", "an_thoi", "ganh_dau")
        }}
        out = build(gt, dashboard, nowcast)
        self.assertEqual(out["engine"], "PQ_LOCAL_NOW_V2")
        self.assertEqual(out["points"]["duong_dong"]["marine"]["data_class"], "MODEL_ONLY")
        self.assertEqual(out["points"]["duong_dong"]["temperature"]["data_class"], "ESTIMATED_NOW")
        self.assertEqual(out["points"]["duong_dong"]["rain"]["data_class"], "ESTIMATED_NOW")
        self.assertGreater(out["points"]["duong_dong"]["rain"]["gauge_anchor_count"], 0)

    def test_convective_background_prevents_false_calm_when_vvpq_unavailable(self):
        gt = {
            "generated_at": "2026-09-20T01:20:00+00:00",
            "atmosphere": {"vvpq": {"status": "UNAVAILABLE", "qc": "STALE"}},
            "rainfall": {"status": "FRESH", "stations": {}},
            "station_status": {},
        }
        rows = [{"time_iso": "2026-09-20T08:00:00+07:00", "temperature": 28,
                 "wind": 2.3, "gust": 7.7, "rain": 0, "wave": 0.3,
                 "wave_max": 0.6, "period": 4.7, "current": 0.3}]
        dashboard = {
            "generated_at": "2026-09-20T08:00:00+07:00",
            "points": {k: {"temperature": 28, "wind": 2.3, "gust": 7.7, "rain": 0,
                            "wave": 0.3, "wave_max": 0.6, "period": 4.7,
                            "current": 0.3, "hours": rows}
                       for k in ("duong_dong", "an_thoi", "ganh_dau")}
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            k: {"convective_signal": {"score": 90}} for k in ("duong_dong", "an_thoi", "ganh_dau")
        }}
        out = build(gt, dashboard, nowcast)
        w = out["points"]["duong_dong"]
        self.assertGreater(w["wind_kmh"], 2.3)
        self.assertLess(w["wind_kmh"], 7.7)
        self.assertEqual(w["wind"]["data_class"], "ESTIMATED_NOW")
        self.assertEqual(w["wind"]["method"], "PQ_LOCAL_NOW_V1_CONVECTIVE_BACKGROUND")

    def test_fresh_zero_accumulation_is_a_dry_anchor(self):
        gt = {
            "generated_at": "2026-09-20T03:35:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 5,
                "temperature_c": 30, "wind_speed_kmh": 13, "wind_direction_deg": 250,
                "weather": None, "observed_at": "2026-09-20T03:30:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {
                "an_thoi": {
                    "station_name": "An Thới", "lat": 10.018482, "lon": 104.0149,
                    "age_minutes": 0, "accumulation_mm": 0, "increment_mm": None,
                    "increment_window_minutes": None, "increment_qc": "WINDOW_TOO_OLD_FOR_CURRENT_RAIN",
                    "qc": "PASS",
                },
            }},
            "station_status": {},
        }
        rows = [{"time_iso": "2026-09-20T10:00:00+07:00", "temperature": 27,
                 "wind": 5.3, "gust": 13.4, "rain": 1.96, "wave": 0.26,
                 "wave_max": 0.44, "period": 4.1, "current": 0.47}]
        dashboard = {
            "generated_at": "2026-09-20T10:00:00+07:00",
            "points": {k: {"temperature": 27, "wind": 5.3, "gust": 13.4, "rain": 1.96,
                            "wave": 0.26, "wave_max": 0.44, "period": 4.1,
                            "current": 0.47, "hours": rows}
                       for k in ("duong_dong", "an_thoi", "ganh_dau")}
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            "an_thoi": {"convective_signal": {"score": 75}},
            "duong_dong": {"convective_signal": {"score": 50}},
            "ganh_dau": {"convective_signal": {"score": 50}},
        }}
        out = build(gt, dashboard, nowcast)
        rain = out["points"]["an_thoi"]["rain"]
        self.assertGreater(rain["gauge_anchor_count"], 0)
        self.assertEqual(rain["gauge_anchors"][0]["rate_mm_h"], 0.0)
        self.assertEqual(rain["gauge_anchors"][0]["evidence"], "FRESH_ZERO_ACCUMULATION")
        self.assertLess(rain["rain_rate_mm_h"], 0.4)

    def test_colocated_dry_vrain_dominates_model_rain(self):
        gt = {
            "generated_at": "2026-09-20T06:20:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 5,
                "temperature_c": 30, "wind_speed_kmh": 15, "wind_direction_deg": 250,
                "weather": None, "observed_at": "2026-09-20T06:15:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {
                "cua_can": {
                    "station_name": "Cửa Cạn", "lat": 10.292693, "lon": 103.914799,
                    "age_minutes": 0, "accumulation_mm": 0, "increment_mm": 0,
                    "increment_window_minutes": 10, "increment_qc": "PASS", "qc": "PASS",
                },
            }},
            "station_status": {},
        }
        row = {"time_iso": "2026-09-20T13:00:00+07:00", "temperature": 28,
               "wind": 5, "gust": 12, "rain": 5.54, "wave": 0.2,
               "wave_max": 0.4, "period": 4.5, "current": 0.5}
        dashboard = {
            "generated_at": "2026-09-20T13:00:00+07:00",
            "points": {"cua_can": {**row, "hours": [row]},
                       "duong_dong": {**row, "hours": [row]},
                       "an_thoi": {**row, "hours": [row]},
                       "ganh_dau": {**row, "hours": [row]}},
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            "cua_can": {"convective_signal": {"score": 90}},
            "duong_dong": {"convective_signal": {"score": 90}},
            "an_thoi": {"convective_signal": {"score": 90}},
            "ganh_dau": {"convective_signal": {"score": 90}},
        }}
        out = build(gt, dashboard, nowcast)
        rain = out["points"]["cua_can"]["rain"]
        self.assertEqual(rain["nearest_gauge_km"], 0.0)
        self.assertGreater(rain["model_share"], 0.0)
        self.assertLessEqual(rain["model_share"], 0.20)
        self.assertGreater(rain["rain_rate_mm_h"], 0.0)
        self.assertLess(rain["rain_rate_mm_h"], 0.8)
        self.assertEqual(rain["method"], "PQ_LOCAL_NOW_V2_GAUGE_CONVECTIVE_BLEND")

    def test_ensemble_spread_modulates_wind_correction_without_becoming_observation(self):
        gt = {
            "generated_at": "2026-09-20T04:00:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 5,
                "temperature_c": 30, "wind_speed_kmh": 12, "wind_direction_deg": 250,
                "observed_at": "2026-09-20T04:00:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {}},
            "station_status": {},
        }
        rows = [{"time_iso": "2026-09-20T11:00:00+07:00", "temperature": 28,
                 "wind": 5.0, "gust": 12.0, "rain": 0, "wave": 0.3,
                 "wave_max": 0.5, "period": 4.0, "current": 0.3}]
        dashboard = {
            "generated_at": "2026-09-20T11:00:00+07:00",
            "points": {k: {"temperature": 28, "wind": 5.0, "gust": 12.0, "rain": 0,
                            "wave": 0.3, "wave_max": 0.5, "period": 4.0,
                            "current": 0.3, "hours": rows}
                       for k in ("duong_dong", "an_thoi", "ganh_dau")}
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            k: {"convective_signal": {"score": 40}} for k in ("duong_dong", "an_thoi", "ganh_dau")
        }}
        ensemble = {"status": "MEMBER_MATRIX_READY", "points": {
            "duong_dong": [{
                "valid_time": "2026-09-20T11:00:00+07:00",
                "variables": {"wind": {"corrected": {
                    "q50": 7.0, "q90": 14.0, "spread": 8.0,
                    "exceedance_probability": 0.1,
                }, "raw": {}}},
            }]
        }}
        out = build(gt, dashboard, nowcast, ensemble)
        w = out["points"]["duong_dong"]["wind"]
        self.assertEqual(out["engine"], "PQ_LOCAL_NOW_V2")
        self.assertTrue(w["ensemble_context"]["available"])
        self.assertIsNotNone(w["ensemble_context"]["background_sigma_kmh"])
        self.assertIn("ENSEMBLE_AWARE", w["method"])
        self.assertEqual(w["data_class"], "ESTIMATED_NOW")

    def test_remote_dry_gauges_do_not_mask_local_convective_rain_signal(self):
        gt = {
            "generated_at": "2026-09-20T06:40:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 10,
                "temperature_c": 30, "wind_speed_kmh": 18.5, "wind_direction_deg": 260,
                "weather": None, "observed_at": "2026-09-20T06:30:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {
                "cua_can": {
                    "station_name": "Cửa Cạn", "lat": 10.292693, "lon": 103.914799,
                    "age_minutes": 0, "accumulation_mm": 0, "increment_mm": None,
                    "increment_window_minutes": None, "increment_qc": "WINDOW_TOO_SHORT", "qc": "PASS",
                },
                "bai_thom": {
                    "station_name": "Bãi Thơm", "lat": 10.411765, "lon": 104.031055,
                    "age_minutes": 0, "accumulation_mm": 0, "increment_mm": None,
                    "increment_window_minutes": None, "increment_qc": "WINDOW_TOO_SHORT", "qc": "PASS",
                },
                "an_thoi": {
                    "station_name": "An Thới", "lat": 10.018482, "lon": 104.0149,
                    "age_minutes": 0, "accumulation_mm": 0, "increment_mm": None,
                    "increment_window_minutes": None, "increment_qc": "WINDOW_TOO_SHORT", "qc": "PASS",
                },
            }},
            "station_status": {},
        }
        row = {"time_iso": "2026-09-20T13:00:00+07:00", "temperature": 27.6,
               "wind": 5.8, "gust": 22.2, "rain": 5.54, "wave": 0.25,
               "wave_max": 0.47, "period": 4.41, "current": 0.54}
        dashboard = {
            "generated_at": "2026-09-20T13:00:00+07:00",
            "points": {k: {**row, "hours": [row]}
                       for k in ("duong_dong", "an_thoi", "ganh_dau")},
        }
        nowcast = {"status": "POINT_NUMERIC_READY", "points": {
            "duong_dong": {"cooling_c_per_20m_proxy": -3.3, "convective_signal": {"score": 90}},
            "an_thoi": {"cooling_c_per_20m_proxy": -1.0, "convective_signal": {"score": 60}},
            "ganh_dau": {"cooling_c_per_20m_proxy": -1.0, "convective_signal": {"score": 60}},
        }}
        ensemble = {"status": "MEMBER_MATRIX_READY", "points": {
            "duong_dong": [{
                "valid_time": "2026-09-20T13:00:00+07:00",
                "variables": {"rain": {"corrected": {
                    "q50": 1.5, "q90": 2.6, "spread": 1.61,
                    "exceedance_probability": 0.0323,
                }}},
            }]
        }}
        out = build(gt, dashboard, nowcast, ensemble)
        rain = out["points"]["duong_dong"]["rain"]
        self.assertGreaterEqual(rain["model_share"], 0.15)
        self.assertGreater(rain["rain_rate_mm_h"], 0.35)
        self.assertEqual(rain["imminence"]["level"], "HIGH")
        self.assertTrue(rain["imminence"]["not_probability"])
        self.assertIn("HEURISTIC_NOT_PROBABILITY", rain["imminence"]["method"])

    def test_rach_gia_is_model_only_and_not_corrected_by_phu_quoc_anchors(self):
        gt = {
            "generated_at": "2026-09-20T06:20:00+00:00",
            "atmosphere": {"vvpq": {
                "status": "FRESH", "qc": "PASS", "age_minutes": 0,
                "temperature_c": 35, "wind_speed_kmh": 40, "wind_direction_deg": 250,
                "observed_at": "2026-09-20T06:20:00+00:00",
            }},
            "rainfall": {"status": "FRESH", "stations": {
                "cua_can": {
                    "station_name": "Cửa Cạn", "lat": 10.292693, "lon": 103.914799,
                    "age_minutes": 0, "accumulation_mm": 10, "increment_mm": 10,
                    "increment_window_minutes": 10, "increment_qc": "PASS", "qc": "PASS",
                }
            }},
            "station_status": {},
        }
        def pt(temp,wind,gust,rain,wave=.2):
            row={"time_iso":"2026-09-20T13:00:00+07:00","temperature":temp,"wind":wind,
                 "gust":gust,"rain":rain,"wave":wave,"wave_max":wave*1.7,"period":2.5,"current":.3}
            return {**row,"hours":[row]}
        dashboard={"generated_at":"2026-09-20T13:00:00+07:00","points":{
            "duong_dong":pt(29,5,10,2),
            "an_thoi":pt(29,5,10,2),
            "ganh_dau":pt(29,5,10,2),
            "rach_gia":pt(27.5,15.1,20.2,1.34,.26),
        }}
        nowcast={"status":"POINT_NUMERIC_READY","points":{
            "duong_dong":{"convective_signal":{"score":80}},
            "an_thoi":{"convective_signal":{"score":80}},
            "ganh_dau":{"convective_signal":{"score":80}},
            "rach_gia":{"convective_signal":{"score":75}},
        }}
        out=build(gt,dashboard,nowcast)
        rg=out["points"]["rach_gia"]
        self.assertEqual(rg["temperature_c"],27.5)
        self.assertEqual(rg["wind_kmh"],15.1)
        self.assertEqual(rg["wind"]["data_class"],"MODEL_ONLY")
        self.assertEqual(rg["rain"]["data_class"],"MODEL_ONLY")
        self.assertAlmostEqual(rg["rain"]["rain_rate_mm_h"],1.34/3,places=2)
        self.assertEqual(rg["actual_anchors"], {})
        self.assertNotIn("rach_gia_089907", out["source_status"])
        self.assertNotIn("duong_dong_60018", out["source_status"])
        self.assertNotIn("an_thoi_408", out["source_status"])


if __name__ == "__main__":
    unittest.main()
