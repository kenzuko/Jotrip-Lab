import unittest
from datetime import datetime, timezone
from weather.collectors.gefs_local_matrix import _file_member, _url
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

if __name__=="__main__":
    unittest.main()
