"""Direct model request manifests. Download/decode is a separate worker concern."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RequestManifest:
    source: str
    run_time: str
    variables: tuple[str, ...]
    steps: tuple[int, ...]
    bounding_box: tuple[float, float, float, float]
    member_mode: str
    provenance: str = "DIRECT"

    def as_dict(self) -> dict:
        result = asdict(self)
        result["variables"] = list(self.variables)
        result["steps"] = list(self.steps)
        result["bounding_box"] = list(self.bounding_box)
        return result


def latest_completed_cycle(now: datetime, cycles: tuple[int, ...], lag_hours: int) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    candidates = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in cycles]
    eligible = [c for c in candidates if (now - c).total_seconds() >= lag_hours * 3600]
    if eligible:
        return max(eligible)
    previous = now.replace(hour=max(cycles), minute=0, second=0, microsecond=0)
    from datetime import timedelta
    return previous - timedelta(days=1)


def default_manifests(now: datetime) -> list[dict]:
    bbox = (9.70, 103.55, 10.55, 104.45)  # south, west, north, east
    ecmwf_run = latest_completed_cycle(now, (0, 6, 12, 18), 6)
    gefs_run = latest_completed_cycle(now, (0, 6, 12, 18), 6)
    common_steps = tuple(range(0, 73, 3))
    return [
        RequestManifest("ECMWF_DIRECT", ecmwf_run.isoformat(), ("10u", "10v", "10fg", "tp", "vis"), common_steps, bbox, "deterministic").as_dict(),
        RequestManifest("NOAA_GEFS_DIRECT", gefs_run.isoformat(), ("ugrd10m", "vgrd10m", "gust", "apcp", "vis"), common_steps, bbox, "members").as_dict(),
        RequestManifest("NOAA_GEFS_WAVE_DIRECT", gefs_run.isoformat(), ("htsgw", "dirpw", "perpw"), common_steps, bbox, "members").as_dict(),
    ]
