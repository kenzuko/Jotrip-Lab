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
        synop=sources["wmo_48917_synop"]
        self.assertEqual(synop["identity_status"],"INDEPENDENT_FROM_CURRENT_VVPQ")
        self.assertEqual(synop["identity_confidence"],"HIGH")
        self.assertEqual(synop["status"],"ACTIVE_NEAR_REALTIME")
        self.assertEqual(synop["role"],"ACTIVE_NEAR_REALTIME_GROUND_OBSERVATION")
        self.assertEqual(synop["coordinates"]["lat"],10.22)
        self.assertEqual(synop["coordinates"]["lon"],103.97)
        self.assertEqual(synop["current_vvpq_coordinates"]["lat"],10.169722)
        self.assertEqual(synop["current_vvpq_coordinates"]["lon"],103.993056)
        self.assertEqual(synop["relocation_history"]["status"],"NO_VERIFIED_POST_2012_RELOCATION_FOUND")
        self.assertEqual(synop["identity_conflict"]["status"],"THIRD_PARTY_CROSS_ID_CONFLICT")


if __name__=="__main__":
    unittest.main()
