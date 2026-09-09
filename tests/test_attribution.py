import pytest

from adopt_hokkaido_lidar import db
from adopt_hokkaido_lidar.attribution import build_standard_attribution, record_attribution


def test_build_standard_attribution_covers_all_three_gate_scopes():
    records = build_standard_attribution(organization_title="道有林課", license_id="CC-BY")
    scopes = {r.scope for r in records}
    assert scopes == {"source_data", "processing", "hosting"}


def test_build_standard_attribution_source_data_carries_department_and_license():
    records = build_standard_attribution(organization_title="道有林課", license_id="CC-BY")
    source_data = next(r for r in records if r.scope == "source_data")
    assert "道有林課" in source_data.text
    assert source_data.license_id == "CC-BY"


def test_build_standard_attribution_rejects_empty_organization():
    with pytest.raises(ValueError, match="organization_title"):
        build_standard_attribution(organization_title="", license_id="CC-BY")


def test_build_standard_attribution_rejects_empty_license():
    with pytest.raises(ValueError, match="license_id"):
        build_standard_attribution(organization_title="道有林課", license_id="")


def test_build_standard_attribution_does_not_hardcode_a_different_department():
    # Regression guard for the "never generalize to 北海道庁" rule
    # (docs-src/attribution.md) -- two different projects' departments must
    # not collapse into the same text.
    a = build_standard_attribution(organization_title="道有林課", license_id="CC-BY")
    b = build_standard_attribution(organization_title="総合政策部", license_id="CC-BY")
    a_source = next(r for r in a if r.scope == "source_data").text
    b_source = next(r for r in b if r.scope == "source_data").text
    assert a_source != b_source


def test_record_attribution_persists_and_is_idempotent(tmp_path):
    conn = db.connect(str(tmp_path / "s.sqlite3"))
    conn.execute(
        "INSERT INTO source_item (id, source_system, kind, hp_kind, discovered_at) "
        "VALUES ('si1', 'arcgis', 'arcgis_item', 'arcgis_hub_search', 'now')"
    )
    conn.execute(
        "INSERT INTO source_package (id, source_item_id, source_system, fetched_at, raw_json) "
        "VALUES ('sp1', 'si1', 'arcgis', 'now', '{}')"
    )
    conn.execute(
        "INSERT INTO source_member (id, source_package_id, resource_name, resource_format, resource_url) "
        "VALUES ('sm1', 'sp1', 'x', 'ZIP', 'https://example/x.zip')"
    )
    conn.execute(
        "INSERT INTO logical_asset (asset_id, source_member_id, raw_member_path) VALUES ('a1', 'sm1', 'x.laz')"
    )
    conn.commit()

    records = build_standard_attribution(organization_title="道有林課", license_id="CC-BY")
    record_attribution(conn, "a1", records)

    rows = conn.execute("SELECT scope, text, license_id FROM attribution WHERE asset_id = 'a1'").fetchall()
    assert len(rows) == 3

    # Re-running must not duplicate rows (replaces, doesn't append).
    record_attribution(conn, "a1", records)
    rows_again = conn.execute("SELECT scope FROM attribution WHERE asset_id = 'a1'").fetchall()
    assert len(rows_again) == 3
