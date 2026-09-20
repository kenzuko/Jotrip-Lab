import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather.processing.calibration_pipeline import (
    build_actual_index,
    build_calibration,
    build_cases,
)


class CalibrationPipelineTests(unittest.TestCase):
    def test_only_actual_observations_enter_index(self):
        payloads = [
            {
                "atmosphere": {"vvpq": {
                    "data_class": "ACTUAL", "qc": "PASS",
                    "observed_at": "2026-09-20T03:00:00+00:00",
                    "temperature_c": 30, "wind_speed_kmh": 12,
                }},
                "rainfall": {"stations": {}},
            },
            {
                "atmosphere": {"vvpq": {
                    "data_class": "ESTIMATED_NOW", "qc": "PASS",
                    "observed_at": "2026-09-20T03:10:00+00:00",
                    "temperature_c": 99, "wind_speed_kmh": 99,
                }},
                "rainfall": {"stations": {}},
            },
        ]
        idx = build_actual_index(payloads)
        self.assertEqual(len(idx["vvpq"]), 1)
        self.assertEqual(idx["vvpq"][0]["temperature"], 30)

    def test_calibration_waits_for_minimum_samples(self):
        cases = [{
            "target": "vvpq", "variable": "wind", "lead_bucket": "D0_24",
            "observed": 12.0, "forecast": 10.0, "observation_class": "ACTUAL",
            "error": 2.0,
        } for _ in range(29)]
        out = build_calibration(cases, min_samples=30)
        cal = out["targets"]["vvpq"]["wind"]["D0_24"]
        self.assertEqual(cal["status"], "LEARNING")
        self.assertEqual(cal["applied_bias"], 0.0)

        cases.append({
            "target": "vvpq", "variable": "wind", "lead_bucket": "D0_24",
            "observed": 12.0, "forecast": 10.0, "observation_class": "ACTUAL",
            "error": 2.0,
        })
        out = build_calibration(cases, min_samples=30)
        cal = out["targets"]["vvpq"]["wind"]["D0_24"]
        self.assertEqual(cal["status"], "READY")
        self.assertGreater(cal["applied_bias"], 0.0)

    def test_rain_case_requires_window_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            forecast = root / "forecast"
            forecast.mkdir()
            run = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
            payload = {
                "run_time": run.isoformat(),
                "verification_points": {
                    "vrain_an_thoi": [{
                        "lead_hours": 6,
                        "valid_time": (run + timedelta(hours=6)).isoformat(),
                        "rain_q50_mm": 2.0,
                        "rain_period_start_lead": 0,
                    }]
                },
            }
            (forecast / "f.json").write_text(json.dumps(payload), encoding="utf-8")
            actual = {
                "vvpq": [],
                "rain": {
                    "vrain_an_thoi": [
                        {
                            "end": run + timedelta(minutes=10 * i),
                            "increment_mm": 0.1,
                            "window_minutes": 10,
                            "increment_qc": "PASS",
                        }
                        for i in range(1, 37)
                    ]
                },
            }
            cases = build_cases(forecast, actual)
            self.assertEqual(len(cases), 1)
            self.assertAlmostEqual(cases[0]["observed"], 3.6, places=6)
            self.assertEqual(cases[0]["observation_class"], "ACTUAL")


if __name__ == "__main__":
    unittest.main()
