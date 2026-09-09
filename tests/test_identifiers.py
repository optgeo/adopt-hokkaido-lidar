import pytest

from adopt_hokkaido_lidar.identifiers import stable_asset_id


def test_stable_asset_id_is_deterministic():
    a = stable_asset_id("ckan", "h25oribegawasabou", "ORIGINAL/13nc012_org.txt")
    b = stable_asset_id("ckan", "h25oribegawasabou", "ORIGINAL/13nc012_org.txt")
    assert a == b


def test_stable_asset_id_differs_by_member_path():
    a = stable_asset_id("ckan", "h25oribegawasabou", "ORIGINAL/13nc012_org.txt")
    b = stable_asset_id("ckan", "h25oribegawasabou", "ORIGINAL/13nc014_org.txt")
    assert a != b


def test_stable_asset_id_differs_by_package():
    a = stable_asset_id("ckan", "h25oribegawasabou", "ORIGINAL/13nc012_org.txt")
    b = stable_asset_id("ckan", "r01biseikawasabou", "ORIGINAL/13nc012_org.txt")
    assert a != b


def test_stable_asset_id_differs_by_source_system_even_with_same_package_id():
    # CKAN package names and ArcGIS item ids are unrelated id spaces --
    # a same-string collision between the two must not collide asset_ids.
    a = stable_asset_id("ckan", "shared-id", "ORIGINAL/x.laz")
    b = stable_asset_id("arcgis", "shared-id", "ORIGINAL/x.laz")
    assert a != b


def test_stable_asset_id_rejects_unknown_source_system():
    with pytest.raises(ValueError):
        stable_asset_id("geospatial_jp", "pkg", "ORIGINAL/x.laz")


def test_stable_asset_id_distinguishes_same_filename_in_different_subdirs():
    a = stable_asset_id("arcgis", "pkg", "ORIGINAL_LAZ/a/12he811.laz")
    b = stable_asset_id("arcgis", "pkg", "ORIGINAL_LAZ/b/12he811.laz")
    assert a != b


def test_stable_asset_id_rejects_empty_inputs():
    with pytest.raises(ValueError):
        stable_asset_id("ckan", "", "ORIGINAL/x.laz")
    with pytest.raises(ValueError):
        stable_asset_id("ckan", "pkg", "")


def test_stable_asset_id_is_url_and_pmtiles_safe():
    import re

    asset_id = stable_asset_id("arcgis", "fccdb80933434b3ab45bb7b725207e6b", "ORIGINAL_LAZ/12HE811.laz")
    assert re.fullmatch(r"[a-z0-9-]+", asset_id)
    assert asset_id.startswith("arcgis-fccdb80933434b3ab45bb7b725207e6b-")
