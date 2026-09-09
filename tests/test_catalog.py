import json
import shutil

import pytest

from adopt_hokkaido_lidar import db
from adopt_hokkaido_lidar.catalog import build_catalog_files, fetch_published_footprints

tippecanoe_available = pytest.mark.skipif(shutil.which("tippecanoe") is None, reason="tippecanoe not installed")


def _seed_one_published_asset(conn, asset_id="a1"):
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('si1', 'arcgis', 'arcgis_item', 'arcgis_hub_search', 'now')"
    )
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES ('sp1', 'si1', 'arcgis', 'now', '{}')"
    )
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES ('sm1', 'sp1', 'x', 'ZIP', 'https://example/x.zip')"
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES (?, 'sm1', 'x.laz', 'published')",
        (asset_id,),
    )
    geom = {
        "type": "Polygon",
        "coordinates": [[[142.450, 44.240], [142.461, 44.240], [142.461, 44.242], [142.450, 44.242], [142.450, 44.240]]],
    }
    conn.execute(
        "INSERT INTO footprint (asset_id, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, geometry_geojson) "
        "VALUES (?, 142.450, 44.240, 142.461, 44.242, ?)",
        (asset_id, json.dumps(geom)),
    )
    conn.execute(
        "INSERT INTO derived_asset_version (id, asset_id, version) VALUES (?, ?, 1)",
        (f"{asset_id}-v1", asset_id),
    )
    conn.execute(
        "INSERT INTO published_asset (asset_id, derived_asset_version_id, object_url, published_at) "
        "VALUES (?, ?, ?, 'now')",
        (
            asset_id,
            f"{asset_id}-v1",
            f"https://data.source.coop/smartmaps/adopt-hokkaido-lidar/data/arcgis/pkg/{asset_id}/v1/{asset_id}.copc.laz",
        ),
    )
    conn.commit()


def test_fetch_published_footprints_empty_when_nothing_published(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    assert fetch_published_footprints(conn) == []


def test_fetch_published_footprints_returns_asset_geometry_and_url(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_one_published_asset(conn)

    rows = fetch_published_footprints(conn)
    assert len(rows) == 1
    assert rows[0]["asset_id"] == "a1"
    assert rows[0]["geometry"]["type"] == "Polygon"
    assert rows[0]["object_url"].endswith("a1.copc.laz")


def test_fetch_published_footprints_excludes_unpublished_or_footprint_less_assets(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_one_published_asset(conn, asset_id="a1")
    # a2: logical_asset exists but never published -- must not appear.
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES ('a2', 'sm1', 'y.laz', 'validated')"
    )
    conn.commit()

    rows = fetch_published_footprints(conn)
    assert {r["asset_id"] for r in rows} == {"a1"}


def test_build_catalog_files_refuses_empty_catalog(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    with pytest.raises(ValueError, match="no published assets"):
        build_catalog_files(conn, str(tmp_path / "work"))


@tippecanoe_available
def test_build_catalog_files_produces_pmtiles_and_manifest(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_one_published_asset(conn)

    pmtiles_path, manifest_path = build_catalog_files(conn, str(tmp_path / "work"))

    assert pmtiles_path.endswith(".pmtiles")
    with open(pmtiles_path, "rb") as f:
        assert f.read(7) == b"PMTiles"

    with open(manifest_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 1
    assert lines[0]["asset_id"] == "a1"
    assert lines[0]["object_url"].endswith("a1.copc.laz")
