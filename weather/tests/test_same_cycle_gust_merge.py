"""Safety regression: repair forecast gust gaps only from a matching ECMWF run.

Do not join wind and gust across different model cycles, points or valid times.
Missing gusts remain null when no compatible model pair exists.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather.collectors.ecmwf_72h import _collect_gust, _merge_spatial, _spatial_frames
from weather.pipeline.build_dashboard import _merge_short_medium

VALID = "2026-09-30T03:00:00+00:00"


def point(wind, gust, rain=1.0, when=VALID):
    return {"time_iso": when, "wind": wind, "gust": gust, "rain": rain}


def cell(variable, value, *, when=VALID, cell_id="grid_10.00_104.00"):
    return {
        "sample_kind": "SPATIAL_GRID",
        "qc": "PASS",
        "point_id": cell_id,
        "valid_time": when,
        "lead_hours": 3,
        "variable": variable,
        "value": value,
        "unit": "m s**-1",
        "sampled_lat": 10.0,
        "sampled_lon": 104.0,
        "requested_lat": 10.0,
        "requested_lon": 104.0,
    }


class SameCycleGustTests(unittest.TestCase):
    def test_point_patches_both_wind_and_gust_on_identical_cycle_only(self):
        result = _merge_short_medium([point(18, None, rain=7)],
                                     [point(20, 34, rain=99)], same_cycle=True)
        self.assertEqual(result[0]["wind"], 20)
        self.assertEqual(result[0]["gust"], 34)
        self.assertEqual(result[0]["rain"], 7)  # No precipitation cross-mixing.
        self.assertEqual(result[0]["wind_gust_source"],
                         "ECMWF_SAME_CYCLE_MEDIUM_PAIR")

    def test_point_never_mixes_different_cycles_or_valid_times(self):
        old_cycle = _merge_short_medium([point(18, None)],
                                        [point(20, 34)], same_cycle=False)
        self.assertIsNone(old_cycle[0]["gust"])
        different_time = _merge_short_medium(
            [point(18, None)], [point(20, 34, when="2026-09-30T06:00:00Z")],
            same_cycle=True)
        self.assertIsNone(different_time[0]["gust"])

    def test_point_preserves_direct_short_gust_and_rejects_bad_pair(self):
        direct = _merge_short_medium([point(18, 26)], [point(20, 34)],
                                     same_cycle=True)
        self.assertEqual(direct[0]["gust"], 26)
        self.assertNotIn("wind_gust_source", direct[0])
        inconsistent = _merge_short_medium([point(18, None)],
                                           [point(30, 20)], same_cycle=True)
        self.assertIsNone(inconsistent[0]["gust"])

    def test_ecmwf_three_hour_gust_short_name_is_accepted(self):
        # ECMWF publishes requested 10fg as GRIB/ecCodes 10fg3 at +3h.
        # Previously the validator discarded perfectly real values here.
        class Client:
            def __init__(self):
                self.params = []
            def retrieve(self, **kwargs):
                self.params.append(kwargs["param"])
        client = Client()
        cycle = datetime(2026, 9, 30, tzinfo=timezone.utc)
        record = {
            "sample_kind": "POINT",
            "qc": "PASS",
            "point_id": "an_thoi",
            "lead_hours": 3,
            "variable": "10fg3",
            "value": 9.0,
            "unit": "m s**-1",
        }
        with TemporaryDirectory() as tmp, patch(
            "weather.collectors.ecmwf_72h._decode_all", return_value=[record]
        ):
            records, parameter, error = _collect_gust(
                client, Path(tmp), cycle, [0, 3], "short", ()
            )
        self.assertEqual(client.params, [["10fg"]])
        self.assertEqual(records, [record])
        self.assertEqual(parameter, "10fg")
        self.assertIsNone(error)

    def test_spatial_ecmwf_10fg3_alias_is_rendered_as_model_gust(self):
        records = [cell("10u", 3), cell("10v", 4), cell("10fg3", 10)]
        frame = _spatial_frames(records)[0]
        self.assertAlmostEqual(frame["cells"][0]["gust_kmh"], 36, places=2)

    def test_spatial_supplements_matched_cells_with_complete_vector(self):
        short = [cell("10u", 3), cell("10v", 4), cell("tp", 0.001)]
        medium = [cell("10u", 4), cell("10v", 4), cell("10fg", 10),
                  cell("tp", 0.009)]
        cycle = datetime(2026, 9, 30, tzinfo=timezone.utc)
        result = _merge_spatial(short, medium, cycle, cycle)
        row = result["frames"][0]["cells"][0]
        self.assertAlmostEqual(row["wind_kmh"], (32 ** .5) * 3.6, places=2)
        self.assertAlmostEqual(row["gust_kmh"], 36, places=2)
        self.assertAlmostEqual(row["rain_mm"], 1.0, places=2)
        self.assertEqual(row["wind_gust_source"],
                         "ECMWF_SAME_CYCLE_MEDIUM_GRID_PAIR")

    def test_spatial_rejects_different_cycle_and_unmatched_cell(self):
        short = [cell("10u", 3), cell("10v", 4)]
        medium = [cell("10u", 4), cell("10v", 4), cell("10fg", 10)]
        fresh = datetime(2026, 9, 30, 6, tzinfo=timezone.utc)
        old = datetime(2026, 9, 30, tzinfo=timezone.utc)
        out = _merge_spatial(short, medium, fresh, old)
        self.assertIsNone(out["frames"][0]["cells"][0]["gust_kmh"])
        mismatch = [cell("10u", 4, cell_id="other"),
                    cell("10v", 4, cell_id="other"),
                    cell("10fg", 10, cell_id="other")]
        out = _merge_spatial(short, mismatch, old, old)
        self.assertIsNone(out["frames"][0]["cells"][0]["gust_kmh"])


if __name__ == "__main__":
    unittest.main()
