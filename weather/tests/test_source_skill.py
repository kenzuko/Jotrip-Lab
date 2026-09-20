import json
import tempfile
import unittest
from pathlib import Path

from weather.processing.source_skill import build
from weather.pipeline.archive_public_snapshot import archive


class SourceSkillTests(unittest.TestCase):
    def test_vvpq_dedupes_same_metar_and_builds_provisional_multiplier(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            raw=root/"raw"
            ana=root/"analysis"
            raw.mkdir(); ana.mkdir()

            for i,(obs,model,ens) in enumerate([
                ("2026-09-20T03:00:00+00:00",5.0,9.0),
                ("2026-09-20T04:00:00+00:00",6.0,11.0),
                ("2026-09-20T05:00:00+00:00",7.0,13.0),
            ]):
                actual=[10.0,12.0,14.0][i]
                raw_payload={
                    "atmosphere":{"vvpq":{
                        "data_class":"ACTUAL","qc":"PASS","observed_at":obs,
                        "age_minutes":5,"wind_speed_kmh":actual,"temperature_c":29,
                    }},
                    "rainfall":{"stations":{}},
                }
                ana_payload={
                    "points":{"duong_dong":{
                        "wind":{
                            "anchor_model_proxy_kmh":model,
                            "ensemble_context":{"q50_kmh":ens},
                        },
                        "temperature":{"anchor_model_proxy":28},
                    }}
                }
                name=f"0{i}0000.json"
                (raw/name).write_text(json.dumps(raw_payload),encoding="utf-8")
                (ana/name).write_text(json.dumps(ana_payload),encoding="utf-8")

            out=build(raw,ana)
            self.assertEqual(out["vvpq"]["unique_actual_samples"],3)
            self.assertEqual(out["vvpq"]["wind"]["status"],"PROVISIONAL")
            self.assertGreater(out["vvpq"]["wind"]["ensemble_gain_multiplier"],1.0)

    def test_public_archive_keeps_one_row_per_30_minute_bucket(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            base={
                "groundtruth":{"atmosphere":{"vvpq":{}},"rainfall":{"stations":{}}},
                "local_now":{
                    "engine":"PQ_LOCAL_NOW_V2",
                    "points":{"duong_dong":{
                        "temperature_c":29,"wind_kmh":10,
                        "wind":{"method":"m","confidence":0.6},
                        "rain":{"rain_rate_mm_h":0.2,"method":"r","confidence":0.5,"convective_score":70},
                        "wave_hs_m":0.3,
                    }},
                },
            }
            p1={**base,"generated_at":"2026-09-20T05:01:00+00:00"}
            p2={**base,"generated_at":"2026-09-20T05:11:00+00:00"}
            archive(p1,root,30)
            archive(p2,root,30)
            lines=(root/"2026-09-20.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines),1)
            self.assertIn("12:00:00+07:00",json.loads(lines[0])["bucket_local"])


if __name__=="__main__":
    unittest.main()
