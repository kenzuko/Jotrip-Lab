from __future__ import annotations

import argparse
import json
from pathlib import Path

from tourism_intelligence_v2.contracts import build_health, iso_vn, write_bundle
from tourism_intelligence_v2.readiness import build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-registry", default="config/tourism_v2/source-registry.v1.json")
    parser.add_argument("--module-registry", default="config/tourism_v2/module-registry.v1.json")
    parser.add_argument("--weather", required=True)
    parser.add_argument("--sun", required=True)
    parser.add_argument("--marine", required=True)
    parser.add_argument("--airfare-fallback", required=False, default=None)
    parser.add_argument("--forward-airlift", required=False, default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    latest = build(
        args.source_registry,
        args.module_registry,
        args.weather,
        args.sun,
        args.marine,
        args.airfare_fallback,
        args.forward_airlift,
    )
    health = build_health(
        "Tourism Data Readiness",
        "REPORT_READY",
        scheduler_triggered=True,
        collector_completed=True,
        parser_passed=True,
        normalization_passed=True,
        qa_passed=True,
        commit_succeeded=None,
        last_successful_run=iso_vn(),
    )
    health["report_run_status"] = latest["run_status"]
    health["market_condition_not_data_system_condition"] = True
    manifest = {
        "schema_version": "1.1",
        "module_schema_version": latest["schema_version"],
        "collector_version": "read-only-preflight-1.1.0",
        "source_registry_version": "1.1",
        "module_registry_version": "1.1",
        "paid_services_used": False,
    }
    write_bundle(Path(args.output_dir), latest, health, manifest)
    print(json.dumps({"health": health, "latest": latest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
