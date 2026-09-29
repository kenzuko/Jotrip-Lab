"""Run a read-only HTTP probe from a Globalping probe located in Vietnam.

Purpose: inspect the public kttvtudong Phu Quoc station page from a Vietnam
egress IP when the upstream blocks non-Vietnam networks.

No authentication, credential, proxy pool, or write action is used.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.globalping.io/v1/measurements"
USER_AGENT = "JoTrip-WeatherLab/1.0 VN-readonly-probe"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = {"raw": data}
        return exc.code, parsed


def run_probe(
    path: str,
    query: str,
    range_header: str | None = None,
) -> dict:
    request_headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": USER_AGENT,
    }
    if range_header:
        request_headers["Range"] = range_header

    create = {
        "type": "http",
        "target": "kttvtudong.net",
        "locations": [{"country": "VN"}],
        "limit": 1,
        "measurementOptions": {
            "protocol": "HTTPS",
            "port": 443,
            "request": {
                "method": "GET",
                "path": path,
                "query": query,
                "headers": request_headers,
            },
        },
    }
    status, created = _request_json(API, method="POST", payload=create)
    if status != 202:
        raise RuntimeError(f"Globalping create failed HTTP {status}: {created}")
    measurement_id = created["id"]

    for _ in range(35):
        time.sleep(1.0)
        status, result = _request_json(f"{API}/{measurement_id}")
        if status != 200:
            raise RuntimeError(f"Globalping result failed HTTP {status}: {result}")
        if result.get("status") != "in-progress":
            return result
    raise TimeoutError(f"Globalping measurement {measurement_id} did not finish")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="/kttv/detail/view")
    parser.add_argument("--query", default="sid=33")
    parser.add_argument("--range", dest="range_header")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run_probe(args.path, args.query, args.range_header)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = result.get("results") or []
    summary = []
    for row in rows:
        probe = row.get("probe") or {}
        measured = row.get("result") or {}
        raw_body = measured.get("rawBody")
        summary.append(
            {
                "country": probe.get("country"),
                "city": probe.get("city"),
                "network": probe.get("network"),
                "status": measured.get("status"),
                "statusCode": measured.get("statusCode"),
                "resolvedAddress": measured.get("resolvedAddress"),
                "truncated": measured.get("truncated"),
                "contentRange": (measured.get("headers") or {}).get("content-range"),
                "rawBodyLength": len(raw_body) if isinstance(raw_body, str) else None,
            }
        )
    print(
        json.dumps(
            {"id": result.get("id"), "status": result.get("status"), "probes": summary},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
