from adopt_hokkaido_lidar.arcgis import (
    HP_KIND_ARCGIS_HUB_SEARCH,
    HP_KIND_CKAN,
    HP_KIND_EMPTY,
    HP_KIND_UNKNOWN,
    ckan_dataset_slug,
    classify_hp_link,
    parse_coverage_features,
    parse_operational_layers,
)


def test_parse_operational_layers():
    webmap = {
        "operationalLayers": [
            {"id": "a", "title": "オープンデータ範囲", "layerType": "GeoJSON", "itemId": "2af5..."},
            {"id": "b", "title": "11系", "layerType": "ArcGISFeatureLayer", "url": "https://example/FeatureServer/0"},
        ]
    }
    layers = parse_operational_layers(webmap)
    assert len(layers) == 2
    assert layers[0].item_id == "2af5..."
    assert layers[1].url == "https://example/FeatureServer/0"


def test_classify_hp_link_ckan():
    assert classify_hp_link("https://www.geospatial.jp/ckan/dataset/h25oribegawasabou") == HP_KIND_CKAN


def test_classify_hp_link_arcgis_hub_search():
    url = "https://opendata-rakuno-gis.hub.arcgis.com/search?tags=R05%E5%B8%AF%E5%BA%83"
    assert classify_hp_link(url) == HP_KIND_ARCGIS_HUB_SEARCH


def test_classify_hp_link_empty():
    assert classify_hp_link("") == HP_KIND_EMPTY
    assert classify_hp_link(None) == HP_KIND_EMPTY


def test_classify_hp_link_unknown_is_not_guessed_into_a_bucket():
    assert classify_hp_link("https://example.com/totally-different-thing") == HP_KIND_UNKNOWN


def test_ckan_dataset_slug():
    assert ckan_dataset_slug("https://www.geospatial.jp/ckan/dataset/h25oribegawasabou") == "h25oribegawasabou"


def test_ckan_dataset_slug_rejects_non_ckan_url():
    import pytest

    with pytest.raises(ValueError):
        ckan_dataset_slug("https://opendata-rakuno-gis.hub.arcgis.com/search?tags=x")


def test_parse_coverage_features():
    geojson = {
        "features": [
            {
                "properties": {
                    "助言番号": "2013-A-0609",
                    "事業名": "居辺川砂防地形調査",
                    "HP": "https://www.geospatial.jp/ckan/dataset/h25oribegawasabou",
                }
            },
            {
                "properties": {
                    "助言番号": "2022-A-0068",
                    "事業名": "上流川 砂防工事地形調査",
                    "HP": None,
                }
            },
        ]
    }
    features = parse_coverage_features(geojson)
    assert len(features) == 2
    assert features[0].hp_kind == HP_KIND_CKAN
    assert features[1].hp_kind == HP_KIND_EMPTY
