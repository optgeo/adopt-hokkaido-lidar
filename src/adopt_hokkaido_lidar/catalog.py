"""Build and publish the catalog (PMTiles footprint index + manifest.jsonl).

The PMTiles feature carries ONLY asset_id (startup spec constraint, also
enforced by the web app -- web/src/main.ts never trusts any other PMTiles
property). The actual object_url lives only in manifest.jsonl, which the
map looks up by asset_id on click. Rebuilding this catalog is NOT the same
as overwriting an immutable published_asset object -- it's a living index
over what's been published, expected to be regenerated as more assets land
(docs-src/provenance-policy.md's immutability rule is about individual
COPC objects, not this summary).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess

from . import sc_client
from .publish import SC_BUCKET, SC_PRODUCT


def fetch_published_footprints(conn: sqlite3.Connection) -> list[dict]:
    """Query every published asset that has a footprint. Returns GeoJSON-ready dicts."""
    rows = conn.execute(
        "SELECT f.asset_id, f.geometry_geojson, pa.object_url "
        "FROM footprint f "
        "JOIN published_asset pa ON pa.asset_id = f.asset_id "
        "JOIN logical_asset la ON la.asset_id = f.asset_id "
        "WHERE la.status = 'published'"
    ).fetchall()
    return [
        {"asset_id": asset_id, "geometry": json.loads(geom_json), "object_url": object_url}
        for asset_id, geom_json, object_url in rows
    ]


def build_catalog_files(conn: sqlite3.Connection, work_dir: str, *, tippecanoe_executable: str = "tippecanoe") -> tuple[str, str]:
    """Build index.pmtiles and manifest.jsonl locally from every published asset with a footprint.

    Returns (pmtiles_path, manifest_path). Raises if there's nothing to
    build (an empty catalog would be a regression from whatever's already
    published -- callers should not upload an accidentally-empty index over
    a real one).
    """
    os.makedirs(work_dir, exist_ok=True)
    rows = fetch_published_footprints(conn)
    if not rows:
        raise ValueError("no published assets with a footprint found -- refusing to build an empty catalog")

    geojson_path = os.path.join(work_dir, "catalog_index.geojson")
    manifest_path = os.path.join(work_dir, "catalog_manifest.jsonl")
    pmtiles_path = os.path.join(work_dir, "catalog_index.pmtiles")

    features = [
        {"type": "Feature", "properties": {"asset_id": r["asset_id"]}, "geometry": r["geometry"]} for r in rows
    ]
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)

    with open(manifest_path, "w") as f:
        for r in rows:
            f.write(json.dumps({"asset_id": r["asset_id"], "object_url": r["object_url"]}, ensure_ascii=False) + "\n")

    proc = subprocess.run(
        [
            tippecanoe_executable,
            "-o", pmtiles_path,
            "-l", "footprints",
            "-Z0", "-z14",
            "--force",
            geojson_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"tippecanoe failed: {proc.stderr}")

    return pmtiles_path, manifest_path


def publish_catalog(conn: sqlite3.Connection, work_dir: str) -> tuple[str, str]:
    """Build the catalog and upload it to Source Cooperative. Returns (pmtiles_url, manifest_url)."""
    pmtiles_path, manifest_path = build_catalog_files(conn, work_dir)

    pmtiles_s3 = f"s3://{SC_BUCKET}/{SC_PRODUCT}/catalog/index.pmtiles"
    manifest_s3 = f"s3://{SC_BUCKET}/{SC_PRODUCT}/catalog/manifest.jsonl"

    for local, remote in ((pmtiles_path, pmtiles_s3), (manifest_path, manifest_s3)):
        result = sc_client.upload(local, remote)
        if not result.ok:
            raise RuntimeError(f"catalog upload failed for {remote}: {result.stderr}")

    return (
        "https://data.source.coop/smartmaps/adopt-hokkaido-lidar/catalog/index.pmtiles",
        "https://data.source.coop/smartmaps/adopt-hokkaido-lidar/catalog/manifest.jsonl",
    )
