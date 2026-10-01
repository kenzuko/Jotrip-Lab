import unittest

from weather.processing.radar_motion_v3 import match_components, eta_candidates
from weather.processing.event_skill_v3 import build_events, verify_event, skill_summary


def receipt(at, lon):
    return {
        "observed_at": at,
        "local_features": {
            "components_by_threshold": {
                "20dbz": [{
                    "component_id": "20dbz-001",
                    "centroid_lat": 10.0,
                    "centroid_lon": lon,
                    "max_dbz": 38.0,
                    "area_km2": 120.0,
                    "touches_invalid_pixels": False,
                }]
            }
        },
    }


class RadarMotionV3Tests(unittest.TestCase):
    def test_two_frame_track_and_eta_candidate(self):
        previous = receipt("2026-10-01T08:00:00+00:00", 103.8)
        current = receipt("2026-10-01T08:10:00+00:00", 103.9)
        tracking = match_components(previous, current, threshold_dbz=20)
        self.assertEqual(tracking["status"], "TRACKS_READY")
        self.assertEqual(len(tracking["tracks"]), 1)
        track = tracking["tracks"][0]
        self.assertGreater(track["speed_kmh"], 50)
        self.assertLess(track["speed_kmh"], 80)
        self.assertEqual(track["heading"], "Đông")
        eta = eta_candidates(
            tracking,
            {"target": {"lat": 10.0, "lon": 104.1}},
            impact_radius_km=15,
            max_nowcast_minutes=120,
        )
        self.assertEqual(len(eta), 1)
        self.assertEqual(eta[0]["point_id"], "target")
        self.assertEqual(eta[0]["window"], "0_30_MIN")
        self.assertFalse(eta[0]["public_usable"])

    def test_invalid_time_pair_fails_closed(self):
        previous = receipt("2026-10-01T08:10:00+00:00", 103.8)
        current = receipt("2026-10-01T08:00:00+00:00", 103.9)
        self.assertEqual(match_components(previous, current)["status"], "NO_VALID_TIME_PAIR")


class EventSkillV3Tests(unittest.TestCase):
    def _event(self):
        candidates = [{
            "track_id": "20dbz-001-001",
            "point_id": "cua_can",
            "eta_minutes": 20,
            "window": "0_30_MIN",
            "closest_approach_km": 4.0,
            "max_dbz_current": 38.0,
            "confidence": "LOW_TWO_FRAME_SHADOW",
            "touches_invalid_pixels": False,
        }]
        return build_events(
            issued_at="2026-10-01T08:00:00+00:00",
            eta_candidates=candidates,
            verifier_by_point={"cua_can": "VRAIN_CUA_CAN"},
        )[0]

    def test_hit_requires_fresh_actual(self):
        event = self._event()
        observations = [
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:10:00+00:00", "rain_observed": False, "freshness": "FRESH"},
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:22:00+00:00", "rain_observed": True, "freshness": "FRESH"},
        ]
        verified = verify_event(event, observations)
        self.assertEqual(verified["verification"]["result"], "HIT")
        self.assertEqual(verified["verification"]["timing_error_minutes"], 2.0)

    def test_stale_actual_never_becomes_no_rain(self):
        event = self._event()
        observations = [
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:05:00+00:00", "rain_observed": False, "freshness": "STALE"},
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:35:00+00:00", "rain_observed": False, "freshness": "STALE"},
        ]
        verified = verify_event(event, observations)
        self.assertIsNone(verified["verification"]["result"])
        self.assertEqual(verified["verification"]["status"], "INSUFFICIENT_ACTUAL_COVERAGE")

    def test_false_alarm_requires_window_coverage(self):
        event = self._event()
        observations = [
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:05:00+00:00", "rain_observed": False, "freshness": "FRESH"},
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:15:00+00:00", "rain_observed": False, "freshness": "FRESH"},
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:25:00+00:00", "rain_observed": False, "freshness": "FRESH"},
            {"anchor_id": "VRAIN_CUA_CAN", "observed_at": "2026-10-01T08:35:00+00:00", "rain_observed": False, "freshness": "FRESH"},
        ]
        verified = verify_event(event, observations)
        self.assertEqual(verified["verification"]["result"], "FALSE_ALARM")
        summary = skill_summary([verified])
        self.assertEqual(summary["verified_event_count"], 1)
        self.assertEqual(summary["false_alarm_count"], 1)
        self.assertFalse(summary["promotion_ready"])


if __name__ == "__main__":
    unittest.main()
