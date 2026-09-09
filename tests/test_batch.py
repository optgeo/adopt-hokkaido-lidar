from adopt_hokkaido_lidar import db
from adopt_hokkaido_lidar.batch import find_unpublished_jkure_packages


def _seed_jkure_item(conn):
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('jkure', 'arcgis', 'arcgis_hub_search', 'arcgis_hub_search', 'now')"
    )


def _seed_package(conn, package_id):
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES (?, 'jkure', 'arcgis', 'now', '{}')",
        (package_id,),
    )


def _seed_member_and_asset(conn, package_id, member_id, asset_id, *, published: bool):
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES (?, ?, 'x', 'ZIP', 'https://example/x.zip')",
        (member_id, package_id),
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
        "VALUES (?, ?, 'x.laz', ?)",
        (asset_id, member_id, "published" if published else "validated"),
    )
    if published:
        conn.execute(
            "INSERT INTO derived_asset_version (id, asset_id, version) VALUES (?, ?, 1)",
            (f"{asset_id}-v1", asset_id),
        )
        conn.execute(
            "INSERT INTO published_asset (asset_id, derived_asset_version_id, object_url, published_at) "
            "VALUES (?, ?, ?, 'now')",
            (asset_id, f"{asset_id}-v1", f"https://example/{asset_id}.copc.laz"),
        )


def test_never_ingested_package_counts_as_unpublished(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_jkure_item(conn)
    _seed_package(conn, "pkg1")
    conn.commit()

    assert find_unpublished_jkure_packages(conn) == ["pkg1"]


def test_fully_published_package_is_excluded(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_jkure_item(conn)
    _seed_package(conn, "pkg1")
    _seed_member_and_asset(conn, "pkg1", "m1", "a1", published=True)
    conn.commit()

    assert find_unpublished_jkure_packages(conn) == []


def test_partially_published_package_still_counts_as_unpublished(tmp_path):
    # Regression guard for the real 16-member-zip bug: a package with 2 of
    # its members published and 1 still pending must NOT be treated as done.
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_jkure_item(conn)
    _seed_package(conn, "pkg1")
    _seed_member_and_asset(conn, "pkg1", "m1", "a1", published=True)
    _seed_member_and_asset(conn, "pkg1", "m2", "a2", published=True)
    _seed_member_and_asset(conn, "pkg1", "m3", "a3", published=False)
    conn.commit()

    assert find_unpublished_jkure_packages(conn) == ["pkg1"]


def test_mix_of_done_and_not_done_packages(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    _seed_jkure_item(conn)
    _seed_package(conn, "pkg-done")
    _seed_member_and_asset(conn, "pkg-done", "m1", "a1", published=True)
    _seed_package(conn, "pkg-partial")
    _seed_member_and_asset(conn, "pkg-partial", "m2", "a2", published=True)
    _seed_member_and_asset(conn, "pkg-partial", "m3", "a3", published=False)
    _seed_package(conn, "pkg-fresh")
    conn.commit()

    result = find_unpublished_jkure_packages(conn)
    assert set(result) == {"pkg-partial", "pkg-fresh"}
