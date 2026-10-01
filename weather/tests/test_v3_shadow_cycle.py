import unittest

from weather.pipeline.run_v3_shadow_cycle import run_cycle


def radar(at, lon):
    return {
        "observed_at": at,
        "local_features": {
            "components_by_threshold": {
                "20dbz": [{
                    "component_id": "20dbz-001",
                    "centroid_lat": 10.0,
                    "centroid_lon": lon,
                    "max_dbz": 40.0,
                    "area_km2": 100.0,
                    "touches_invalid_pixels": False,
                }]
            }
        }
    }


class V3ShadowCycleTests(unittest.TestCase):
    def test_cycle_creates_pending_event_but_never_promotes(self):
        previous=radar("2026-10-01T08:00:00+00:00",103.80)
        current=radar("2026-10-01T08:10:00+00:00",103.90)
        groundtruth={
            "rainfall":{
                "status":"STALE",
                "stations":{
                    "target":{
                        "station_id":"TEST_GAUGE",
                        "data_class":"ACTUAL",
                        "observed_at":"2026-10-01T08:10:00+00:00",
                        "rain_observed":False
                    }
                }
            }
        }
        points={"points":{"target":{"lat":10.0,"lon":104.1}}}
        runtime={
            "public_ui_enabled":False,
            "production_decision_authority":"WEATHER_V2",
            "radar":{
                "tracking_threshold_dbz":20,
                "max_track_speed_kmh":120,
                "impact_radius_km":15,
                "max_nowcast_minutes":120,
                "minimum_verified_events_for_public_eta":30,
                "public_display_enabled":False,
                "rights_gate_required_before_public_promotion":True
            },
            "verification":{"anchors":{"target":"TEST_GAUGE"}}
        }
        out=run_cycle(current,previous,groundtruth,points,runtime,{})
        self.assertEqual(out["status"],"SHADOW_ONLY")
        self.assertEqual(out["production_authority"],"WEATHER_V2")
        self.assertEqual(len(out["tracking"]["tracks"]),1)
        self.assertEqual(len(out["eta_candidates"]),1)
        self.assertEqual(len(out["events"]),1)
        self.assertEqual(out["events"][0]["verification"]["status"],"PENDING")
        self.assertEqual(out["verifier_observations"],[])
        self.assertFalse(out["skill"]["promotion_ready"])

    def test_fresh_actual_can_verify_hit(self):
        previous=radar("2026-10-01T08:00:00+00:00",103.80)
        current=radar("2026-10-01T08:10:00+00:00",103.90)
        groundtruth={
            "rainfall":{
                "status":"FRESH",
                "stations":{
                    "target":{
                        "station_id":"TEST_GAUGE",
                        "data_class":"ACTUAL",
                        "observed_at":"2026-10-01T08:30:00+00:00",
                        "rain_observed":True,
                        "increment_mm":1.2,
                        "rain_intensity_mm_h":2.4
                    }
                }
            }
        }
        points={"points":{"target":{"lat":10.0,"lon":104.1}}}
        runtime={
            "public_ui_enabled":False,
            "production_decision_authority":"WEATHER_V2",
            "radar":{
                "tracking_threshold_dbz":20,
                "max_track_speed_kmh":120,
                "impact_radius_km":15,
                "max_nowcast_minutes":120,
                "minimum_verified_events_for_public_eta":30,
                "public_display_enabled":False,
                "rights_gate_required_before_public_promotion":True
            },
            "verification":{"anchors":{"target":"TEST_GAUGE"}}
        }
        out=run_cycle(current,previous,groundtruth,points,runtime,{})
        self.assertEqual(out["events"][0]["verification"]["result"],"HIT")
        self.assertEqual(out["skill"]["verified_event_count"],1)
        self.assertFalse(out["skill"]["promotion_ready"])


if __name__=="__main__":
    unittest.main()
