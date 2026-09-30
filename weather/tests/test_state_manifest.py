import unittest

from weather.pipeline.build_state_manifest import build


class WeatherStateManifestTests(unittest.TestCase):
    def test_source_times_remain_independent(self):
        dashboard={
            "snapshot_id":"PQWX_TEST",
            "generated_at":"2026-09-30T07:30:00+00:00",
            "source_cycles":{"ECMWF":"2026-09-30T00:00:00+00:00","GEFS":"2026-09-30T00:00:00+00:00"},
        }
        ground={
            "generated_at":"2026-09-30T07:31:00+00:00",
            "atmosphere":{"vvpq":{"observed_at":"2026-09-30T07:00:00+00:00"}},
            "rainfall":{"stations":{
                "an_thoi":{"observed_at":"2026-09-30T07:12:00+00:00","last_checked_at":"2026-09-30T07:31:00+00:00"},
                "cua_can":{"observed_at":"2026-09-30T06:55:00+00:00","last_checked_at":"2026-09-30T07:31:00+00:00"},
            }},
        }
        local={"generated_at":"2026-09-30T07:32:00+00:00"}
        nowcast={
            "sampled_time":"2026-09-30T07:20:00+00:00",
            "generated_at":"2026-09-30T07:33:00+00:00",
            "latest_object":"AHI-L2-FLDK-Clouds/x/AHI-CHGT_x.nc",
        }
        ensemble={"run_time":"2026-09-30T00:00:00+00:00","generated_at":"2026-09-30T07:10:00+00:00"}
        out=build(dashboard,ground,local,nowcast,ensemble)
        self.assertEqual(out["snapshot_id"],"PQWX_TEST")
        self.assertEqual(out["sources"]["groundtruth"]["vvpq_observed_at"],"2026-09-30T07:00:00+00:00")
        self.assertEqual(out["sources"]["groundtruth"]["vrain_latest_observed_at"],"2026-09-30T07:12:00+00:00")
        self.assertEqual(out["sources"]["groundtruth"]["vrain_latest_checked_at"],"2026-09-30T07:31:00+00:00")
        self.assertEqual(out["sources"]["nowcast"]["source_id"],"AHI-L2-FLDK-Clouds/x/AHI-CHGT_x.nc")
        self.assertEqual(out["updated_at"],"2026-09-30T07:33:00+00:00")
        self.assertTrue(out["policy"]["fetch_time_is_not_observation_time"])


if __name__=="__main__":
    unittest.main()
