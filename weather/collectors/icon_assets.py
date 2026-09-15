"""Manage versioned official DWD ICON remapping assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ASSET_URL = "https://opendata.dwd.de/weather/lib/cdo/ICON_GLOBAL2WORLD_025_EASY.tar.bz2"


def inspect_official_pack(output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="jotrip-icon-grid-") as temp:
        archive = Path(temp) / "icon-remap.tar.bz2"
        request = urllib.request.Request(ASSET_URL, headers={"User-Agent": "JoTrip-Lab/1.0"})
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        with tarfile.open(archive, "r:bz2") as bundle:
            members = [{"name": item.name, "size": item.size, "type": "file" if item.isfile() else "dir"}
                       for item in bundle.getmembers()]
    result = {
        "status": "OFFICIAL_REMAP_PACK_READY",
        "source": ASSET_URL,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "members": members,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_official_pack(args.output), ensure_ascii=False, indent=2))
