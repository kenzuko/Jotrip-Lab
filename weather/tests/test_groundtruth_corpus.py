import unittest
from pathlib import Path

from weather.processing.groundtruth_corpus import build_corpus


class GroundTruthCorpusTests(unittest.TestCase):
    def test_verified_research_corpus_is_part_of_data_plane_with_tiers(self):
        root=Path(__file__).resolve().parents[1]
        payload=build_corpus(
            root/"groundtruth/corpus/observations_seed_v6.csv",
            root/"config/groundtruth_sources.json",
        )
        self.assertGreaterEqual(payload["record_count"],28)
        self.assertGreaterEqual(payload["counts_by_class"].get("RAW_OBS",0),1)
        self.assertGreaterEqual(payload["counts_by_class"].get("OFFICIAL_AGGREGATE_OBS",0),1)
        self.assertGreaterEqual(len(payload["source_registry"]["sources"]),15)
        roles={r["production_role"] for r in payload["records"]}
        self.assertIn("VERIFICATION_ACTUAL",roles)
        self.assertIn("WINDOWED_HISTORICAL_VERIFICATION",roles)
        self.assertTrue(payload["policy"]["current_time_actual_requires_live_timestamped_stream"])
        self.assertFalse(payload["policy"]["model_or_satellite_is_groundtruth"])

    def test_identifier_collision_lock_is_present(self):
        root=Path(__file__).resolve().parents[1]
        payload=build_corpus(
            root/"groundtruth/corpus/observations_seed_v6.csv",
            root/"config/groundtruth_sources.json",
        )
        self.assertEqual(
            payload["policy"]["identifier_collision_guard"],
            "namespace+identifier+station_epoch+timestamp",
        )
        sources={s["id"]:s for s in payload["source_registry"]["sources"]}
        self.assertEqual(sources["wmo_48917_synop"]["namespace"],"WMO_INDEX")
        self.assertEqual(sources["vvpq_metar_speci"]["namespace"],"ICAO")
        self.assertNotEqual(sources["wmo_48917_synop"]["namespace"],sources["vvpq_metar_speci"]["namespace"])

        wmo=sources["wmo_48917_synop"]
        self.assertEqual(wmo["status"],"ACTIVE_NEAR_REALTIME")
        self.assertEqual(wmo["station_identity_status"],"RESOLVED_WMO_OSCAR")
        self.assertEqual(wmo["independence_from_vvpq"],"CONFIRMED_INDEPENDENT_PHYSICAL_SITE")
        self.assertEqual(wmo["evidence_weight_for_independent_source_count"],1)
        self.assertAlmostEqual(wmo["current_coordinates"]["lat"],10.2166666667)
        self.assertAlmostEqual(wmo["current_coordinates"]["lon"],103.9666666667)
        synop_rows=[
            r for r in payload["records"]
            if str(r.get("station_id") or "")=="48917" and "SYNOP" in str(r.get("source") or "").upper()
        ]
        self.assertTrue(synop_rows)
        self.assertTrue(all(r["production_role"]=="INDEPENDENT_GROUND_OBSERVATION_CROSSCHECK" for r in synop_rows))
        self.assertTrue(all(r["evidence_weight_for_independent_source_count"]==1 for r in synop_rows))


if __name__=="__main__":
    unittest.main()
