"""Verified research corpus loader for JoTrip Weather Ground Truth.

The corpus is part of the production data plane, but provenance classes retain
separate roles:
- RAW_OBS may be used as actual verification.
- OFFICIAL_AGGREGATE_OBS is windowed historical verification.
- PUBLISHED_STATION_OBS is corroboration / historical verification only.
No corpus row is silently promoted to a current-time observation.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _num(v: Any) -> float | None:
    try:
        return float(v) if str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def load_observation_seed(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row:
                continue
            record = {k: (v if v != "" else None) for k, v in row.items()}
            record["value"] = _num(record.get("value"))
            cls = str(record.get("source_class") or "").upper()
            record["production_role"] = {
                "RAW_OBS": "VERIFICATION_ACTUAL",
                "OFFICIAL_AGGREGATE_OBS": "WINDOWED_HISTORICAL_VERIFICATION",
                "PUBLISHED_STATION_OBS": "HISTORICAL_CORROBORATION",
            }.get(cls, "REGISTRY_ONLY")
            rows.append(record)
    return rows


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "groundtruth-source-registry-v1", "sources": []}
    return json.loads(path.read_text(encoding="utf-8"))


def build_corpus(seed_path: Path, registry_path: Path) -> dict[str, Any]:
    rows = load_observation_seed(seed_path)
    registry = load_registry(registry_path)
    by_class = Counter(str(r.get("source_class") or "UNKNOWN") for r in rows)
    by_metric = Counter(str(r.get("metric") or "UNKNOWN") for r in rows)
    return {
        "schema_version": "weather-groundtruth-corpus-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "counts_by_class": dict(sorted(by_class.items())),
        "counts_by_metric": dict(sorted(by_metric.items())),
        "records": rows,
        "source_registry": registry,
        "policy": {
            "current_time_actual_requires_live_timestamped_stream": True,
            "official_aggregate_is_live_now": False,
            "published_station_observation_is_live_now": False,
            "model_or_satellite_is_groundtruth": False,
            "identifier_collision_guard": "namespace+identifier+station_epoch+timestamp",
        },
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=Path, required=True)
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    payload = build_corpus(a.seed, a.registry)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "record_count": payload["record_count"],
        "counts_by_class": payload["counts_by_class"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
