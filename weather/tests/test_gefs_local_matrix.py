import unittest
from datetime import datetime, timezone
from weather.collectors.gefs_local_matrix import _file_member, _url, _wind_from_direction_deg, _wind_sector, _wind_exposure_factor
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

if __name__=="__main__":
    unittest.main()
