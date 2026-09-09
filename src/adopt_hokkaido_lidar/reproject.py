"""Reproject a projected bbox to WGS84 for footprint storage/display.

Shells out to `cs2cs` (PROJ) rather than adding a Python geodesy
dependency -- already proven against the real Jクレ tile in
docs-src/discovery-report.md (EPSG:2454 -> WGS84, verified against the
tile's own reprojected center matching independently-fetched GSI elevation
data for that point).
"""

from __future__ import annotations

import re
import subprocess

_EPSG_IN_WKT = re.compile(r'PROJCS\[.*AUTHORITY\["EPSG","(\d+)"\]\]\s*$')


def extract_epsg_from_projcs_wkt(wkt: str) -> str:
    """Pull the trailing PROJCS EPSG code out of a WKT1 string (as PDAL reports it).

    Raises ValueError rather than guessing when the pattern isn't found --
    a geographic-only or unrecognized WKT shape must not silently produce
    a wrong code.
    """
    m = _EPSG_IN_WKT.search(wkt)
    if not m:
        raise ValueError(f"could not find a trailing PROJCS EPSG code in WKT: {wkt[:120]}...")
    return m.group(1)


def reproject_point(x: float, y: float, source_epsg: str) -> tuple[float, float]:
    """Reproject one (x, y) point from `source_epsg` to WGS84 (lon, lat) via cs2cs."""
    proc = subprocess.run(
        ["cs2cs", f"+init=epsg:{source_epsg}", "+to", "+init=epsg:4326", "-f", "%.8f"],
        input=f"{x} {y}\n",
        capture_output=True,
        text=True,
        check=True,
    )
    lon, lat, _ = proc.stdout.split()
    return float(lon), float(lat)


def reproject_bbox_to_wgs84_ring(
    minx: float, miny: float, maxx: float, maxy: float, source_epsg: str
) -> list[list[float]]:
    """Reproject a bbox's 4 corners to a closed WGS84 polygon ring (5 points, first == last)."""
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)]
    return [list(reproject_point(x, y, source_epsg)) for x, y in corners]
