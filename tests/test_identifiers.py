import pytest

from adopt_hokkaido_lidar.identifiers import stable_asset_id


def test_stable_asset_id_is_deterministic():
    a = stable_asset_id("h25oribegawasabou", "ORIGINAL/12od01.laz")
    b = stable_asset_id("h25oribegawasabou", "ORIGINAL/12od01.laz")
    assert a == b


def test_stable_asset_id_differs_by_member_path():
    a = stable_asset_id("h25oribegawasabou", "ORIGINAL/12od01.laz")
    b = stable_asset_id("h25oribegawasabou", "ORIGINAL/12od02.laz")
    assert a != b


def test_stable_asset_id_differs_by_package():
    a = stable_asset_id("h25oribegawasabou", "ORIGINAL/12od01.laz")
    b = stable_asset_id("r01biseikawasabou", "ORIGINAL/12od01.laz")
    assert a != b


def test_stable_asset_id_distinguishes_same_filename_in_different_subdirs():
    a = stable_asset_id("pkg", "ORIGINAL/a/12od01.laz")
    b = stable_asset_id("pkg", "ORIGINAL/b/12od01.laz")
    assert a != b


def test_stable_asset_id_rejects_empty_inputs():
    with pytest.raises(ValueError):
        stable_asset_id("", "ORIGINAL/12od01.laz")
    with pytest.raises(ValueError):
        stable_asset_id("pkg", "")


def test_stable_asset_id_is_url_and_pmtiles_safe():
    import re

    asset_id = stable_asset_id("H25 Oribegawa Sabou!!", "ORIGINAL/12od01.laz")
    assert re.fullmatch(r"[a-z0-9-]+", asset_id)
    assert asset_id.startswith("h25-oribegawa-sabou-")
