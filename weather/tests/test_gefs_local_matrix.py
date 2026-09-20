import unittest
from datetime import datetime, timezone
from weather.collectors.gefs_local_matrix import (
    SPATIAL_GRID_REQUESTS,
    _file_member,
    _spatial_summaries,
    _url,
    _wind_from_direction_deg,
    _wind_sector,
    _wind_exposure_factor,
    _verification_summaries,
    _summaries,
)
from weather.processing.ensemble_local import correct_distribution

class GefsLocalMatrixTests(unittest.TestCase):
    def test_member_filenames(self):
        self.assertEqual(_file_member("c00"), "gec00")
        self.assertEqual(_file_member("p01"), "gep01")
        self.assertEqual(_file_member("p30"), "gep30")

    def test_filter_url_is_spatial_subset(self):
        cycle=datetime(2026,9,17,6,tzinfo=timezone.utc)
        u=_url(cycle,"p01",6)
        self.assertIn("filter_gefs_atmos_0p50a.pl",u)
        self.assertIn("gep01.t06z.pgrb2a.0p50.f006",u)
        self.assertIn("leftlon=103.0",u)
        self.assertIn("var_APCP=on",u)


    def test_spatial_grid_is_native_half_degree(self):
        self.assertGreaterEqual(len(SPATIAL_GRID_REQUESTS), 16)
        self.assertTrue(all(abs(lat * 2 - round(lat * 2)) < 1e-9 for lat, _ in SPATIAL_GRID_REQUESTS))
        self.assertTrue(all(abs(lon * 2 - round(lon * 2)) < 1e-9 for _, lon in SPATIAL_GRID_REQUESTS))

    def test_spatial_summary_keeps_vector_and_probability(self):
        members = {}
        for idx, wind in enumerate((20.0, 32.0, 40.0), start=1):
            members[f"p{idx:02d}"] = {
                "temperature_c": 28.0 + idx,
                "wind_kmh": wind,
                "rain_mm": float(idx * 3),
                "u10_ms": 5.0 + idx,
                "v10_ms": -2.0,
                "sampled_lat": 10.0,
                "sampled_lon": 104.0,
                "distance_km": 0.0,
            }
        vectors = {
            "grid_10.00_104.00|6|2026-09-18T06:00:00+00:00": {
                "point_id": "grid_10.00_104.00",
                "lead_hours": 6,
                "valid_time": "2026-09-18T06:00:00+00:00",
                "members": members,
            }
        }
        out = _spatial_summaries(vectors)
        self.assertEqual(out["status"], "READY")
        self.assertEqual(out["cell_count"], 1)
        self.assertEqual(len(out["frames"]), 1)
        wind = out["frames"][0]["cells"][0]["wind"]
        self.assertEqual(wind["members"], 3)
        self.assertGreater(wind["prob"], 0)
        self.assertIsNotNone(wind["u10_q50_ms"])
        self.assertIsNotNone(wind["v10_q50_ms"])
        self.assertIsNotNone(wind["direction_q50_deg"])

    def test_learning_distribution_is_raw(self):
        cal={"status":"LEARNING","applied_bias":0.0}
        out=correct_distribution([10,20,30],cal,variable="wind",threshold=25)
        self.assertEqual(out["status"],"LEARNING")
        self.assertEqual(out["raw"]["q50"],out["corrected"]["q50"])

    def test_wind_direction_uses_meteorological_from_convention(self):
        self.assertAlmostEqual(_wind_from_direction_deg(10.0, 0.0), 270.0)
        self.assertAlmostEqual(_wind_from_direction_deg(0.0, 10.0), 180.0)
        self.assertEqual(_wind_sector(225.0), "SW")

    def test_bai_sao_is_sheltered_from_west_southwest(self):
        self.assertLess(_wind_exposure_factor("bai_sao", 225.0), 0.7)
        self.assertLess(_wind_exposure_factor("bai_sao", 270.0), 0.7)
        self.assertEqual(_wind_exposure_factor("an_thoi", 225.0), 1.0)

    def test_verification_anchor_summary_is_compact(self):
        vectors = {
            "vvpq|6|2026-09-20T06:00:00+00:00": {
                "point_id": "vvpq",
                "lead_hours": 6,
                "valid_time": "2026-09-20T06:00:00+00:00",
                "members": {
                    "c00": {
                        "temperature_c": 29.0, "wind_kmh": 10.0, "rain_mm": 1.0,
                        "rain_period_start_lead": 0, "sampled_lat": 10.0,
                        "sampled_lon": 104.0, "distance_km": 12.0,
                    },
                    "p01": {
                        "temperature_c": 31.0, "wind_kmh": 14.0, "rain_mm": 3.0,
                        "rain_period_start_lead": 0, "sampled_lat": 10.0,
                        "sampled_lon": 104.0, "distance_km": 12.0,
                    },
                },
            }
        }
        out = _verification_summaries(vectors)
        row = out["vvpq"][0]
        self.assertEqual(row["temperature_q50_c"], 30.0)
        self.assertEqual(row["wind_q50_kmh"], 12.0)
        self.assertEqual(row["rain_q50_mm"], 2.0)
        self.assertEqual(row["rain_period_start_lead"], 0)

    def test_ready_calibration_changes_duong_dong_wind_distribution(self):
        members = {
            "c00": {
                "temperature_c": 29.0, "wind_kmh": 10.0, "wind_local_kmh": 10.0,
                "wind_exposure_factor": 1.0, "rain_mm": 0.0,
            },
            "p01": {
                "temperature_c": 29.0, "wind_kmh": 12.0, "wind_local_kmh": 12.0,
                "wind_exposure_factor": 1.0, "rain_mm": 0.0,
            },
        }
        vectors = {
            "duong_dong|6|2026-09-20T06:00:00+00:00": {
                "point_id": "duong_dong",
                "lead_hours": 6,
                "valid_time": "2026-09-20T06:00:00+00:00",
                "members": members,
            }
        }
        bundle = {
            "targets": {
                "vvpq": {
                    "wind": {
                        "D0_24": {
                            "status": "READY",
                            "applied_bias": 2.0,
                            "sample_count": 30,
                            "minimum_samples": 30,
                        }
                    }
                }
            }
        }
        out = _summaries(vectors, bundle)
        wind = out["duong_dong"][0]["variables"]["wind"]
        self.assertEqual(wind["status"], "CALIBRATED")
        self.assertAlmostEqual(wind["corrected"]["q50"], wind["raw"]["q50"] + 2.0, places=6)

if __name__=="__main__":
    unittest.main()
