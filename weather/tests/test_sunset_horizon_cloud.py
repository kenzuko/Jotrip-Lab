import unittest

from weather.collectors.himawari_nowcast import _horizon_cloud_for_target, _sunset_azimuth_deg


TARGET_LAT = 10.2172
TARGET_LON = 103.9593


def west_cells(cloud_fraction: float, height_m: float = 1800.0):
    cells = []
    # Dense synthetic line-of-sight samples over the Gulf, centered on the
    # westward sunset bearing. Longitudes span roughly 20-90 km offshore.
    for i, lon in enumerate([103.78, 103.70, 103.62, 103.54, 103.46, 103.38, 103.30, 103.22]):
        cells.append({
            "lat": TARGET_LAT + (i % 3 - 1) * 0.008,
            "lon": lon,
            "cloud_fraction": cloud_fraction,
            "cloud_top_median_m": height_m,
        })
    return cells


class SunsetHorizonCloudTests(unittest.TestCase):
    def test_sunset_azimuth_is_westward_for_phu_quoc(self):
        az = _sunset_azimuth_deg("2026-09-29T10:00:00Z", TARGET_LAT)
        self.assertGreater(az, 250)
        self.assertLess(az, 285)

    def test_dense_horizon_cloud_is_flagged_and_trending_up(self):
        spatial = {
            "frames": [
                {"sampled_time": "2026-09-29T09:30:00Z", "cells": west_cells(0.25)},
                {"sampled_time": "2026-09-29T09:50:00Z", "cells": west_cells(0.92)},
            ]
        }
        out = _horizon_cloud_for_target(spatial, TARGET_LAT, TARGET_LON)
        self.assertEqual(out["status"], "LIKELY_OBSCURED")
        self.assertGreaterEqual(out["obscuration_score"], 70)
        self.assertEqual(out["trend"], "INCREASING")
        self.assertEqual(out["dominant_layer"], "LOW")
        self.assertIn(out["confidence"], {"MEDIUM", "HIGH"})
        self.assertEqual(out["method"], "HIMAWARI_SUNSET_HORIZON_OCCUPANCY_V1_NOT_OPTICAL_DEPTH")

    def test_sparse_horizon_cloud_stays_clear(self):
        spatial = {
            "frames": [
                {"sampled_time": "2026-09-29T09:30:00Z", "cells": west_cells(0.06)},
                {"sampled_time": "2026-09-29T09:50:00Z", "cells": west_cells(0.08)},
            ]
        }
        out = _horizon_cloud_for_target(spatial, TARGET_LAT, TARGET_LON)
        self.assertEqual(out["status"], "CLEAR")
        self.assertLess(out["obscuration_score"], 20)
        self.assertEqual(out["trend"], "STABLE")


if __name__ == "__main__":
    unittest.main()
