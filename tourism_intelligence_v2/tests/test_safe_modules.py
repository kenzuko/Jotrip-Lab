from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tourism_intelligence_v2.collectors.airfare.collector import parse_vietnam_airlines
from tourism_intelligence_v2.collectors.airfare.processor import summarize as airfare_summary
from tourism_intelligence_v2.collectors.hotel_forward.processor import summarize as hotel_summary
from tourism_intelligence_v2.collectors.marine_ops.collector import parse_port_clearance_html, parse_thanh_thoi_html
from tourism_intelligence_v2.readiness import build as build_readiness
from tourism_intelligence_v2.registry import freshness, load_registry

ROOT = Path(__file__).resolve().parents[2]
VN = ZoneInfo("Asia/Ho_Chi_Minh")


class SafeModuleTests(unittest.TestCase):
    def test_registry(self):
        registry = load_registry(ROOT / "config/tourism_v2/source-registry.v1.json")
        self.assertGreaterEqual(len(registry["sources"]), 11)
        self.assertFalse(any(source.get("paid") for source in registry["sources"]))

    def test_freshness_formula(self):
        item = freshness(30, 60)
        self.assertEqual(item["state"], "FRESH")
        self.assertGreater(item["score"], 0.6)

    def test_marine_port_parser_strict_d0(self):
        html = """<table><tr><td>1</td><td>5000.2026/KGG.HT</td><td>SUPERDONG III</td><td>9622277</td><td>XVRH</td><td>16/09/2026 05:10</td><td>CANG HA TIEN KG</td><td>View</td></tr><tr><td>2</td><td>5001.2026/KGG.HT</td><td>THRIVING 7</td><td>9840403</td><td>3WAR7</td><td>15/09/2026 05:20</td><td>CANG THACH THOI KG</td><td>View</td></tr></table>"""
        rows = parse_port_clearance_html(html, "16/09/2026")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "fast_boat")

    def test_thanh_thoi_strict_date(self):
        html = "<html><body>Lịch Phà Chạy (Ngày: 16/9/2026) Phú Quốc - Hà Tiên (Đã xuất bến) Thriving 8</body></html>"
        rows = parse_thanh_thoi_html(html, "16/09/2026")
        self.assertEqual(rows[0]["category"], "ferry")
        self.assertEqual(parse_thanh_thoi_html(html, "15/09/2026"), [])

    def test_hotel_gate_blocks_low_coverage(self):
        result = hotel_summary([{"hotel_id": "a", "available": True, "rate_all_in_vnd": 100}], {"a", "b", "c"})
        self.assertEqual(result["state"], "INSUFFICIENT_COVERAGE")
        self.assertIsNone(result["forward_compression"])

    def test_airfare_gate_blocks_low_coverage(self):
        result = airfare_summary([{"route": "SGN-PQC", "total_vnd": 1000000}], {"SGN-PQC", "HAN-PQC"}, threshold=0.65)
        self.assertEqual(result["state"], "INSUFFICIENT_COVERAGE")
        self.assertIsNone(result["airfare_pressure"])

    def test_public_airfare_fallback_is_never_fixed_basket(self):
        config = json.loads((ROOT / "config/tourism_v2/airfare-sources.v1.json").read_text(encoding="utf-8"))
        self.assertFalse(config["fixed_basket_compatible"])
        self.assertTrue(config["rules"]["never_emit_airfare_pressure_from_fallback_only"])
        self.assertTrue(all(not item["fixed_basket_compatible"] for item in config["sources"]))

    def test_vietnam_airlines_parser(self):
        text = "Hanoi (HAN) to Phu Quoc (PQC) One-way/Economy Depart: 28/09/2026 From 988.181 VND Viewed 6 hours ago"
        rows = parse_vietnam_airlines(text, "HAN-PQC")
        self.assertEqual(rows[0]["currency"], "VND")
        self.assertEqual(rows[0]["amount"], 988181)

    def test_forward_airlift_requires_direct_market_coverage(self):
        config = json.loads((ROOT / "config/tourism_v2/forward-airlift-sources.v1.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(config["score_gate"]["minimum_market_coverage"], 0.65)
        self.assertGreaterEqual(config["score_gate"]["minimum_direct_market_coverage"], 0.5)
        self.assertTrue(config["rules"]["proxy_market_coverage_alone_cannot_unlock_composite_score"])

    def test_research_fallback_forbids_fake_trends(self):
        config = json.loads((ROOT / "config/tourism_v2/research-fallback.v1.json").read_text(encoding="utf-8"))
        hotel = config["modules"]["hotel_forward"]
        airfare = config["modules"]["airfare"]
        self.assertEqual(hotel["fallback_mode"], "RESEARCH_ON_DEMAND")
        self.assertIn("trend without comparable historical snapshots", hotel["forbidden_outputs"])
        self.assertIn("Airfare Pressure score from public deal pages", airfare["forbidden_outputs"])

    def test_module_registry_declares_research_and_live_fallbacks(self):
        config = json.loads((ROOT / "config/tourism_v2/module-registry.v1.json").read_text(encoding="utf-8"))
        modules = {item["module_id"]: item for item in config["modules"]}
        self.assertEqual(modules["hotel_forward"]["automation_state"], "RESEARCH_ON_DEMAND")
        self.assertEqual(modules["social_intent"]["automation_state"], "RESEARCH_ON_DEMAND")
        self.assertEqual(modules["airfare"]["automation_state"], "FALLBACK_LIVE")
        self.assertEqual(modules["forward_airlift"]["automation_state"], "PARTIAL_LIVE")

    def test_readiness_does_not_promote_fallback_to_core_ready(self):
        now = datetime.now(VN).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weather = root / "weather.json"
            sun = root / "sun.json"
            marine = root / "marine.json"
            airfare = root / "airfare.json"
            forward = root / "forward.json"

            weather.write_text(json.dumps({
                "cutoff_time": now,
                "data_mode": "B",
                "direct_ingest_status": {"ecmwf": {"qc": "PASS"}},
                "critical_data_gaps": [],
            }), encoding="utf-8")
            sun.write_text(json.dumps({
                "state": "REPORT_READY",
                "qa_passed": True,
                "collected_at_vn": now,
                "source_date": "2026-09-16",
            }), encoding="utf-8")
            marine.write_text(json.dumps({
                "state": "REPORT_READY",
                "qa_passed": True,
                "collected_at_vn": now,
                "sources": {"PORT_CLEARANCE_KGG": "OK", "THANH_THOI_OPERATOR": "OK"},
            }), encoding="utf-8")
            airfare.write_text(json.dumps({
                "state": "PARTIAL_READY",
                "qa_passed": True,
                "last_successful_run": now,
                "source_coverage": 0.75,
            }), encoding="utf-8")
            forward.write_text(json.dumps({
                "state": "PARTIAL_READY",
                "qa_passed": True,
                "last_successful_run": now,
                "market_coverage": 0.3333,
                "direct_market_coverage": 0.1667,
                "direct_source_count": 2,
                "score_gate_passed": False,
            }), encoding="utf-8")

            result = build_readiness(
                ROOT / "config/tourism_v2/source-registry.v1.json",
                ROOT / "config/tourism_v2/module-registry.v1.json",
                weather,
                sun,
                marine,
                airfare,
                forward,
            )

        self.assertEqual(result["overall_completeness_percent"], 60.0)
        self.assertEqual(result["direct_evidence_coverage_percent"], 60.0)
        self.assertEqual(result["run_status"], "DEGRADED")
        self.assertEqual(result["modules"]["hotel_forward"]["state"], "RESEARCH_ON_DEMAND")
        self.assertEqual(result["modules"]["airfare"]["state"], "FALLBACK_READY")
        self.assertFalse(result["modules"]["airfare"]["fixed_basket_ready"])
        self.assertFalse(result["modules"]["airfare"]["airfare_pressure_eligible"])
        self.assertIn("airfare", result["missing_core_modules"])
        self.assertIn("hotel_forward", result["missing_core_modules"])
        self.assertEqual(result["modules"]["forward_airlift"]["state"], "PARTIAL_READY")
        self.assertFalse(result["modules"]["forward_airlift"]["forward_airlift_signal_eligible"])

    def test_forward_projects_not_in_current_hotel_index(self):
        config = json.loads((ROOT / "config/tourism_v2/hotel-basket.v1.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not item["include_in_availability_index"] for item in config["forward_projects"]))


if __name__ == "__main__":
    unittest.main()
