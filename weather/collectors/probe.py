"""Low-cost direct-source health probes. No paid service is activated here."""
from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_url(url: str, timeout: float = 5.0) -> dict:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "JoTrip-Lab/0.1 source-health"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"status": "REACHABLE", "http_status": response.status, "checked_at": _utcnow()}
    except urllib.error.HTTPError as exc:
        # 401/403 proves the endpoint exists but is not currently ingest eligible.
        status = "AUTH_REQUIRED" if exc.code in (401, 403) else "HTTP_ERROR"
        return {"status": status, "http_status": exc.code, "checked_at": _utcnow(), "error": str(exc)}
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
        return {"status": "RETRIEVAL_FAILED", "checked_at": _utcnow(), "error": str(exc)}


def probe_sources() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    result = {}
    pending = {}
    executor = ThreadPoolExecutor(max_workers=4)
    for source, item in config.items():
        if item.get("requires_credentials") and not os.getenv("COPERNICUSMARINE_SERVICE_USERNAME"):
            result[source] = {"status": "AUTH_REQUIRED", "checked_at": _utcnow(), "cost_guard": "NO_PAID_SERVICE_ACTIVATED"}
        else:
            pending[executor.submit(probe_url, item["base_url"])] = source
    for future in as_completed(pending):
        source = pending[future]
        result[source] = future.result()
        result[source]["cost_guard"] = "NO_PAID_SERVICE_ACTIVATED"
    executor.shutdown(wait=True)
    return result


if __name__ == "__main__":
    print(json.dumps(probe_sources(), ensure_ascii=False, indent=2))
