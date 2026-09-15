"""SQLite archive for local/CI MVP; schema maps cleanly to PostgreSQL later."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_runs (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, model TEXT, system TEXT, run_time TEXT NOT NULL,
 status TEXT NOT NULL, expected_members INTEGER, retrieved_members INTEGER, collector_version TEXT
);
CREATE TABLE IF NOT EXISTS forecast_values (
 record_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, member TEXT, valid_time TEXT NOT NULL,
 variable TEXT NOT NULL, requested_lat REAL, requested_lon REAL, sampled_lat REAL, sampled_lon REAL,
 grid_resolution REAL, value REAL NOT NULL, unit TEXT NOT NULL, qc TEXT NOT NULL, lineage_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, location_id TEXT NOT NULL, observation_time TEXT NOT NULL,
 variable TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL, qc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routes (
 route_id TEXT NOT NULL, version TEXT NOT NULL, geometry_json TEXT NOT NULL,
 production_eligible INTEGER NOT NULL, PRIMARY KEY (route_id, version)
);
CREATE TABLE IF NOT EXISTS route_values (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, route_id TEXT NOT NULL, segment_id TEXT,
 valid_time TEXT NOT NULL, variable TEXT NOT NULL, typical_value REAL, max_value REAL,
 upper_percentile REAL, worst_point_json TEXT, exposure_duration REAL, unit TEXT, qc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS official_events (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, issue_time TEXT, valid_from TEXT, valid_to TEXT,
 scope TEXT, event_type TEXT, status TEXT, raw_reference TEXT, parsed_payload TEXT
);
CREATE TABLE IF NOT EXISTS derived_values (
 id TEXT PRIMARY KEY, metric TEXT NOT NULL, value_json TEXT NOT NULL, formula_id TEXT NOT NULL,
 formula_version TEXT NOT NULL, input_record_ids TEXT NOT NULL, git_commit_sha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
 snapshot_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, cutoff_time TEXT NOT NULL,
 generated_at TEXT NOT NULL, data_mode TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL
);
"""


class WeatherStore:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(str(path))
        self.connection.executescript(SCHEMA)

    def save_snapshot(self, snapshot: dict) -> None:
        self.connection.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snapshot["snapshot_id"], snapshot["schema_version"], snapshot["cutoff_time"], snapshot["generated_at"], snapshot["data_mode"], json.dumps(snapshot, ensure_ascii=False, sort_keys=True), snapshot["payload_hash"]),
        )
        self.connection.commit()

    def save_model_run(self, run: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO model_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run["id"], run["source"], run.get("model"), run.get("system"), run["run_time"],
             run["status"], run.get("expected_members"), run.get("retrieved_members"), run.get("collector_version")),
        )
        self.connection.commit()

    def save_forecast_values(self, records: list[dict]) -> None:
        rows = [(r["record_id"], r["run_id"], r.get("member"), r["valid_time"], r["variable"],
                 r.get("requested_lat"), r.get("requested_lon"), r.get("sampled_lat"), r.get("sampled_lon"),
                 r.get("grid_resolution"), r["value"], r["unit"], r["qc"], r["lineage_id"]) for r in records]
        self.connection.executemany("INSERT OR REPLACE INTO forecast_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        self.connection.commit()

    def save_observations(self, records: list[dict]) -> None:
        rows = [(r["id"], r["source"], r["location_id"], r["observation_time"], r["variable"],
                 r["value"], r["unit"], r["qc"]) for r in records]
        self.connection.executemany("INSERT OR REPLACE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        self.connection.commit()

    def save_official_event(self, event: dict) -> None:
        self.connection.execute("INSERT OR REPLACE INTO official_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (event["id"], event["source"], event.get("issue_time"), event.get("valid_from"),
                                 event.get("valid_to"), event.get("scope"), event.get("event_type"), event.get("status"),
                                 event.get("raw_reference"), json.dumps(event.get("parsed_payload", {}), ensure_ascii=False)))
        self.connection.commit()

    def save_derived_value(self, record: dict) -> None:
        self.connection.execute("INSERT OR REPLACE INTO derived_values VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (record["id"], record["metric"], json.dumps(record["value"], ensure_ascii=False),
                                 record["formula_id"], record["formula_version"],
                                 json.dumps(record["input_record_ids"]), record["git_commit_sha"]))
        self.connection.commit()

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        row = self.connection.execute("SELECT payload FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self) -> None:
        self.connection.close()
