from adopt_hokkaido_lidar.ckan import find_original_laz_candidates, parse_package


def test_parse_package_and_finds_original_laz():
    # Shape modeled directly on the real h25oribegawasabou package_show response.
    result = {
        "name": "h25oribegawasabou",
        "license_id": "CC-BY",
        "organization": {"title": "総合政策部"},
        "notes": "座標参照系　EPSG2455　JGD2000平面直角座標系13系",
        "resources": [
            {"name": "位置図KML", "format": "KML", "url": ".../survey_plan.kml"},
            {"name": "オリジナルデータ", "format": "ZIP", "url": ".../original.zip"},
        ],
    }
    package = parse_package(result)
    assert package.license_id == "CC-BY"
    assert package.organization_title == "総合政策部"

    candidates = find_original_laz_candidates(package)
    assert len(candidates) == 1
    assert candidates[0].url.endswith("original.zip")


def test_find_original_laz_candidates_empty_when_only_derived_products():
    # Shape modeled on r01biseikawasabou / hokkaido-h30atumachiku: derived
    # products only, no original.zip anywhere in the resource list.
    result = {
        "name": "r01biseikawasabou",
        "license_id": "CC-BY",
        "organization": {"title": "総合政策部"},
        "notes": "",
        "resources": [
            {"name": "2mCSV", "format": "ZIP", "url": ".../2mcsv.zip"},
            {"name": "2mDTM", "format": "ZIP", "url": ".../2mdtm.zip"},
            {"name": "航空写真01", "format": "ZIP", "url": ".../photojpeg01.zip"},
        ],
    }
    package = parse_package(result)
    candidates = find_original_laz_candidates(package)
    assert candidates == []


def test_find_original_laz_candidates_ignores_non_zip_format():
    result = {
        "name": "example",
        "license_id": None,
        "organization": {},
        "notes": None,
        "resources": [
            {"name": "オリジナルデータ", "format": "KML", "url": ".../original.kml"},
        ],
    }
    package = parse_package(result)
    assert find_original_laz_candidates(package) == []
