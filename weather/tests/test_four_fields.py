"""Time-aligned four-field regression: real ECMWF offshore grid, never copied now-wave."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from weather.pipeline.build_dashboard import _add_coastal_wave_reference
from weather.collectors.ecmwf_72h import _collect_gust, MEDIUM_SPATIAL_GRID_REQUESTS


VALID = "2026-09-23T00:00:00Z"
LOCAL = "2026-09-23T07:00:00+07:00"


def offshore_frame(valid=VALID):
    return {"valid_time": valid, "cells": [
        {"lat": 10.0, "lon": 103.75, "wave_hs_m": 0.61, "wave_period_s": 4.0},
        {"lat": 10.0, "lon": 104.25, "wave_hs_m": 0.44, "wave_period_s": 3.0},
        {"lat": 10.5, "lon": 103.75, "wave_hs_m": None, "wave_period_s": None},
    ]}


class FourFieldsTests(unittest.TestCase):
    def test_medium_forecast_samples_both_reviewed_offshore_coasts(self):
        # Long-range fields otherwise lack a valid wave grid near either shore.
        self.assertIn((10.0, 103.75), MEDIUM_SPATIAL_GRID_REQUESTS)
        self.assertIn((10.0, 104.25), MEDIUM_SPATIAL_GRID_REQUESTS)


    def test_missing_coastal_wave_uses_correct_side_same_time_with_explicit_reference(self):
        rows = {
            "duong_dong": [{"time_iso": LOCAL, "wind": 12, "gust": 18, "rain": 2, "wave": None, "period": None, "wave_max": None}],
            "ham_ninh": [{"time_iso": LOCAL, "wind": 10, "gust": 16, "rain": 1, "wave": None, "period": None, "wave_max": None}],
        }
        _add_coastal_wave_reference(rows, {"status": "READY", "frames": [offshore_frame()]})
        self.assertEqual(rows["duong_dong"][0]["wave"], 0.61)
        self.assertEqual(rows["ham_ninh"][0]["wave"], 0.44)
        for point, side in (("duong_dong", "WEST"), ("ham_ninh", "EAST")):
            row = rows[point][0]
            self.assertEqual(row["wave_source"], "ECMWF_WAVE_OFFSHORE_GRID_REFERENCE")
            self.assertEqual(row["wave_reference"]["coast_side"], side)
            self.assertLessEqual(row["wave_reference"]["distance_km"], 35)
            self.assertEqual(row["wave_reference"]["valid_time"], VALID)
            self.assertFalse(row["wave_reference"]["nearshore_observation"])
            self.assertTrue(all(row[field] is not None for field in ("rain", "wind", "gust", "wave")))

    def test_missing_time_or_distant_grid_never_fabricates_wave(self):
        rows = {"duong_dong": [{"time_iso": LOCAL, "wave": None, "period": None}]}
        _add_coastal_wave_reference(rows, {"status": "READY", "frames": [offshore_frame("2026-09-23T03:00:00Z")]})
        self.assertIsNone(rows["duong_dong"][0]["wave"])
        _add_coastal_wave_reference(rows, {"status": "READY", "frames": [
            {"valid_time": VALID, "cells": [{"lat": 9.5, "lon": 103.25, "wave_hs_m": 2.0}]}
        ]})
        self.assertIsNone(rows["duong_dong"][0]["wave"])

    def test_never_overwrite_valid_direct_wave(self):
        rows = {"duong_dong": [{"time_iso": LOCAL, "wave": 0.33, "period": 4.1}]}
        _add_coastal_wave_reference(rows, {"status": "READY", "frames": [offshore_frame()]})
        self.assertEqual(rows["duong_dong"][0]["wave"], 0.33)
        self.assertNotIn("wave_reference", rows["duong_dong"][0])

    @patch("weather.collectors.ecmwf_72h._decode_all")
    def test_missing_10fg_lead_is_fetched_from_i10fg(self, decode):
        class Client:
            def __init__(self):
                self.calls = []
            def retrieve(self, **kwargs):
                self.calls.append((kwargs["param"][0], kwargs["step"]))
        def result(path, *_args):
            field = "10fg" if "gust-10fg" in str(path) else "i10fg"
            lead = 3 if field == "10fg" else 6
            return [{"variable": field, "lead_hours": lead, "point_id": "duong_dong",
                     "sample_kind": "OPERATIONAL_ANCHOR", "qc": "PASS", "value": 5}]
        decode.side_effect = result
        client = Client()
        records, source, error = _collect_gust(
            client, Path("/tmp"), datetime(2026, 9, 23, tzinfo=timezone.utc),
            [0, 3, 6], "test", ()
        )
        self.assertEqual(source, "10fg+i10fg")
        self.assertIsNone(error)
        self.assertEqual({r["lead_hours"] for r in records}, {3, 6})
        self.assertEqual(client.calls, [("10fg", [3, 6]), ("i10fg", [6])])


if __name__ == "__main__":
    unittest.main()
