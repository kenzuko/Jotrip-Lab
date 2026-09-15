"""Operational status normalization for port permits and restrictions."""
from __future__ import annotations

import hashlib


def normalize_port_evidence(*, source: str, observed_time: str, scope: str,
                            evidence_type: str, trip_status: str, reference: str | None = None) -> dict:
    allowed_types = {"PORT_RESTRICTION", "DEPARTURE_PERMIT", "OPERATOR_NOTICE", "FIELD_CONFIRMATION"}
    allowed_status = {"OPEN", "DEPARTED", "RESTRICTED", "CLOSED", "CANCELLED", "UNKNOWN"}
    if evidence_type not in allowed_types or trip_status not in allowed_status:
        raise ValueError("invalid operational evidence")
    identity = f"{source}|{observed_time}|{scope}|{evidence_type}|{trip_status}|{reference}"
    return {"id": hashlib.sha256(identity.encode()).hexdigest()[:24], "source": source,
            "observation_time": observed_time, "scope": scope, "event_type": evidence_type,
            "status": trip_status, "raw_reference": reference, "provenance": "OFFICIAL_OPERATIONAL"}
