import json
import shutil

import pytest

from adopt_hokkaido_lidar.pdal_pipeline import build_copc_pipeline, probe_metadata, run_pipeline

pdal_available = pytest.mark.skipif(shutil.which("pdal") is None, reason="pdal executable not installed")


def test_build_copc_pipeline_las():
    pipeline = build_copc_pipeline("/tmp/in.laz", "/tmp/out.copc.laz", "las")
    assert pipeline == {
        "pipeline": [
            {"type": "readers.las", "filename": "/tmp/in.laz"},
            {"type": "writers.copc", "filename": "/tmp/out.copc.laz"},
        ]
    }


def test_build_copc_pipeline_text_csv_requires_header():
    with pytest.raises(ValueError, match="text_header"):
        build_copc_pipeline("/tmp/in.txt", "/tmp/out.copc.laz", "text_csv")


def test_build_copc_pipeline_text_csv_with_header():
    pipeline = build_copc_pipeline(
        "/tmp/in.txt", "/tmp/out.copc.laz", "text_csv", text_header="id,X,Y,Z,Classification"
    )
    reader = pipeline["pipeline"][0]
    assert reader["type"] == "readers.text"
    assert reader["header"] == "id,X,Y,Z,Classification"


def test_build_copc_pipeline_rejects_unknown_format():
    with pytest.raises(ValueError, match="unknown source_format"):
        build_copc_pipeline("/tmp/in.zip", "/tmp/out.copc.laz", "zip")


def test_build_copc_pipeline_override_srs_only_when_given():
    without = build_copc_pipeline("/tmp/in.laz", "/tmp/out.copc.laz", "las")
    assert "override_srs" not in without["pipeline"][0]

    with_srs = build_copc_pipeline("/tmp/in.laz", "/tmp/out.copc.laz", "las", override_srs="EPSG:6680")
    assert with_srs["pipeline"][0]["override_srs"] == "EPSG:6680"


@pdal_available
def test_run_pipeline_end_to_end_text_csv_to_copc(tmp_path):
    # Mirrors the real CKAN case (h25oribegawasabou): plain "id,X,Y,Z,class" rows,
    # no embedded CRS -- exercised here with a tiny synthetic dataset so the test
    # needs no network access.
    csv_path = tmp_path / "points.txt"
    lines = [f"{i},{-68413.45 + i * 0.5},{-100500.66 + i * 0.5},{89.41 + i * 0.01},1" for i in range(50)]
    csv_path.write_text("\n".join(lines) + "\n")

    out_path = tmp_path / "out.copc.laz"
    pipeline = build_copc_pipeline(
        str(csv_path),
        str(out_path),
        "text_csv",
        text_header="Id,X,Y,Z,Classification",
        override_srs="EPSG:2454",
    )
    result = run_pipeline(pipeline)

    assert result.ok, result.stderr
    assert out_path.exists()
    assert out_path.stat().st_size > 0

    meta = probe_metadata(str(out_path))
    assert meta["metadata"]["copc"] is True
    assert meta["metadata"]["count"] == 50


@pdal_available
def test_run_pipeline_reports_failure_without_raising(tmp_path):
    pipeline = build_copc_pipeline(str(tmp_path / "does-not-exist.laz"), str(tmp_path / "out.copc.laz"), "las")
    result = run_pipeline(pipeline)
    assert not result.ok
    assert result.stderr  # PDAL should explain itself on stderr


@pdal_available
def test_probe_metadata_extracts_embedded_crs(tmp_path):
    # A minimal LAS built by PDAL itself, purely to check probe_metadata's
    # plumbing (this is not the real Jクレ file -- that's investigated
    # directly in docs-src/discovery-report.md via a live range-GET, not a
    # unit test).
    csv_path = tmp_path / "points.txt"
    csv_path.write_text("1,-68413.45,-100500.66,89.41,1\n2,-68412.95,-100500.57,89.35,1\n")
    las_path = tmp_path / "sample.las"
    pipeline = {
        "pipeline": [
            {"type": "readers.text", "filename": str(csv_path), "header": "Id,X,Y,Z,Classification"},
            {"type": "writers.las", "filename": str(las_path), "a_srs": "EPSG:2454"},
        ]
    }
    result = run_pipeline(pipeline)
    assert result.ok, result.stderr

    meta = probe_metadata(str(las_path))
    assert "2454" in meta["metadata"]["spatialreference"]
