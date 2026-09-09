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


def stable_asset_id(ckan_package_name: str, laz_member_path: str) -> str:
    """Derive a stable asset_id from a CKAN package name and a LAZ member path.

    Format: "<slugified-package-name>-<12 hex chars of sha256(member path)>".
    The hash covers the *full* member path (not just the stem) so that two
    same-named LAZ files in different subdirectories of the same zip never
    collide.
    """
    if not ckan_package_name:
        raise ValueError("ckan_package_name must not be empty")
    if not laz_member_path:
        raise ValueError("laz_member_path must not be empty")
    digest = hashlib.sha256(laz_member_path.encode("utf-8")).hexdigest()[:12]
    return f"{_slugify(ckan_package_name)}-{digest}"
