"""Static inspection of the public iWeather map application bundle.

Uses the already captured browser-network metadata to locate the current
same-origin /map/app.*.js bundle, downloads that public static asset once, and
stores only short contexts around radar decoding terms. It never calls product
endpoints or reuses browser tokens.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

NETWORK = Path("weather/research/v3-iweather-network-probe.json")
OUT = Path("weather/research/v3-iweather-map-bundle-inspection.json")
UA = "JoTrip-WeatherV3-Research/1.0 (public-static-asset-inspection)"

TOKENS = (
    "/product/radar", "/product/lastradar", "/product/configProduct",
    "CMAX", "radarConfig", "getImageData", "ImageData", "Uint8Array",
    "Uint8ClampedArray", "readPixels", "texture", "colormap", "colorMap",
    "palette", "reflectivity", "dbz", "dBZ", "254", "255"
)


def contexts(text: str, token: str, limit: int = 20) -> list[str]:
    out = []
    low = text.lower()
    needle = token.lower()
    start = 0
    while len(out) < limit:
        idx = low.find(needle, start)
        if idx < 0:
            break
        left = max(0, idx - 350)
        right = min(len(text), idx + len(token) + 650)
        out.append(text[left:right].replace("\n", " ").replace("\r", " ")[:1200])
        start = idx + len(token)
    return out


def main() -> None:
    net = json.loads(NETWORK.read_text(encoding="utf-8"))
    candidates = []
    for row in net.get("responses") or []:
        url = row.get("url") or ""
        path = urlsplit(url).path
        if re.search(r"/map/app\.[A-Za-z0-9_-]+\.js$", path):
            candidates.append(url)
    candidates = sorted(set(candidates))

    payload = {
        "schema_version": "weather-v3-iweather-map-bundle-inspection-v1",
        "source_receipt": str(NETWORK),
        "candidate_bundles": candidates,
        "rules": {
            "public_static_asset_only": True,
            "no_product_endpoint_calls": True,
            "no_token_replay": True,
            "context_only_output": True,
        },
        "bundles": [],
        "contexts": {},
        "status": "NO_BUNDLE",
    }

    if candidates:
        for url in candidates:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/javascript,*/*"})
            with urlopen(req, timeout=30) as res:
                raw = res.read()
            text = raw.decode("utf-8", errors="replace")
            payload["bundles"].append({
                "url": url,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
            bundle_key = urlsplit(url).path.rsplit("/", 1)[-1]
            for token in TOKENS:
                hits = contexts(text, token)
                if hits:
                    payload["contexts"].setdefault(token, {})[bundle_key] = hits
        payload["status"] = "INSPECTED"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "bundles": payload["bundles"],
        "tokens_found": sorted(payload["contexts"]),
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
