"""Remap one live ICON field with DWD's official weights and extract Phu Quoc."""
from __future__ import annotations

import argparse
import bz2
import json
import math
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from weather.collectors.icon_assets import REMAP_PACK_URL, download_remap_pack
from weather.collectors.live_smoke import _decode_grib, _request

DWD_ROOT = "https://opendata.dwd.de/weather/nwp/icon/grib"

SPATIAL_GRID_DEG = 0.25
SPATIAL_GRID_REQUESTS = tuple(
    (round(lat, 2), round(lon, 2))
    for lat in (9.50, 9.75, 10.00, 10.25, 10.50, 10.75)
    for lon in (103.50, 103.75, 104.00, 104.25, 104.50)
)


def _field_stamp(name: str) -> str | None:
    match = re.search(r"_(\d{10})_000_U_10M\.grib2\.bz2$", name, flags=re.I)
    return match.group(1) if match else None


def _discover_variable(variable_dir: str, token: str) -> dict[str, str]:
    errors = []
    found: dict[str, str] = {}
    pattern = rf'href="([^"]+_000_{token}\.grib2\.bz2)"'
    for hour in (0, 6, 12, 18):
        directory = f"{DWD_ROOT}/{hour:02d}/{variable_dir}/"
        try:
            html = _request(directory).decode("utf-8", errors="replace")
            names = re.findall(pattern, html, flags=re.I)
            for name in set(names):
                stamp = re.search(r"_(\d{10})_000_", name)
                if stamp:
                    found[stamp.group(1)] = directory + name
        except Exception as exc:
            errors.append(f"{directory}: {type(exc).__name__}: {exc}")
    if not found:
        raise RuntimeError("No live ICON field for " + token + ": " + " | ".join(errors))
    return found


def discover_latest_fields() -> dict[str, str]:
    """Select the newest common step-000 U/V pair."""
    us = _discover_variable("u_10m", "U_10M")
    vs = _discover_variable("v_10m", "V_10M")
    common = sorted(set(us) & set(vs))
    if not common:
        raise RuntimeError("No common live ICON U/V cycle")
    stamp = common[-1]
    return {"stamp": stamp, "u": us[stamp], "v": vs[stamp]}


def discover_latest_field() -> str:
    """Backward-compatible U10 helper."""
    return discover_latest_fields()["u"]


def _safe_extract(pack: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(pack, mode="r:bz2") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"Unsafe tar member: {member.name}")
        archive.extractall(destination, filter="data")


def _remap_field(source_url: str, work: Path, target_grid: Path, weights: Path, name: str) -> tuple[Path, int, str]:
    compressed = _request(source_url, timeout=90)
    source_grib = work / f"icon-native-{name}.grib2"
    source_grib.write_bytes(bz2.decompress(compressed))
    remapped = work / f"icon-world-025-{name}.grib2"
    command = [
        "cdo", "-f", "grb2",
        f"remap,{target_grid},{weights}",
        str(source_grib), str(remapped),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode:
        raise RuntimeError(f"CDO remap failed for {name}: {completed.stderr[-2000:]}")
    return remapped, len(compressed), completed.stderr[-1000:]


def _lead_hours(value) -> int:
    text = str(value).strip().lower()
    if text.endswith("m"):
        try:
            return int(round(float(text[:-1]) / 60.0))
        except ValueError:
            return 0
    if text.endswith("h"):
        try:
            return int(round(float(text[:-1])))
        except ValueError:
            return 0
    try:
        return int(round(float(text)))
    except ValueError:
        return 0


def _decode_spatial_uv(u_path: Path, v_path: Path) -> dict:
    from eccodes import (
        codes_get,
        codes_grib_find_nearest,
        codes_grib_new_from_file,
        codes_release,
    )

    def open_gid(path: Path):
        stream = path.open("rb")
        gid = codes_grib_new_from_file(stream)
        if gid is None:
            stream.close()
            raise RuntimeError(f"No GRIB message decoded from {path}")
        return stream, gid

    su, gu = open_gid(u_path)
    sv, gv = open_gid(v_path)
    try:
        cells = []
        for lat, lon in SPATIAL_GRID_REQUESTS:
            nu = codes_grib_find_nearest(gu, lat, lon)[0]
            nv = codes_grib_find_nearest(gv, lat, lon)[0]
            u = float(nu["value"])
            v = float(nv["value"])
            speed = math.hypot(u, v) * 3.6
            direction = (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0
            cells.append({
                "lat": round(float(nu["lat"]), 4),
                "lon": round(float(nu["lon"]), 4),
                "requested_lat": lat,
                "requested_lon": lon,
                "u10_ms": round(u, 4),
                "v10_ms": round(v, 4),
                "wind_kmh": round(speed, 3),
                "wind_direction_deg": round(direction, 1),
            })
        data_date = int(codes_get(gu, "dataDate"))
        data_time = int(codes_get(gu, "dataTime"))
        return {
            "status": "READY" if cells else "UNAVAILABLE",
            "product": "ICON_GLOBAL_0P25_REMAP_STEP0",
            "requested_grid_deg": SPATIAL_GRID_DEG,
            "display_interpolation": "RENDER_ONLY",
            "data_date": data_date,
            "data_time": data_time,
            "lead_hours": _lead_hours(codes_get(gu, "endStep")),
            "cell_count": len(cells),
            "cells": cells,
            "note": "DWD ICON global official conservative remap to 0.25°; step-000 spatial wind cross-check only.",
        }
    finally:
        codes_release(gu)
        codes_release(gv)
        su.close()
        sv.close()


def extract_live_icon_point(output: Path | None = None, field_url: str | None = None) -> dict:
    fields = discover_latest_fields()
    if field_url:
        fields["u"] = field_url
    with tempfile.TemporaryDirectory(prefix="jotrip-icon-") as temp:
        work = Path(temp)
        pack = work / "remap.tar.bz2"
        pack_meta = download_remap_pack(pack)
        _safe_extract(pack, work)
        assets = work / "ICON_GLOBAL2WORLD_025_EASY"
        target_grid = assets / "target_grid_world_025.txt"
        weights = assets / "weights_icogl2world_025.nc"

        remap_u, bytes_u, stderr_u = _remap_field(fields["u"], work, target_grid, weights, "u")
        remap_v, bytes_v, stderr_v = _remap_field(fields["v"], work, target_grid, weights, "v")
        decoded_u = _decode_grib(remap_u, nearest=True)
        decoded_v = _decode_grib(remap_v, nearest=True)
        spatial = _decode_spatial_uv(remap_u, remap_v)
        result = {
            "status": "POINT_NUMERIC_READY",
            "source": "DWD_ICON_DIRECT",
            "field_url": fields["u"],
            "field_urls": {"u": fields["u"], "v": fields["v"]},
            "cycle_stamp": fields.get("stamp"),
            "remap_pack_url": REMAP_PACK_URL,
            "remap_pack_sha256": pack_meta["sha256"],
            "method": "DWD_OFFICIAL_CONSERVATIVE_REMAP_0P25",
            "compressed_field_bytes": bytes_u + bytes_v,
            "decoded": decoded_u,
            "decoded_u": decoded_u,
            "decoded_v": decoded_v,
            "spatial": spatial,
            "cdo_stderr": (stderr_u + "\n" + stderr_v)[-1800:],
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
