"""Credential-gated official Copernicus Marine subset adapter."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def configuration_status() -> dict:
    required = (
        "COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD",
        "COPERNICUS_WAVE_DATASET_ID", "COPERNICUS_CURRENT_DATASET_ID",
    )
    missing = [name for name in required if not os.getenv(name)]
    return {"status": "READY" if not missing else "AUTH_OR_CONFIG_REQUIRED", "missing": missing}


def subset(*, dataset_id: str, variables: list[str], start: datetime, end: datetime,
           bbox: tuple[float, float, float, float], output: Path,
           minimum_depth: float | None = None, maximum_depth: float | None = None) -> dict:
    status = configuration_status()
    if status["status"] != "READY":
        return status
    try:
        import copernicusmarine
    except ImportError as exc:
        raise RuntimeError("Install the official copernicusmarine package") from exc
    south, west, north, east = bbox
    kwargs = {
        "dataset_id": dataset_id, "variables": variables,
        "minimum_longitude": west, "maximum_longitude": east,
        "minimum_latitude": south, "maximum_latitude": north,
        "start_datetime": start.isoformat(), "end_datetime": end.isoformat(),
        "output_filename": output.name, "output_directory": str(output.parent),
        "username": os.environ["COPERNICUSMARINE_SERVICE_USERNAME"],
        "password": os.environ["COPERNICUSMARINE_SERVICE_PASSWORD"], "overwrite": True,
    }
    if minimum_depth is not None:
        kwargs["minimum_depth"] = minimum_depth
    if maximum_depth is not None:
        kwargs["maximum_depth"] = maximum_depth
    response = copernicusmarine.subset(**kwargs)
    return {"status": "OBJECT_RETRIEVED", "dataset_id": dataset_id,
            "variables": variables, "path": str(output), "response": str(response)}
