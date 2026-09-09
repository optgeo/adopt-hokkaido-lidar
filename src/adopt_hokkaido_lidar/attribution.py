"""Attribution record construction (docs-src/attribution.md).

Attribution is recorded per-scope, never as one blanket README line
(startup spec Section 35). This module builds the three scopes required by
publish.py's gate -- source_data, processing, hosting -- from facts already
established during discovery, never invented here:

  - source_data: the responsible department (source_item.responsible_department,
    e.g. "道有林課" for the Jクレ project -- confirmed from the 72-feature
    coverage GeoJSON's 担当部署 field, docs-src/discovery-report.md) and the
    license actually returned by the source system (source_package.license_id)
  - processing: this project, fixed
  - hosting: Source Cooperative, fixed

basemap/elevation/external_viewer scopes are the web map's concern
(docs-src/basemap.md, docs-src/attribution.md) and aren't produced here --
they don't vary per asset the way source_data does.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

PROCESSING_ATTRIBUTION_TEXT = "optgeo/adopt-hokkaido-lidar (https://github.com/optgeo/adopt-hokkaido-lidar)"
HOSTING_ATTRIBUTION_TEXT = "Source Cooperative (smartmaps/adopt-hokkaido-lidar, https://source.coop/smartmaps/adopt-hokkaido-lidar)"


@dataclass(frozen=True)
class AttributionRecord:
    scope: str
    text: str
    license_id: str | None = None


def build_standard_attribution(
    *, organization_title: str, license_id: str
) -> list[AttributionRecord]:
    """Build the three publish-gate-required attribution records for one asset.

    Both `organization_title` and `license_id` must come from data actually
    fetched for this asset's specific source_item/source_package -- never a
    cached default from a different project (docs-src/attribution.md: the
    department and license vary per案件 and must not be generalized to
    "北海道庁").
    """
    if not organization_title:
        raise ValueError("organization_title must not be empty -- do not default to a generic '北海道庁'")
    if not license_id:
        raise ValueError("license_id must not be empty -- confirm it from the source system, don't assume CC-BY")

    return [
        AttributionRecord(
            scope="source_data",
            text=f"{organization_title}(北海道)",
            license_id=license_id,
        ),
        AttributionRecord(scope="processing", text=PROCESSING_ATTRIBUTION_TEXT),
        AttributionRecord(scope="hosting", text=HOSTING_ATTRIBUTION_TEXT),
    ]


def record_attribution(conn: sqlite3.Connection, asset_id: str, records: list[AttributionRecord]) -> None:
    """Persist attribution records for one asset. Replaces any existing rows for the same scopes."""
    for record in records:
        conn.execute(
            "DELETE FROM attribution WHERE asset_id = ? AND scope = ?",
            (asset_id, record.scope),
        )
        conn.execute(
            "INSERT INTO attribution (id, asset_id, scope, text, license_id) VALUES (?, ?, ?, ?, ?)",
            (f"{asset_id}::{record.scope}", asset_id, record.scope, record.text, record.license_id),
        )
    conn.commit()
