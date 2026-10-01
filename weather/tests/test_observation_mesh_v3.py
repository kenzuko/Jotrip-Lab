import json
import unittest
from pathlib import Path

from weather.processing.observation_mesh_v3 import (
    collapse_independence,
    load_registry,
    normalize_receipt,
    production_eligible,
    shadow_summary,
)


class ObservationMeshV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry(Path("weather/config/observation_sources_v3.json"))

    def test_existing_core_sources_are_active(self):
        self.assertTrue(production_eligible("vvpq_metar_speci", self.registry))
        self.assertTrue(production_eligible("vrain_phu_quoc", self.registry))
        self.assertTrue(production_eligible("himawari_existing", self.registry))

    def test_unresolved_new_sources_cannot_promote(self):
        self.assertFalse(production_eligible("iweather_radar_cmax", self.registry))
        self.assertFalse(production_eligible("iweather_lightning", self.registry))
        self.assertFalse(production_eligible("kttv_60018", self.registry))

    def test_null_never_becomes_zero(self):
        row = normalize_receipt({
            "source_id": "vrain_phu_quoc",
            "observed_at": "2026-10-01T06:00:00Z",
            "received_at": "2026-10-01T06:02:00Z",
            "variable": "precipitation",
            "numeric": True,
            "value": None,
        }, self.registry)
        self.assertIsNone(row["value"])

    def test_rendered_observation_stays_rendered(self):
        # Use a registry clone to exercise the rendered fallback class.
        reg = json.loads(json.dumps(self.registry))
        for source in reg["sources"]:
            if source["id"] == "iweather_radar_cmax":
                source["evidence_class"] = "REMOTE_RENDERED_OBSERVED"
                source["lifecycle"] = "SHADOW"
                break
        row = normalize_receipt({
            "source_id": "iweather_radar_cmax",
            "observed_at": "2026-10-01T06:00:00Z",
            "variable": "echo_present",
            "value": True,
            "confidence": 0.7,
        }, reg)
        self.assertTrue(row["rendered_interpretation"])
        self.assertEqual(row["source_class"], "REMOTE_RENDERED_OBSERVED")

    def test_same_backend_group_does_not_become_two_independent_votes(self):
        rows = [
            {
                "source_id": "iweather_radar_cmax",
                "independence_group": "VN_NATIONAL_RADAR_NETWORK",
            },
            {
                "source_id": "hymetnet_radar",
                "independence_group": "VN_NATIONAL_RADAR_NETWORK",
            },
        ]
        groups = collapse_independence(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups["VN_NATIONAL_RADAR_NETWORK"]), 2)

    def test_shadow_summary_keeps_weather_v2_as_authority(self):
        out = shadow_summary([
            {
                "source_id": "iweather_radar_cmax",
                "observed_at": "2026-10-01T06:00:00Z",
                "variable": "echo_present",
                "value": True,
                "qc_status": "PASS",
            }
        ], self.registry)
        self.assertEqual(out["status"], "SHADOW_ONLY")
        self.assertEqual(out["production_authority"], "WEATHER_V2_UNCHANGED")
        self.assertFalse(out["receipts"][0]["production_eligible"])


if __name__ == "__main__":
    unittest.main()
