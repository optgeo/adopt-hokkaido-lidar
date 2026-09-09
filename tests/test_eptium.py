import pytest

from adopt_hokkaido_lidar.eptium import eptium_url


def test_eptium_url_encodes_the_copc_url():
    url = eptium_url("https://data.source.coop/smartmaps/adopt-hokkaido-lidar/data/pkg/x/v1/x.copc.laz")
    assert url.startswith("https://eptium.com/?copc=")
    assert "https%3A%2F%2Fdata.source.coop" in url
    # no raw, unencoded second "?" or "/" leaking through the query value
    assert url.count("?") == 1


def test_eptium_url_rejects_non_absolute_url():
    with pytest.raises(ValueError):
        eptium_url("data/pkg/x/v1/x.copc.laz")
