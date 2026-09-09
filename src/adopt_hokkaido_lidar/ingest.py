"""Ingest one raw point file: range-download its zip member, convert to COPC, validate.

Orchestrates zip_inspect + http_client + pdal_pipeline + disk_guard against
one target member. Does not touch Source Cooperative -- that's publish.py's
job, gated on this step's output (docs-src/provenance-policy.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import zlib
from dataclasses import dataclass

from . import http_client
from .disk_guard import DEFAULT_MIN_FREE_BYTES, check_free_space_at
from .pdal_pipeline import build_copc_pipeline, probe_metadata, run_pipeline
from .reproject import extract_epsg_from_projcs_wkt, reproject_bbox_to_wgs84_ring
from .identifiers import stable_asset_id
from .zip_inspect import (
    ZipMember,
    classify_member_format,
    find_eocd,
    find_raw_point_members,
    member_byte_range,
    parse_central_directory,
)

# Working assumption for peak local footprint per in-flight item: the raw
# decompressed member plus the COPC output, with headroom -- see PLAN.md
# "ディスク容量ガード付きの逐次ingest/publish".
_FOOTPRINT_MULTIPLIER = 3
TAIL_FETCH_BYTES = 262_144  # matches the range used against the real zips in Phase 0


class IngestBlocked(RuntimeError):
    """Raised when disk space or another precondition refuses to start this item."""


@dataclass(frozen=True)
class IngestResult:
    asset_id: str
    copc_path: str
    sha256: str
    point_count: int
    crs_wkt: str | None
    source_format: str
    validation_report_path: str
    footprint_ring_wgs84: list[list[float]] | None = None


def _decompress_member(zip_member_bytes: bytes) -> bytes:
    """Parse the local file header at the start of a ranged member fetch and inflate its data.

    Mirrors the manual curl+zlib procedure validated by hand against the
    real h25oribegawasabou and Jクレ zips (docs-src/discovery-report.md).
    """
    name_len = int.from_bytes(zip_member_bytes[26:28], "little")
    extra_len = int.from_bytes(zip_member_bytes[28:30], "little")
    compression_method = int.from_bytes(zip_member_bytes[8:10], "little")
    data_start = 30 + name_len + extra_len
    data = zip_member_bytes[data_start:]
    if compression_method == 0:
        return data
    if compression_method == 8:
        return zlib.decompressobj(-15).decompress(data)
    raise ValueError(f"unsupported zip compression method {compression_method}")


def inspect_zip_member(zip_url: str, total_size: int, member_path: str) -> ZipMember:
    """Fetch just the tail of a remote zip and return the ZipMember matching `member_path`."""
    tail = http_client.fetch_tail(zip_url, total_size, TAIL_FETCH_BYTES)
    members = parse_central_directory(tail.body)
    for m in members:
        if m.name == member_path:
            return m
    raise ValueError(f"member {member_path!r} not found in zip central directory ({len(members)} entries)")


def ingest_member(
    *,
    zip_url: str,
    zip_total_size: int,
    member_path: str,
    asset_id: str,
    work_dir: str,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
) -> IngestResult:
    """Download one zip member (ranged, not the whole archive), convert to COPC, validate.

    Raises IngestBlocked without touching the network if disk space is
    insufficient. Leaves exactly one file behind on success: `<asset_id>.copc.laz`
    in work_dir, alongside its validation_report.json -- the caller
    (publish.py) is responsible for uploading and then deleting these.
    """
    os.makedirs(work_dir, exist_ok=True)

    tail = http_client.fetch_tail(zip_url, zip_total_size, TAIL_FETCH_BYTES)
    members = parse_central_directory(tail.body)
    _, cd_offset, _ = find_eocd(tail.body)
    target = next((m for m in members if m.name == member_path), None)
    if target is None:
        raise ValueError(f"member {member_path!r} not found in zip central directory")

    required_bytes = target.uncompressed_size * _FOOTPRINT_MULTIPLIER
    check = check_free_space_at(work_dir, required_bytes, min_free_bytes)
    if not check.ok:
        raise IngestBlocked(
            f"refusing to download {member_path}: free={check.free_bytes} "
            f"required={check.required_bytes} threshold={check.threshold_bytes}"
        )

    start, end = member_byte_range(target, members, cd_offset)
    ranged = http_client.fetch_range(zip_url, start, end)
    raw_bytes = _decompress_member(ranged.body)
    if len(raw_bytes) != target.uncompressed_size:
        raise ValueError(
            f"decompressed size mismatch for {member_path}: expected {target.uncompressed_size}, got {len(raw_bytes)}"
        )

    source_format = classify_member_format(member_path)
    if source_format == "unknown":
        raise ValueError(f"member {member_path!r} is neither a recognized LAS/LAZ nor text point format")

    raw_suffix = ".laz" if source_format == "las" else ".txt"
    raw_path = os.path.join(work_dir, f"{asset_id}.raw{raw_suffix}")
    with open(raw_path, "wb") as f:
        f.write(raw_bytes)

    copc_path = os.path.join(work_dir, f"{asset_id}.copc.laz")
    pipeline_kwargs = {}
    if source_format == "text_csv":
        raise NotImplementedError(
            "text_csv conversion needs a per-dataset confirmed column header "
            "(docs-src/discovery-report.md Section 3.1a) -- not wired into this "
            "CLI path yet; only the 'las' path is exercised so far (Jクレ priority)."
        )
    pipeline = build_copc_pipeline(raw_path, copc_path, source_format, **pipeline_kwargs)
    result = run_pipeline(pipeline)
    if not result.ok:
        raise RuntimeError(f"pdal pipeline failed for {member_path}: {result.stderr}")

    os.remove(raw_path)  # transient conversion input, not the deliverable -- safe to drop immediately

    sha256 = hashlib.sha256()
    with open(copc_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    digest = sha256.hexdigest()

    meta = probe_metadata(copc_path)["metadata"]
    crs_wkt = meta.get("spatialreference")

    footprint_ring_wgs84: list[list[float]] | None = None
    footprint_error: str | None = None
    try:
        if not crs_wkt:
            raise ValueError("no embedded CRS to reproject the footprint from")
        epsg = extract_epsg_from_projcs_wkt(crs_wkt)
        footprint_ring_wgs84 = reproject_bbox_to_wgs84_ring(
            meta["minx"], meta["miny"], meta["maxx"], meta["maxy"], epsg
        )
    except Exception as e:  # noqa: BLE001 -- footprint failure must not abort ingest; recorded, not silent
        footprint_error = str(e)

    validation_report = {
        "asset_id": asset_id,
        "source_zip_url": zip_url,
        "source_member_path": member_path,
        "source_format": source_format,
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "point_count": meta.get("count"),
        "crs_wkt": crs_wkt,
        "vertical_datum": None,
        "vertical_datum_confirmed": False,
        "sha256": digest,
        "notes": [],
    }
    if crs_wkt and "JGD2000" in crs_wkt:
        validation_report["notes"].append(
            "Embedded CRS references JGD2000, an older datum superseded by JGD2011 in "
            "2011-2014 for Japanese public surveying. This has not been confirmed as "
            "correct vs. a processing-pipeline mislabeling -- see "
            "docs-src/discovery-report.md. Flagged for human review before publish."
        )
    if footprint_error:
        validation_report["notes"].append(f"footprint reprojection failed: {footprint_error}")

    report_path = os.path.join(work_dir, f"{asset_id}.validation_report.json")
    with open(report_path, "w") as f:
        json.dump(validation_report, f, ensure_ascii=False, indent=2)

    return IngestResult(
        asset_id=asset_id,
        copc_path=copc_path,
        sha256=digest,
        point_count=meta.get("count", 0),
        crs_wkt=crs_wkt,
        source_format=source_format,
        validation_report_path=report_path,
        footprint_ring_wgs84=footprint_ring_wgs84,
    )


def record_ingest_result(conn: sqlite3.Connection, result: IngestResult, *, asset_id: str) -> None:
    """Persist the ingest result as a new derived_asset_version row and advance logical_asset.status."""
    existing = conn.execute(
        "SELECT MAX(version) FROM derived_asset_version WHERE asset_id = ?", (asset_id,)
    ).fetchone()[0]
    version = (existing or 0) + 1

    with open(result.validation_report_path) as f:
        report_text = f.read()

    conn.execute(
        "INSERT INTO derived_asset_version "
        "(id, asset_id, version, source_format, copc_local_path, sha256, point_count, crs, validation_report) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{asset_id}-v{version}",
            asset_id,
            version,
            result.source_format,
            result.copc_path,
            result.sha256,
            result.point_count,
            result.crs_wkt,
            report_text,
        ),
    )
    conn.execute("UPDATE logical_asset SET status = 'validated' WHERE asset_id = ?", (asset_id,))

    if result.footprint_ring_wgs84:
        lons = [p[0] for p in result.footprint_ring_wgs84]
        lats = [p[1] for p in result.footprint_ring_wgs84]
        geometry_geojson = json.dumps(
            {"type": "Polygon", "coordinates": [result.footprint_ring_wgs84]}
        )
        conn.execute(
            "INSERT OR REPLACE INTO footprint "
            "(asset_id, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, geometry_geojson) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (asset_id, min(lons), min(lats), max(lons), max(lats), geometry_geojson),
        )

    conn.commit()


class NoRawMembersFound(ValueError):
    """Raised when a source_package's zip has no recognizable LAS/LAZ or text point member at all.

    Refuses to guess -- this is the situation docs-src/discovery-report.md
    flags as needing human classification (e.g. h25oribegawasabou's
    "original.zip" that turned out to contain neither).
    """


def ingest_arcgis_source_package(
    conn: sqlite3.Connection, package_id: str, work_dir: str
) -> list[tuple[str, str, IngestResult]]:
    """Resolve, inspect, and ingest every raw point member of one ArcGIS-sourced source_package.

    A single zip can hold multiple mesh sub-tiles as separate LAZ members
    (confirmed live: item 01cb9198f4af4628a539631a276fff23 held 16 --
    12IE0711.laz through 12IE0744.laz). Each becomes its own
    source_member/logical_asset, since "1 LAZ = 1 COPC" is the actual
    publishing unit, not "1 zip = 1 COPC". Shared by the `ingest` CLI verb
    and batch.py. Returns a list of (asset_id, raw_stem, IngestResult), one
    per member.
    """
    row = conn.execute(
        "SELECT sm.id, sm.resource_url FROM source_member sm WHERE sm.source_package_id = ? LIMIT 1",
        (package_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"no source_member found for source_package {package_id!r}")
    placeholder_member_id, data_url = row

    final_url, total_size = http_client.resolve_download(data_url)
    tail = http_client.fetch_tail(final_url, total_size, TAIL_FETCH_BYTES)
    members = parse_central_directory(tail.body)
    raw_members = find_raw_point_members(members)
    if not raw_members:
        raise NoRawMembersFound(f"no LAS/LAZ or text point member found in {package_id}")

    results: list[tuple[str, str, IngestResult]] = []
    for i, member in enumerate(raw_members):
        member_id = placeholder_member_id if i == 0 else f"{package_id}::member::{i}"
        raw_stem = os.path.splitext(os.path.basename(member.name))[0].lower()
        asset_id = stable_asset_id("arcgis", package_id, member.name)

        already_published = conn.execute(
            "SELECT 1 FROM published_asset WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if already_published:
            continue  # resumed run: this member was already fully published, don't redo the work

        conn.execute(
            "INSERT OR IGNORE INTO source_member "
            "(id, source_package_id, resource_name, resource_format, resource_url) "
            "VALUES (?, ?, ?, 'ZIP', ?)",
            (member_id, package_id, member.name, data_url),
        )
        conn.execute(
            "UPDATE source_member SET raw_member_path = ?, raw_format = ? WHERE id = ?",
            (member.name, classify_member_format(member.name), member_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO logical_asset (asset_id, source_member_id, raw_member_path, status) "
            "VALUES (?, ?, ?, 'discovered')",
            (asset_id, member_id, member.name),
        )
        conn.commit()

        result = ingest_member(
            zip_url=final_url,
            zip_total_size=total_size,
            member_path=member.name,
            asset_id=asset_id,
            work_dir=work_dir,
        )
        record_ingest_result(conn, result, asset_id=asset_id)
        results.append((asset_id, raw_stem, result))

    return results
