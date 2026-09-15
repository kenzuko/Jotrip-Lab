"""Remap one live ICON field with DWD's official weights and extract Phu Quoc."""
from __future__ import annotations

import argparse
import bz2
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from weather.collectors.icon_assets import REMAP_PACK_URL, download_remap_pack
from weather.collectors.live_smoke import _decode_grib, _request

DWD_ROOT = "https://opendata.dwd.de/weather/nwp/icon/grib"


def _field_stamp(name: str) -> str | None:
    match = re.search(r"_(\d{10})_000_U_10M\.grib2\.bz2$", name, flags=re.I)
    return match.group(1) if match else None


def discover_latest_field() -> str:
    """Select the newest step-000 object across 00/06/12/18 ICON directories."""
    errors = []
    candidates: list[tuple[str, str]] = []
    for hour in (0, 6, 12, 18):
        directory = f"{DWD_ROOT}/{hour:02d}/u_10m/"
        try:
            html = _request(directory).decode("utf-8", errors="replace")
            names = re.findall(r'href="([^"]+_000_U_10M\.grib2\.bz2)"', html, flags=re.I)
            for name in set(names):
                stamp = _field_stamp(name)
                if stamp:
                    candidates.append((stamp, directory + name))
        except Exception as exc:
            errors.append(f"{directory}: {type(exc).__name__}: {exc}")
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    raise RuntimeError("No live ICON step-000 field: " + " | ".join(errors))


def _safe_extract(pack: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(pack, mode="r:bz2") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"Unsafe tar member: {member.name}")
        archive.extractall(destination, filter="data")


def extract_live_icon_point(output: Path | None = None, field_url: str | None = None) -> dict:
    field_url = field_url or discover_latest_field()
    with tempfile.TemporaryDirectory(prefix="jotrip-icon-") as temp:
        work = Path(temp)
        pack = work / "remap.tar.bz2"
        pack_meta = download_remap_pack(pack)
        _safe_extract(pack, work)
        assets = work / "ICON_GLOBAL2WORLD_025_EASY"
        target_grid = assets / "target_grid_world_025.txt"
        weights = assets / "weights_icogl2world_025.nc"

        compressed = _request(field_url, timeout=90)
        source_grib = work / "icon-native.grib2"
        source_grib.write_bytes(bz2.decompress(compressed))
        remapped = work / "icon-world-025.grib2"
        command = [
            "cdo", "-f", "grb2",
            f"remap,{target_grid},{weights}",
            str(source_grib), str(remapped),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode:
            raise RuntimeError(f"CDO remap failed: {completed.stderr[-2000:]}")
        decoded = _decode_grib(remapped, nearest=True)
        result = {
            "status": "POINT_NUMERIC_READY",
            "source": "DWD_ICON_DIRECT",
            "field_url": field_url,
            "remap_pack_url": REMAP_PACK_URL,
            "remap_pack_sha256": pack_meta["sha256"],
            "method": "DWD_OFFICIAL_CONSERVATIVE_REMAP_0P25",
            "compressed_field_bytes": len(compressed),
            "decoded": decoded,
            "cdo_stderr": completed.stderr[-1000:],
        }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--field-url")
    args = parser.parse_args()
    print(json.dumps(extract_live_icon_point(args.output, args.field_url), indent=2))
