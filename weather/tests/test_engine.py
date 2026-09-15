from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from weather.collectors.catalog import default_manifests, latest_completed_cycle
from weather.collectors.copernicus import configuration_status
from weather.collectors.official_bulletin import parse_official_bulletin, validity_status
from weather.collectors.port_status import normalize_port_evidence
from weather.collectors.probe import probe_source
from weather.pipeline.build_snapshot import build_snapshot
from weather.pipeline.decision_features import build_decision_features
from weather.processing.decision import decide_product
from weather.processing.drift import compare_run_series, compare_runs
from weather.processing.ensemble import summarize_members
from weather.processing.geometry import sample_route
from weather.processing.marine import current_from_uv, speed_mps_to_kmh, summarize_route
from weather.processing.quality import assert_numeric_source, completeness, critical_gaps, numeric_weight
from weather.processing.readiness import decision_eligible, derive_data_mode
from weather.processing.rainfall import cumulative_to_increment, ensemble_rain_probability, rolling_accumulation
from weather.processing.route import summarize_route_timeseries
from weather.processing.snapshot import verify_snapshot
from weather.processing.units import add_speed_display, speed_to_kmh
from weather.processing.operational_probability import operational_window_probability
from weather.processing.outlook import daily_ensemble_outlook
from weather.processing.window import detect_windows
from weather.storage import WeatherStore

ROOT = Path(__file__).resolve().parents[1]


class QualityTests(unittest.TestCase):
    def test_no_news_numerics(self):
        self.assertEqual(numeric_weight("NEWS"), 0)
        with self.assertRaises(ValueError):
            assert_numeric_source("CONSUMER_AGGREGATOR")
        assert_numeric_source("ECMWF_DIRECT")

    def test_weighted_completeness_and_critical_gap(self):
        products = json.loads((ROOT / "config/products.json").read_text(encoding="utf-8"))
        availability = {"restriction": 1, "hs": 1, "gust": 1, "convection": 1, "visibility": 0, "wave_direction": .75, "wave_period": .5, "local_truth": .9}
        score = completeness(products["cano_south"], availability)
        self.assertGreater(score, 75)
        self.assertIn("visibility", critical_gaps(products["cano_south"], availability))


class SourceFailoverTests(unittest.TestCase):
    @patch("weather.collectors.probe.probe_url")
    def test_primary_timeout_uses_official_mirror(self, mocked):
        mocked.side_effect = [
            {"status": "RETRIEVAL_FAILED", "checked_at": "t1", "error": "timeout"},
            {"status": "REACHABLE", "checked_at": "t2", "http_status": 200},
        ]
        result = probe_source({"endpoints": [
            {"name": "primary", "url": "https://primary.invalid"},
            {"name": "official_mirror", "url": "https://mirror.invalid"},
        ]})
        self.assertEqual(result["status"], "REACHABLE")
        self.assertEqual(result["selected_endpoint"], "official_mirror")
        self.assertEqual(result["fallback_level"], 1)
        self.assertEqual(len(result["attempts"]), 2)


class OfficialEvidenceTests(unittest.TestCase):
    def test_an_thoi_bulletin_is_parsed_as_forecast_not_actual(self):
        text = "Gió Tây đến Tây Nam cấp 3-4. Độ cao sóng: 0,50 - 1,25m. Tầm nhìn xa trên 10km."
        event = parse_official_bulletin(text, source="AN_THOI_OFFICIAL",
                                        issue_time="2026-09-14T05:00:00+07:00",
                                        valid_from="2026-09-14T07:00:00+07:00",
                                        valid_to="2026-09-15T07:00:00+07:00", scope="AN_THOI_35KM")
        self.assertEqual(event["parsed_payload"]["wind_beaufort"], [3, 4])
        self.assertEqual(event["parsed_payload"]["wave_height_m"], [.5, 1.25])
        self.assertFalse(event["is_observation"])
        now = datetime.fromisoformat("2026-09-14T12:00:00+07:00")
        self.assertEqual(validity_status(event, now), "ACTIVE_VALID")

    def test_departure_permit_is_trip_operational_evidence(self):
        event = normalize_port_evidence(source="PORT", observed_time="2026-09-15T06:00:00+07:00",
                                        scope="HT_PQ_TRIP_0600", evidence_type="DEPARTURE_PERMIT",
                                        trip_status="DEPARTED")
        self.assertEqual(event["status"], "DEPARTED")


class ReadinessTests(unittest.TestCase):
    def test_http_reachable_is_not_decision_eligible(self):
        self.assertFalse(decision_eligible({"status": "REACHABLE", "qc": "PASS"}))

    def test_mode_a_requires_extracted_marine_ensemble_and_route(self):
        sources = {
            "ECMWF": {"readiness": "POINT_ROUTE_EXTRACTED", "qc": "PASS"},
            "GEFS_WAVE": {"readiness": "MEMBER_COMPLETE", "qc": "PASS"},
        }
        points = {"point_coverage": ["duong_dong", "an_thoi", "ganh_dau"]}
        self.assertEqual(derive_data_mode(sources, points), "A")

    def test_unverified_route_cannot_unlock_mode_a(self):
        sources = {"ECMWF": {"readiness": "POINT_ROUTE_EXTRACTED", "qc": "PASS"},
                   "GEFS_WAVE": {"readiness": "MEMBER_COMPLETE", "qc": "PASS"}}
        route = {"spatial_mode": "ROUTE", "routes": {"r": {"production_eligible": False, "qc": "PASS"}}}
        self.assertEqual(derive_data_mode(sources, route), "B")

    def test_copernicus_missing_credentials_is_explicit(self):
        with patch.dict("os.environ", {}, clear=True):
            result = configuration_status()
        self.assertEqual(result["status"], "AUTH_OR_CONFIG_REQUIRED")
        self.assertIn("COPERNICUSMARINE_SERVICE_USERNAME", result["missing"])


class EnsembleTests(unittest.TestCase):
    def test_member_gate(self):
        self.assertEqual(summarize_members(list(range(7)), 10)["status"], "NOT_ELIGIBLE")
        partial = summarize_members(list(range(8)), 10, threshold=5)
        self.assertEqual(partial["status"], "PARTIAL_ENSEMBLE")
        self.assertAlmostEqual(partial["exceedance_probability"], .25)


class MarineTests(unittest.TestCase):
    def test_operational_speed_unit_is_kmh(self):
        self.assertEqual(speed_mps_to_kmh(10), 36.0)

    def test_current_vector_convention(self):
        self.assertEqual(current_from_uv(1, 0)["direction_toward_deg"], 90.0)
        self.assertEqual(current_from_uv(1, 0)["speed_kmh"], 3.6)

    def test_land_grid_rejected(self):
        samples = [
            {"segment_id": "land", "hs_m": 9, "gust_mps": 30, "sea_land_status": "LAND", "qc": "REJECTED_LAND_GRID", "sampled_coordinate": [104, 10]},
            {"segment_id": "sea-1", "hs_m": 1.1, "gust_mps": 8, "sea_land_status": "SEA", "qc": "PASS", "sampled_coordinate": [104.1, 9.9]},
            {"segment_id": "sea-2", "hs_m": 1.3, "gust_mps": 9, "sea_land_status": "SEA", "qc": "PASS", "sampled_coordinate": [104.2, 9.8]}
        ]
        result = summarize_route(samples)
        self.assertEqual(result["route_max_hs_m"], 1.3)
        self.assertEqual(result["max_gust_kmh"], 32.4)
        self.assertEqual(result["worst_segment"], "sea-2")


class UnitPolicyTests(unittest.TestCase):
    def test_mps_and_knots_convert_to_kmh(self):
        self.assertEqual(speed_to_kmh(10, "m/s"), 36.0)
        self.assertEqual(speed_to_kmh(10, "kt"), 18.52)

    def test_raw_value_is_preserved(self):
        record = add_speed_display({"value": 10, "unit": "m s**-1"})
        self.assertEqual(record["value"], 10)
        self.assertEqual(record["unit"], "m s**-1")
        self.assertEqual(record["display_value"], 36.0)
        self.assertEqual(record["display_unit"], "km/h")


class RainfallTests(unittest.TestCase):
    def test_cumulative_rain_and_rolling_window(self):
        records = [
            {"valid_time": "03", "lead_hours": 3, "value_mm": 1},
            {"valid_time": "06", "lead_hours": 6, "value_mm": 4},
            {"valid_time": "09", "lead_hours": 9, "value_mm": 6},
        ]
        increments = cumulative_to_increment(records)
        self.assertEqual([r["rain_increment_mm"] for r in increments], [1, 3, 2])
        self.assertEqual(rolling_accumulation(increments, 6)[-1]["rain_6h_mm"], 5)

    def test_member_rain_probability(self):
        records = [{"member": i, "rain_increment_mm": value} for i, value in enumerate([1, 4, 8, 12])]
        result = ensemble_rain_probability(records, 5, expected_members=4)
        self.assertEqual(result["probability"], .5)


class RouteTimeSeriesTests(unittest.TestCase):
    def test_route_summary_uses_only_route_sea_samples(self):
        rows = [
            {"valid_time": "t1", "segment_id": "a", "hs_m": 1.0, "gust_kmh": 25,
             "wave_direction_deg": 180, "heading_deg": 180, "duration_minutes": 20,
             "sea_land_status": "SEA", "qc": "PASS"},
            {"valid_time": "t1", "segment_id": "b", "hs_m": 1.4, "gust_kmh": 35,
             "wave_direction_deg": 270, "heading_deg": 180, "duration_minutes": 25,
             "sea_land_status": "SEA", "qc": "PASS"},
        ]
        result = summarize_route_timeseries(rows)[0]
        self.assertEqual(result["route_max_hs_m"], 1.4)
        self.assertEqual(result["route_max_gust_kmh"], 35)
        self.assertEqual(result["exposure_duration_minutes"], 45)

    def test_route_sampling_respects_native_grid(self):
        points = [[104.0, 10.0], [104.1, 10.0]]
        samples = sample_route(points, native_grid_km=25, maximum_spacing_km=5)
        self.assertGreaterEqual(len(samples), 3)
        self.assertTrue(all(row["effective_spacing_km"] <= 5 for row in samples))


class OperationalWindowTests(unittest.TestCase):
    def test_coherent_member_probability(self):
        rows = []
        for member, gust in ((0, 30), (1, 45), (2, 25), (3, 20)):
            rows += [{"member": member, "variable": "gust_kmh", "value": gust},
                     {"member": member, "variable": "hs_m", "value": 1.0}]
        result = operational_window_probability(rows, {"gust_kmh": 40, "hs_m": 1.5}, expected_members=4)
        self.assertEqual(result["p_operational_window"], .75)

    def test_window_merge_and_missing_gate(self):
        thresholds = {"gust_kmh": {"watch": 30, "avoid": 45}}
        rows = [
            {"start_time": "05", "end_time": "06", "gust_kmh": 20},
            {"start_time": "06", "end_time": "07", "gust_kmh": 25},
            {"start_time": "07", "end_time": "08", "gust_kmh": 35},
            {"start_time": "08", "end_time": "09", "gust_kmh": None},
        ]
        windows = detect_windows(rows, thresholds, ["gust_kmh"])
        self.assertEqual(windows[0]["window_class"], "BEST")
        self.assertEqual(windows[0]["end_time"], "07")
        self.assertEqual(windows[-1]["window_class"], "UNRESOLVED")

    def test_missing_changes_confidence_not_weather_hazard(self):
        result = decide_product(restriction="OPEN", windows=[{"window_class": "BEST"}],
                                critical_missing=["visibility"])
        self.assertEqual(result["decision"], "HOLD_WATCH")
        self.assertEqual(result["reason"], "CRITICAL_UNCERTAINTY")

    def test_d4_d14_output_is_planning_only(self):
        rows = [{"date": "D4", "variable": "gust_kmh", "value": i} for i in range(31)]
        result = daily_ensemble_outlook(rows)[0]
        self.assertEqual(result["status"], "PLANNING_ONLY")
        self.assertNotIn("decision", result)


class DriftTests(unittest.TestCase):
    def test_pushback_only_comparable_runs(self):
        base = {"model": "GEFS", "system": "ens", "variable": "hs", "location_id": "route", "valid_window": "D1_AM", "extraction_method": "route_v1", "value": 1.8, "onset_hour": 6}
        current = dict(base, value=1.2, onset_hour=18)
        self.assertEqual(compare_runs(base, current)["trend"], "RECEDING")
        self.assertEqual(compare_runs(base, dict(current, model="ECMWF"))["status"], "NOT_COMPARABLE")

    def test_repeated_improvement_is_forecast_reversal(self):
        base = {"model": "GEFS", "system": "ens", "variable": "hs", "location_id": "route",
                "valid_window": "D1_AM", "extraction_method": "route_v1", "stable_tolerance": .1}
        runs = [dict(base, value=value, onset_hour=hour) for value, hour in
                ((2.0, 6), (1.7, 9), (1.3, 15), (1.0, 21))]
        self.assertEqual(compare_run_series(runs)["trend"], "FORECAST_REVERSAL_IMPROVING")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_sealed_and_archived(self):
        fixture = json.loads((ROOT / "tests/fixtures/an_thoi_2026_09_14.json").read_text(encoding="utf-8"))
        health = {"ECMWF_DIRECT": {"status": "REACHABLE"}, "NOAA_GEFS_DIRECT": {"status": "RETRIEVAL_FAILED"}}
        snapshot = build_snapshot(fixture, datetime(2026, 9, 14, 22, 45, tzinfo=timezone.utc), health)
        self.assertTrue(verify_snapshot(snapshot))
        self.assertEqual(snapshot["points"]["an_thoi"]["base_state"]["sea_state"], "NORMAL")
        self.assertEqual(snapshot["points"]["an_thoi"]["decision"], "GO_WITH_WATCH")
        with tempfile.TemporaryDirectory() as folder:
            store = WeatherStore(Path(folder) / "weather.db")
            store.save_snapshot(snapshot)
            self.assertEqual(store.get_snapshot(snapshot["snapshot_id"])["payload_hash"], snapshot["payload_hash"])
            store.close()

    def test_manifest_has_direct_provenance_and_bbox(self):
        manifests = default_manifests(datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
        self.assertTrue(all(m["provenance"] == "DIRECT" for m in manifests))
        self.assertTrue(all(len(m["bounding_box"]) == 4 for m in manifests))

    def test_latest_completed_run_never_future(self):
        now = datetime(2026, 9, 15, 2, tzinfo=timezone.utc)
        run = latest_completed_cycle(now, (0, 6, 12, 18), 6)
        self.assertLess(run, now)

    def test_end_to_end_features_are_reproducible(self):
        payload = json.loads((ROOT / "tests/fixtures/end_to_end_decision.json").read_text(encoding="utf-8"))
        first = build_decision_features(payload)
        second = build_decision_features(payload)
        self.assertEqual(first, second)
        self.assertEqual(first["decision"]["decision"], "GO_WITH_WATCH")
        self.assertEqual(first["operational_probability"]["p_operational_window"], .75)
        self.assertEqual(first["route"][0]["worst_segment"], "s2")


if __name__ == "__main__":
    unittest.main()
