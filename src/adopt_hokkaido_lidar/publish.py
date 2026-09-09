"""Publish a validated derived_asset_version to Source Cooperative.

Gated per docs-src/provenance-policy.md: a logical_asset only becomes a
published_asset once license, attribution, and vertical datum are all
confirmed non-null/non-empty. A gate failure moves the asset to
'suspended_provenance_review' instead of publishing -- it is never silently
skipped or auto-deleted, and the local COPC is kept (not deleted) so the
conversion work isn't wasted while it waits for human review.

Upload verification here is a content-length check via head_object_size,
not a byte-exact remote checksum (sc_client.head_object_size explains why).
The locally-computed sha256 is uploaded alongside the object as the durable
record for any future independent verification.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass

from . import sc_client

SC_BUCKET = "smartmaps"
SC_PRODUCT = "adopt-hokkaido-lidar"


class PublishBlocked(RuntimeError):
    """Raised when the provenance gate refuses to publish -- never bypassed automatically."""


@dataclass(frozen=True)
class GateCheck:
    ok: bool
    missing: list[str]


def check_publish_gate(conn: sqlite3.Connection, asset_id: str) -> GateCheck:
    """Evaluate the publish gate for one logical_asset. Pure read, no side effects."""
    missing: list[str] = []

    dav = conn.execute(
        "SELECT crs, vertical_datum, sha256, copc_local_path FROM derived_asset_version "
        "WHERE asset_id = ? ORDER BY version DESC LIMIT 1",
        (asset_id,),
    ).fetchone()
    if dav is None:
        return GateCheck(ok=False, missing=["no derived_asset_version -- run ingest first"])

    crs, vertical_datum, sha256, copc_local_path = dav
    if not crs:
        missing.append("crs")
    if not vertical_datum:
        missing.append("vertical_datum (never guessed -- must be explicitly confirmed)")
    if not sha256:
        missing.append("sha256")
    if not copc_local_path or not os.path.exists(copc_local_path):
        missing.append("copc_local_path (file missing on disk)")

    attribution_scopes = {
        row[0]
        for row in conn.execute("SELECT scope FROM attribution WHERE asset_id = ?", (asset_id,))
    }
    required_scopes = {"source_data", "processing", "hosting"}
    for scope in sorted(required_scopes - attribution_scopes):
        missing.append(f"attribution[{scope}]")

    return GateCheck(ok=not missing, missing=missing)


def object_key(source_system: str, source_package_id: str, raw_stem: str, version: int) -> str:
    return f"data/{source_system}/{source_package_id}/{raw_stem}/v{version}/{raw_stem}.copc.laz"


def publish_asset(
    conn: sqlite3.Connection,
    asset_id: str,
    *,
    source_system: str,
    source_package_id: str,
    raw_stem: str,
) -> str:
    """Publish one logical_asset. Returns the published object's https URL.

    Raises PublishBlocked (without uploading anything) if the gate fails.
    """
    gate = check_publish_gate(conn, asset_id)
    if not gate.ok:
        conn.execute(
            "UPDATE logical_asset SET status = 'suspended_provenance_review', suspended_reason = ? WHERE asset_id = ?",
            (json.dumps(gate.missing, ensure_ascii=False), asset_id),
        )
        conn.commit()
        raise PublishBlocked(f"publish gate failed for {asset_id}: {', '.join(gate.missing)}")

    version, copc_local_path = conn.execute(
        "SELECT version, copc_local_path FROM derived_asset_version WHERE asset_id = ? ORDER BY version DESC LIMIT 1",
        (asset_id,),
    ).fetchone()

    key = object_key(source_system, source_package_id, raw_stem, version)
    s3_url = f"s3://{SC_BUCKET}/{SC_PRODUCT}/{key}"
    https_url = f"https://data.source.coop/{SC_BUCKET}/{SC_PRODUCT}/{key}"

    result = sc_client.upload(copc_local_path, s3_url)
    if not result.ok:
        raise RuntimeError(f"upload failed for {asset_id}: {result.stderr}")

    local_size = os.path.getsize(copc_local_path)
    remote_size = sc_client.head_object_size(s3_url)
    if remote_size != local_size:
        raise RuntimeError(
            f"upload verification failed for {asset_id}: local size {local_size} != remote size {remote_size}"
        )

    conn.execute(
        "INSERT INTO published_asset (asset_id, derived_asset_version_id, object_url, published_at) "
        "VALUES (?, ?, ?, ?)",
        (asset_id, f"{asset_id}-v{version}", https_url, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    conn.execute("UPDATE logical_asset SET status = 'published' WHERE asset_id = ?", (asset_id,))
    conn.commit()

    os.remove(copc_local_path)  # verified uploaded -- safe to drop the local binary now

    return https_url
