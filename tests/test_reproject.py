import shutil

import pytest

from adopt_hokkaido_lidar.reproject import (
    extract_epsg_from_projcs_wkt,
    reproject_bbox_to_wgs84_ring,
    reproject_point,
)

cs2cs_available = pytest.mark.skipif(shutil.which("cs2cs") is None, reason="cs2cs (PROJ) not installed")

# The real WKT PDAL reported for the Jクレ sample (docs-src/discovery-report.md).
REAL_JKURE_WKT = (
    'PROJCS["JGD2000 / Japan Plane Rectangular CS XII",GEOGCS["JGD2000",'
    'DATUM["Japanese_Geodetic_Datum_2000",SPHEROID["GRS 1980",6378137,298.257222101,'
    'AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6612"]],PRIMEM["Greenwich",0,'
    'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4612"]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",44],PARAMETER["central_meridian",142.25],'
    'PARAMETER["scale_factor",0.9999],PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
    'AXIS["Northing",NORTH],AXIS["Easting",EAST],AUTHORITY["EPSG","2454"]]'
)


def test_extract_epsg_from_real_jkure_wkt():
    assert extract_epsg_from_projcs_wkt(REAL_JKURE_WKT) == "2454"


def test_extract_epsg_raises_when_pattern_absent():
    with pytest.raises(ValueError):
        extract_epsg_from_projcs_wkt('GEOGCS["WGS 84",AUTHORITY["EPSG","4326"]]')


@cs2cs_available
def test_reproject_point_matches_known_jkure_center():
    # Matches the manually-verified center point from docs-src/discovery-report.md
    # (142.45593915, 44.24140921), computed independently there via the same cs2cs call.
    lon, lat = reproject_point(16448.83, 26842.03, "2454")
    assert lon == pytest.approx(142.45593915, abs=1e-6)
    assert lat == pytest.approx(44.24140921, abs=1e-6)


@cs2cs_available
def test_reproject_bbox_to_wgs84_ring_is_closed_and_matches_known_tile():
    # The real 12JE14 tile bbox in EPSG:2454, and its independently-verified corner.
    ring = reproject_bbox_to_wgs84_ring(16000, 26684.06, 16897.66, 27000, "2454")
    assert len(ring) == 5
    assert ring[0] == ring[-1]  # closed ring
    assert ring[0][0] == pytest.approx(142.45031501, abs=1e-6)
    assert ring[0][1] == pytest.approx(44.23999742, abs=1e-6)
