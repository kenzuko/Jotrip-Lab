"""Normalize official Vietnamese bulletin text without treating it as observation."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime


WIND = re.compile(r"(?:gió|Gió)[^.]{0,80}?cấp\s*(\d)(?:\s*[-–]\s*(\d))?", re.I)
WAVE = re.compile(r"(?:độ cao sóng|sóng)\s*:?\s*(\d+(?:[,.]\d+)?)\s*[-–]\s*(\d+(?:[,.]\d+)?)\s*m", re.I)
VIS = re.compile(r"(?:tầm nhìn xa|tầm nhìn)\s*:?\s*(?:trên\s*)?(\d+(?:[,.]\d+)?)\s*km", re.I)


def parse_official_bulletin(text: str, *, source: str, issue_time: str, valid_from: str,
                            valid_to: str, scope: str, raw_reference: str | None = None) -> dict:
    wind, wave, visibility = WIND.search(text), WAVE.search(text), VIS.search(text)
    parsed = {}
    if wind:
        parsed["wind_beaufort"] = [int(wind.group(1)), int(wind.group(2) or wind.group(1))]
    if wave:
        parsed["wave_height_m"] = [float(wave.group(1).replace(",", ".")),
                                   float(wave.group(2).replace(",", "."))]
    if visibility:
        parsed["visibility_km_min"] = float(visibility.group(1).replace(",", "."))
    normalized = " ".join(text.split())
    event_id = hashlib.sha256(f"{source}|{issue_time}|{scope}|{normalized}".encode()).hexdigest()[:24]
    return {"id": event_id, "source": source, "issue_time": issue_time,
            "valid_from": valid_from, "valid_to": valid_to, "scope": scope,
            "event_type": "OFFICIAL_FORECAST", "status": "ACTIVE_VALID",
            "raw_reference": raw_reference, "raw_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "parsed_payload": parsed, "parse_status": "PARSED" if parsed else "RAW_NOT_PARSED",
            "provenance": "OFFICIAL", "is_observation": False}


def validity_status(event: dict, now: datetime) -> str:
    start = datetime.fromisoformat(event["valid_from"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(event["valid_to"].replace("Z", "+00:00"))
    if now < start:
        return "NOT_YET_VALID"
    if now <= end:
        return "ACTIVE_VALID"
    return "EXPIRED"
