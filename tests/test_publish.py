import pytest

from adopt_hokkaido_lidar import db
from adopt_hokkaido_lidar.publish import PublishBlocked, check_publish_gate, object_key, publish_asset


def _seed_source_chain(conn, *, source_system="arcgis"):
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('si1', ?, 'arcgis_item', 'arcgis_hub_search', 'now')",
        (source_system,),
    )
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES ('sp1', 'si1', ?, 'now', '{}')",
        (source_system,),
    )
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES ('sm1', 'sp1', '12HE88_ORIGINAL_LAZ', 'ZIP', 'https://example/12HE88.zip')"
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES ('a1', 'sm1', 'ORIGINAL_LAZ/12HE811.laz', 'validated')"
    )


def test_gate_fails_with_no_derived_asset_version(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    conn.commit()

    gate = check_publish_gate(conn, "a1")
    assert not gate.ok
    assert any("ingest" in m for m in gate.missing)


def test_gate_fails_without_vertical_datum(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    copc_path = tmp_path / "a1.copc.laz"
    copc_path.write_bytes(b"fake copc bytes")
    conn.execute(
        "INSERT INTO derived_asset_version (id, asset_id, version, source_format, copc_local_path, sha256, crs) "
        "VALUES ('a1-v1', 'a1', 1, 'las', ?, 'deadbeef', 'EPSG:2454')",
        (str(copc_path),),
    )
    conn.commit()

    gate = check_publish_gate(conn, "a1")
    assert not gate.ok
    assert any("vertical_datum" in m for m in gate.missing)


def test_gate_fails_without_attribution(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    copc_path = tmp_path / "a1.copc.laz"
    copc_path.write_bytes(b"fake copc bytes")
    conn.execute(
        "INSERT INTO derived_asset_version "
        "(id, asset_id, version, source_format, copc_local_path, sha256, crs, vertical_datum) "
        "VALUES ('a1-v1', 'a1', 1, 'las', ?, 'deadbeef', 'EPSG:2454', 'JGD2011 (vertical)')",
        (str(copc_path),),
    )
    conn.commit()

    gate = check_publish_gate(conn, "a1")
    assert not gate.ok
    assert any("attribution[source_data]" in m for m in gate.missing)
    assert any("attribution[processing]" in m for m in gate.missing)
    assert any("attribution[hosting]" in m for m in gate.missing)


def test_gate_passes_when_everything_confirmed(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    copc_path = tmp_path / "a1.copc.laz"
    copc_path.write_bytes(b"fake copc bytes")
    conn.execute(
        "INSERT INTO derived_asset_version "
        "(id, asset_id, version, source_format, copc_local_path, sha256, crs, vertical_datum) "
        "VALUES ('a1-v1', 'a1', 1, 'las', ?, 'deadbeef', 'EPSG:2454', 'JGD2011 (vertical)')",
        (str(copc_path),),
    )
    for scope in ("source_data", "processing", "hosting"):
        conn.execute(
            "INSERT INTO attribution (id, asset_id, scope, text) VALUES (?, 'a1', ?, 'x')",
            (f"attr-{scope}", scope),
        )
    conn.commit()

    gate = check_publish_gate(conn, "a1")
    assert gate.ok
    assert gate.missing == []


def test_publish_asset_raises_and_suspends_when_gate_fails(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_source_chain(conn)
    conn.commit()

    with pytest.raises(PublishBlocked):
        publish_asset(conn, "a1", source_system="arcgis", source_package_id="pkg", raw_stem="12he811")

    status, reason = conn.execute(
        "SELECT status, suspended_reason FROM logical_asset WHERE asset_id = 'a1'"
    ).fetchone()
    assert status == "suspended_provenance_review"
    assert reason  # some explanation was recorded, not silently dropped


def test_object_key_layout_matches_plan_md():
    key = object_key("arcgis", "fccdb80933434b3ab45bb7b725207e6b", "12he811", 1)
    assert key == "data/arcgis/fccdb80933434b3ab45bb7b725207e6b/12he811/v1/12he811.copc.laz"
