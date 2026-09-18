import unittest
from datetime import datetime, timezone

from weather.collectors.ecmwf_72h import _merge_spatial, _spatial_frames


def rec(cell, valid, lead, variable, value, unit="m s**-1"):
    return {
        "sample_kind": "SPATIAL_GRID",
        "qc": "PASS",
        "point_id": cell,
        "valid_time": valid,
        "lead_hours": lead,
        "variable": variable,
        "value": value,
        "unit": unit,
        "sampled_lat": 10.0,
        "sampled_lon": 104.0,
        "requested_lat": 10.0,
        "requested_lon": 104.0,
    }


class SpatialFieldTests(unittest.TestCase):
    def test_ecmwf_spatial_frame_builds_vectors_and_rain_increment(self):
        records = []
        for lead, valid, tp in (
            (0, "2026-09-18T00:00:00+00:00", 0.001),
            (3, "2026-09-18T03:00:00+00:00", 0.003),
        ):
            records.extend([
                rec("grid_10.00_104.00", valid, lead, "10u", 3.0),
                rec("grid_10.00_104.00", valid, lead, "10v", 4.0),
                rec("grid_10.00_104.00", valid, lead, "2t", 301.15, "K"),
                rec("grid_10.00_104.00", valid, lead, "tp", tp, "m"),
            ])
        frames = _spatial_frames(records)
        self.assertEqual(len(frames), 2)
        first = frames[0]["cells"][0]
        second = frames[1]["cells"][0]
        self.assertAlmostEqual(first["wind_kmh"], 18.0, places=2)
        self.assertAlmostEqual(first["temperature_c"], 28.0, places=2)
        self.assertAlmostEqual(first["rain_mm"], 1.0, places=2)
        self.assertAlmostEqual(second["rain_mm"], 2.0, places=2)
        self.assertIsNotNone(first["wind_direction_deg"])

    def test_merge_never_differences_tp_across_cycles(self):
        short = [
            rec("grid_10.00_104.00", "2026-09-18T00:00:00+00:00", 0, "tp", 0.001, "m"),
            rec("grid_10.00_104.00", "2026-09-18T03:00:00+00:00", 3, "tp", 0.002, "m"),
        ]
        medium = [
            rec("grid_10.00_104.00", "2026-09-18T00:00:00+00:00", 0, "tp", 0.010, "m"),
            rec("grid_10.00_104.00", "2026-09-18T06:00:00+00:00", 6, "tp", 0.014, "m"),
        ]
        out = _merge_spatial(
            short,
            medium,
            datetime(2026, 9, 18, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 18, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(out["status"], "READY")
        self.assertEqual(len(out["frames"]), 3)
        last = out["frames"][-1]["cells"][0]
        self.assertAlmostEqual(last["rain_mm"], 4.0, places=2)
        self.assertEqual(out["display_interpolation"], "RENDER_ONLY")


if __name__ == "__main__":
    unittest.main()
