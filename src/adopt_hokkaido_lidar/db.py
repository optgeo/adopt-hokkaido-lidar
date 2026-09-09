"""SQLite schema for the 9-entity state model.

DRAFT: the startup spec gave an exhaustive, verbatim field list per entity.
This module implements a reasonable first cut of that schema based on the
entity names and roles as understood during Phase 0, but has not been
reconciled field-by-field against the original spec text. Treat every
column list here as provisional until that reconciliation happens --
do not build Phase 1 ingestion logic that assumes this schema is final.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_item (
    id TEXT PRIMARY KEY,                 -- ArcGIS Item id or equivalent
    kind TEXT NOT NULL,                  -- 'coverage_feature' | 'arcgis_item' | ...
    advisory_no TEXT,
    project_name TEXT,
    hp_url TEXT,
    hp_kind TEXT NOT NULL,               -- ckan | arcgis_hub_search | empty | unknown
    discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_package (
    id TEXT PRIMARY KEY,                 -- CKAN package name, or equivalent
    source_item_id TEXT NOT NULL REFERENCES source_item(id),
    license_id TEXT,
    organization_title TEXT,
    notes TEXT,
    fetched_at TEXT NOT NULL,
    raw_json TEXT NOT NULL               -- full package_show response, for audit
);

CREATE TABLE IF NOT EXISTS source_member (
    id TEXT PRIMARY KEY,                 -- source_package_id + resource url hash
    source_package_id TEXT NOT NULL REFERENCES source_package(id),
    resource_name TEXT NOT NULL,
    resource_format TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    is_original_laz_candidate INTEGER NOT NULL DEFAULT 0,
    laz_member_path TEXT                 -- path of the .laz file inside the zip, once inspected
);

CREATE TABLE IF NOT EXISTS logical_asset (
    asset_id TEXT PRIMARY KEY,           -- identifiers.stable_asset_id(...)
    source_member_id TEXT NOT NULL REFERENCES source_member(id),
    laz_member_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (status IN (
            'discovered', 'validated', 'published',
            'suspended_provenance_review'
        )),
    suspended_reason TEXT
);

CREATE TABLE IF NOT EXISTS derived_asset_version (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES logical_asset(asset_id),
    version INTEGER NOT NULL,
    copc_local_path TEXT,
    sha256 TEXT,
    point_count INTEGER,
    crs TEXT,
    vertical_datum TEXT,
    validated_at TEXT,
    validation_report TEXT,              -- JSON blob
    UNIQUE (asset_id, version)
);

CREATE TABLE IF NOT EXISTS published_asset (
    asset_id TEXT PRIMARY KEY REFERENCES logical_asset(asset_id),
    derived_asset_version_id TEXT NOT NULL REFERENCES derived_asset_version(id),
    object_url TEXT NOT NULL UNIQUE,     -- immutable
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS footprint (
    asset_id TEXT PRIMARY KEY REFERENCES logical_asset(asset_id),
    bbox_minx REAL NOT NULL,
    bbox_miny REAL NOT NULL,
    bbox_maxx REAL NOT NULL,
    bbox_maxy REAL NOT NULL,
    geometry_geojson TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attribution (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES logical_asset(asset_id),
    scope TEXT NOT NULL
        CHECK (scope IN (
            'source_data', 'basemap', 'elevation',
            'processing', 'hosting', 'external_viewer'
        )),
    text TEXT NOT NULL,
    license_id TEXT
);

CREATE TABLE IF NOT EXISTS provenance_link (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES logical_asset(asset_id),
    from_entity TEXT NOT NULL,           -- e.g. 'source_member'
    from_id TEXT NOT NULL,
    to_entity TEXT NOT NULL,             -- e.g. 'derived_asset_version'
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,              -- e.g. 'converted_from', 'validated_by'
    recorded_at TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
