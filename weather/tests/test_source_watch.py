import unittest
from unittest.mock import patch

from weather.collectors import source_watch


class SourceWatchTests(unittest.TestCase):
    def setUp(self):
        self.awc = [{
            "icaoId":"VVPQ","obsTime":1789689600,"rawOb":"METAR VVPQ 180000Z 30005KT 9000 SCT015 27/25 Q1011",
            "temp":27,"dewp":25,"wdir":300,"wspd":5
        }]
        self.vrain = [
            {"sn":"An Thới","lt":10.018482,"lg":104.0149,"d":0.0,"l":"Không mưa"},
            {"sn":"Cửa Cạn","lt":10.292693,"lg":103.914799,"d":0.0,"l":"Không mưa"},
        ]
        v_sig=source_watch._vvpq_signature(self.awc)
        r_sig=source_watch._vrain_signatures(self.vrain)
        self.previous_gt={
            "atmosphere":{"vvpq":{
                "observed_at":"2026-09-18T00:00:00+00:00",
                "raw_payload_hash":v_sig["raw_payload_hash"],
                "raw_observation":v_sig["raw_observation"],
            }},
            "rainfall":{"stations":{
                key:{
                    "raw_payload_hash":value["raw_payload_hash"],
                    "accumulation_mm":value["accumulation_mm"],
                } for key,value in r_sig.items()
            }}
        }
        self.previous_nowcast={"latest_object":"AHI-L2-FLDK-Clouds/old/AHI-CHGT_old.nc"}

    def _run(self,awc=None,vrain=None,himawari=None):
        awc=self.awc if awc is None else awc
        vrain=self.vrain if vrain is None else vrain
        himawari=himawari or {"key":"AHI-L2-FLDK-Clouds/old/AHI-CHGT_old.nc","last_modified":"2026-09-18T00:00:00Z"}
        def fake_json(url):
            if "aviationweather" in url:
                return awc
            return vrain
        with patch.object(source_watch,"_fetch_json",side_effect=fake_json), \
             patch.object(source_watch,"_latest_himawari_object",return_value=himawari):
            return source_watch.watch(self.previous_gt,self.previous_nowcast)

    def test_unchanged_sources_do_not_trigger_heavy_processors(self):
        out=self._run()
        self.assertFalse(out["groundtruth_changed"])
        self.assertFalse(out["himawari_changed"])
        self.assertEqual(out["status"],"PASS")

    def test_new_vvpq_observation_triggers_groundtruth(self):
        awc=[{**self.awc[0],"obsTime":1789691400,"rawOb":"METAR VVPQ 180030Z 28008KT 9000 SCT015 28/25 Q1011"}]
        out=self._run(awc=awc)
        self.assertTrue(out["vvpq_changed"])
        self.assertTrue(out["groundtruth_changed"])

    def test_changed_vrain_row_triggers_groundtruth(self):
        vrain=[{**self.vrain[0],"d":0.4,"l":"Mưa nhẹ"},self.vrain[1]]
        out=self._run(vrain=vrain)
        self.assertTrue(out["vrain_changed"])
        self.assertTrue(out["groundtruth_changed"])

    def test_new_himawari_object_triggers_nowcast_only(self):
        out=self._run(himawari={
            "key":"AHI-L2-FLDK-Clouds/new/AHI-CHGT_new.nc",
            "last_modified":"2026-09-18T00:10:00Z",
        })
        self.assertTrue(out["himawari_changed"])
        self.assertFalse(out["groundtruth_changed"])


if __name__=="__main__":
    unittest.main()
