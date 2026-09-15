"""Immutable canonical snapshot construction."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def seal_snapshot(payload: dict) -> dict:
    result = deepcopy(payload)
    result.pop("payload_hash", None)
    result["payload_hash"] = hashlib.sha256(canonical_json(result).encode("utf-8")).hexdigest()
    return result


def verify_snapshot(payload: dict) -> bool:
    expected = payload.get("payload_hash")
    return bool(expected) and seal_snapshot(payload)["payload_hash"] == expected
