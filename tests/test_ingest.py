import json

from adopt_hokkaido_lidar import db
from adopt_hokkaido_lidar.ingest import IngestResult, record_ingest_result


def _seed_source_chain(conn):
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
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path) VALUES ('a1', 'sm1', 'x.laz')"
    )
    conn.commit()


def test_record_ingest_result_writes_derived_asset_version_and_footprint(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)

    report_path = tmp_path / "a1.validation_report.json"
    report_path.write_text(json.dumps({"asset_id": "a1"}))

    ring = [
        [142.45031501, 44.23999742],
        [142.46155336, 44.23997716],
        [142.46156355, 44.24282073],
        [142.45032466, 44.24284099],
        [142.45031501, 44.23999742],
    ]
    result = IngestResult(
        asset_id="a1",
        copc_path=str(tmp_path / "a1.copc.laz"),
        sha256="deadbeef",
        point_count=448887,
        crs_wkt='PROJCS["JGD2000 / Japan Plane Rectangular CS XII"...AUTHORITY["EPSG","2454"]]',
        source_format="las",
        validation_report_path=str(report_path),
        footprint_ring_wgs84=ring,
    )

    record_ingest_result(conn, result, asset_id="a1")

    dav = conn.execute("SELECT version, point_count, crs FROM derived_asset_version WHERE asset_id = 'a1'").fetchone()
    assert dav == (1, 448887, result.crs_wkt)

    status = conn.execute("SELECT status FROM logical_asset WHERE asset_id = 'a1'").fetchone()[0]
    assert status == "validated"

    fp = conn.execute(
        "SELECT bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, geometry_geojson FROM footprint WHERE asset_id = 'a1'"
    ).fetchone()
    minx, miny, maxx, maxy, geom_json = fp
    assert minx == 142.45031501
    assert maxx == 142.46156355
    geom = json.loads(geom_json)
    assert geom["type"] == "Polygon"
    assert geom["coordinates"][0] == ring


def test_record_ingest_result_skips_footprint_when_none(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)

    report_path = tmp_path / "a1.validation_report.json"
    report_path.write_text(json.dumps({"asset_id": "a1"}))

    result = IngestResult(
        asset_id="a1",
        copc_path=str(tmp_path / "a1.copc.laz"),
        sha256="deadbeef",
        point_count=100,
        crs_wkt=None,
        source_format="las",
        validation_report_path=str(report_path),
        footprint_ring_wgs84=None,
    )
    record_ingest_result(conn, result, asset_id="a1")

    assert conn.execute("SELECT * FROM footprint WHERE asset_id = 'a1'").fetchone() is None


def test_record_ingest_result_increments_version_on_second_call(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    report_path = tmp_path / "a1.validation_report.json"
    report_path.write_text("{}")

    def make_result():
        return IngestResult(
            asset_id="a1",
            copc_path=str(tmp_path / "a1.copc.laz"),
            sha256="x",
            point_count=1,
            crs_wkt=None,
            source_format="las",
            validation_report_path=str(report_path),
        )

    record_ingest_result(conn, make_result(), asset_id="a1")
    record_ingest_result(conn, make_result(), asset_id="a1")

    versions = [
        r[0] for r in conn.execute("SELECT version FROM derived_asset_version WHERE asset_id = 'a1' ORDER BY version")
    ]
    assert versions == [1, 2]
