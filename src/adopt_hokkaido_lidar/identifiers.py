"""Stable, deterministic identifier generation.

asset_id must be the same every time it's derived from the same
(source package, LAZ member) pair, across runs and across machines --
it's the join key between logical_asset, footprint, and the PMTiles
feature's sole `asset_id` property.
"""

from __future__ import annotations

import hashlib
import re

_SAFE_CHARS = re.compile(r"[^a-z0-9_-]+")


def _slugify(value: str) -> str:
    return _SAFE_CHARS.sub("-", value.lower()).strip("-")


_VALID_SOURCE_SYSTEMS = ("ckan", "arcgis")


def stable_asset_id(source_system: str, source_package_id: str, raw_member_path: str) -> str:
    """Derive a stable asset_id from a source system, package id, and raw member path.

    source_system is included because CKAN package names and ArcGIS item ids
    are drawn from two unrelated id spaces -- without it, a CKAN package and
    an ArcGIS item that happened to share an id string would collide.

    Format: "<source_system>-<slugified-package-id>-<12 hex chars of
    sha256(member path)>". The hash covers the *full* member path (not just
    the stem) so that two same-named raw files in different subdirectories
    of the same zip never collide.
    """
    if source_system not in _VALID_SOURCE_SYSTEMS:
        raise ValueError(f"source_system must be one of {_VALID_SOURCE_SYSTEMS}, got {source_system!r}")
    if not source_package_id:
        raise ValueError("source_package_id must not be empty")
    if not raw_member_path:
        raise ValueError("raw_member_path must not be empty")
    digest = hashlib.sha256(raw_member_path.encode("utf-8")).hexdigest()[:12]
    return f"{source_system}-{_slugify(source_package_id)}-{digest}"
