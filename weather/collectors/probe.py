"""Low-cost direct-source health probes. No paid service is activated here."""
from __future__ import annotations

import json
import os
import argparse
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


def probe_source(item: dict) -> dict:
    attempts = []
    for endpoint in item["endpoints"]:
        state = probe_url(endpoint["url"])
        attempts.append({"endpoint": endpoint["name"], "url": endpoint["url"], **state})
        if state["status"] == "REACHABLE":
            return {
                "status": "REACHABLE", "selected_endpoint": endpoint["name"],
                "fallback_level": len(attempts) - 1, "attempts": attempts,
                "checked_at": state["checked_at"], "cost_guard": "NO_PAID_SERVICE_ACTIVATED"
            }
    return {
        "status": "RETRIEVAL_FAILED", "selected_endpoint": None,
        "fallback_level": None, "attempts": attempts, "checked_at": _utcnow(),
        "cost_guard": "NO_PAID_SERVICE_ACTIVATED"
    }


def probe_sources() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    result = {}
    pending = {}
    executor = ThreadPoolExecutor(max_workers=4)
    for source, item in config.items():
        if item.get("requires_credentials") and not os.getenv("COPERNICUSMARINE_SERVICE_USERNAME"):
            result[source] = {"status": "AUTH_REQUIRED", "checked_at": _utcnow(), "cost_guard": "NO_PAID_SERVICE_ACTIVATED"}
        else:
            pending[executor.submit(probe_source, item)] = source
    for future in as_completed(pending):
        source = pending[future]
        result[source] = future.result()
    executor.shutdown(wait=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    health = probe_sources()
    rendered = json.dumps(health, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
