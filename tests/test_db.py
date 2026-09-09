from adopt_hokkaido_lidar import db


def test_connect_creates_all_nine_entity_tables(tmp_path):
    conn = db.connect(str(tmp_path / "state.sqlite3"))
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    expected = {
        "source_item",
        "source_package",
        "source_member",
        "logical_asset",
        "derived_asset_version",
        "published_asset",
        "footprint",
        "attribution",
        "provenance_link",
    }
    assert expected.issubset(tables)
    conn.close()


def test_connect_is_idempotent(tmp_path):
    path = str(tmp_path / "state.sqlite3")
    db.connect(path).close()
    # Running init again against the same file must not error (CREATE TABLE IF NOT EXISTS).
    db.connect(path).close()


def test_logical_asset_status_check_constraint(tmp_path):
    conn = db.connect(str(tmp_path / "state.sqlite3"))
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('si1','ckan','coverage_feature','ckan','now')"
    )
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES ('sp1','si1','ckan','now','{}')"
    )
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES ('sm1','sp1','オリジナルデータ','ZIP','https://example/original.zip')"
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES ('a1','sm1','ORIGINAL/13nc012_org.txt','discovered')"
    )
    conn.commit()

    import sqlite3

    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
            "VALUES ('a2','sm1','ORIGINAL/13nc014_org.txt','not_a_real_status')"
        )
    conn.close()


def test_source_item_source_system_check_constraint(tmp_path):
    import sqlite3

    import pytest

    conn = db.connect(str(tmp_path / "state.sqlite3"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
            "VALUES ('si1','geospatial_jp','coverage_feature','ckan','now')"
        )
    conn.close()


def test_derived_asset_version_source_format_check_constraint(tmp_path):
    import sqlite3

    import pytest

    conn = db.connect(str(tmp_path / "state.sqlite3"))
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('si1','arcgis','arcgis_item','arcgis_hub_search','now')"
    )
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES ('sp1','si1','arcgis','now','{}')"
    )
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES ('sm1','sp1','12HE88_ORIGINAL_LAZ','ZIP','https://example/12HE88.zip')"
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES ('a1','sm1','ORIGINAL_LAZ/12HE811.laz','discovered')"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO derived_asset_version (id, asset_id, version, source_format) "
            "VALUES ('v1','a1',1,'zip')"
        )
    conn.close()
