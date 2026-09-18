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
            "station_status": {"60018": {"readiness": "FEED_EMPTY"}, "408": {"readiness": "FEED_UNRESOLVED"}},
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
        self.assertEqual(out["engine"], "PQ_LOCAL_NOW_V1")
        self.assertEqual(out["points"]["duong_dong"]["marine"]["data_class"], "MODEL_ONLY")
        self.assertEqual(out["points"]["duong_dong"]["temperature"]["data_class"], "ESTIMATED_NOW")
        self.assertEqual(out["points"]["duong_dong"]["rain"]["data_class"], "ESTIMATED_NOW")
        self.assertGreater(out["points"]["duong_dong"]["rain"]["gauge_anchor_count"], 0)


if __name__ == "__main__":
    unittest.main()
