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

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        row = self.connection.execute("SELECT payload FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self) -> None:
        self.connection.close()
