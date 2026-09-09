"""CLI entry point: `python -m adopt_hokkaido_lidar <verb>`.

Runnable directly without `just`; the justfile is a thin wrapper around this.
Only the verbs implemented so far are wired in -- unimplemented verbs from
the startup spec's full command surface will be added as their underlying
modules land.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import arcgis_search, db, http_client, ingest, publish
from .attribution import build_standard_attribution, record_attribution
from .identifiers import stable_asset_id
from .zip_inspect import classify_member_format, find_raw_point_members, parse_central_directory

JKURE_TAG = "上川北部・網走西部Jクレ"


def cmd_init_db(args: argparse.Namespace) -> int:
    conn = db.connect(args.db_path)
    conn.close()
    print(f"initialized schema at {args.db_path}")
    return 0


def cmd_discover_jkure(args: argparse.Namespace) -> int:
    """Enumerate the Jクレ project's ORIGINAL LAZ items via ArcGIS org-wide tag search.

    Metadata only -- no downloads, no disk-space guard needed at this step.
    """
    conn = db.connect(args.db_path)
    items = arcgis_search.search_original_laz_by_tag(JKURE_TAG)
    print(f"found {len(items)} ORIGINAL LAZ items for tag {JKURE_TAG!r}")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "INSERT OR IGNORE INTO source_item (id, source_system, kind, project_name, hp_kind, discovered_at) "
        "VALUES ('jkure', 'arcgis', 'arcgis_hub_search', ?, 'arcgis_hub_search', ?)",
        (JKURE_TAG, now),
    )

    inserted = 0
    for item in items:
        conn.execute(
            "INSERT OR IGNORE INTO source_package "
            "(id, source_item_id, source_system, license_id, fetched_at, raw_json) "
            "VALUES (?, 'jkure', 'arcgis', ?, ?, ?)",
            (item.item_id, item.license_info, now, str(item.tags)),
        )
        member_path_guess = item.title  # resolved precisely at ingest time via zip_inspect
        member_id = f"{item.item_id}::member"
        conn.execute(
            "INSERT OR IGNORE INTO source_member "
            "(id, source_package_id, resource_name, resource_format, resource_url, is_original_laz_candidate) "
            "VALUES (?, ?, ?, 'ZIP', ?, 1)",
            (member_id, item.item_id, member_path_guess, arcgis_search.item_data_url(item.item_id)),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"recorded {inserted} source_package/source_member rows under source_item 'jkure'")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    conn = db.connect(args.db_path)
    row = conn.execute(
        "SELECT sp.id, sm.id, sm.resource_url FROM source_package sp "
        "JOIN source_member sm ON sm.source_package_id = sp.id WHERE sp.id = ?",
        (args.item_id,),
    ).fetchone()
    if row is None:
        print(f"no source_package/source_member found for item {args.item_id!r}; run discover-jkure first", file=sys.stderr)
        return 1
    package_id, member_id, data_url = row

    final_url, total_size = http_client.resolve_download(data_url)

    tail = http_client.fetch_tail(final_url, total_size, ingest.TAIL_FETCH_BYTES)
    members = parse_central_directory(tail.body)
    raw_members = find_raw_point_members(members)
    if len(raw_members) != 1:
        print(
            f"expected exactly 1 raw point member in {args.item_id}, found {len(raw_members)}: "
            f"{[m.name for m in raw_members]} -- refusing to guess which one",
            file=sys.stderr,
        )
        return 1
    member = raw_members[0]

    raw_stem = os.path.splitext(os.path.basename(member.name))[0].lower()
    asset_id = stable_asset_id("arcgis", package_id, member.name)

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

    print(f"ingesting {asset_id} ({member.name}, {member.uncompressed_size} bytes uncompressed)...")
    result = ingest.ingest_member(
        zip_url=final_url,
        zip_total_size=total_size,
        member_path=member.name,
        asset_id=asset_id,
        work_dir=args.work_dir,
    )
    ingest.record_ingest_result(conn, result, asset_id=asset_id)
    conn.close()

    print(f"ingested {asset_id}: {result.point_count} points, sha256={result.sha256}")
    print(f"crs: {result.crs_wkt}")
    print(f"raw_stem for publish: {raw_stem}")
    return 0


def cmd_confirm_provenance(args: argparse.Namespace) -> int:
    """Record the human-confirmed vertical datum and standard attribution for one asset.

    This is the deliberate human-review step the publish gate exists to
    force (docs-src/provenance-policy.md) -- it never runs automatically as
    part of ingest.
    """
    conn = db.connect(args.db_path)

    updated = conn.execute(
        "UPDATE derived_asset_version SET vertical_datum = ? "
        "WHERE id = (SELECT id FROM derived_asset_version WHERE asset_id = ? ORDER BY version DESC LIMIT 1)",
        (args.vertical_datum, args.asset_id),
    ).rowcount
    if updated == 0:
        print(f"no derived_asset_version found for {args.asset_id}; run ingest first", file=sys.stderr)
        return 1

    records = build_standard_attribution(organization_title=args.organization, license_id=args.license)
    record_attribution(conn, args.asset_id, records)
    conn.commit()
    conn.close()

    print(f"recorded vertical_datum and {len(records)} attribution rows for {args.asset_id}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    conn = db.connect(args.db_path)
    try:
        url = publish.publish_asset(
            conn,
            args.asset_id,
            source_system=args.source_system,
            source_package_id=args.source_package_id,
            raw_stem=args.raw_stem,
        )
    except publish.PublishBlocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print(f"published: {url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adopt-hokkaido-lidar")
    sub = parser.add_subparsers(dest="verb", required=True)

    p_init_db = sub.add_parser("init-db", help="Create/upgrade the local SQLite state database.")
    p_init_db.add_argument("--db-path", default="state.sqlite3")
    p_init_db.set_defaults(func=cmd_init_db)

    p_discover = sub.add_parser("discover-jkure", help="Enumerate the Jクレ project's ORIGINAL LAZ items (ArcGIS).")
    p_discover.add_argument("--db-path", default="state.sqlite3")
    p_discover.set_defaults(func=cmd_discover_jkure)

    p_ingest = sub.add_parser("ingest", help="Download, convert, and validate one ArcGIS item's LAZ member.")
    p_ingest.add_argument("item_id", help="ArcGIS item id (from discover-jkure)")
    p_ingest.add_argument("--db-path", default="state.sqlite3")
    p_ingest.add_argument("--work-dir", default=".work")
    p_ingest.set_defaults(func=cmd_ingest)

    p_confirm = sub.add_parser(
        "confirm-provenance", help="Record human-confirmed vertical datum and attribution for one asset."
    )
    p_confirm.add_argument("asset_id")
    p_confirm.add_argument("--vertical-datum", required=True)
    p_confirm.add_argument("--organization", required=True, help="Responsible department, e.g. 道有林課")
    p_confirm.add_argument("--license", required=True, help="e.g. CC-BY")
    p_confirm.add_argument("--db-path", default="state.sqlite3")
    p_confirm.set_defaults(func=cmd_confirm_provenance)

    p_publish = sub.add_parser("publish", help="Publish a validated asset to Source Cooperative (gated).")
    p_publish.add_argument("asset_id")
    p_publish.add_argument("--source-system", required=True, choices=["ckan", "arcgis"])
    p_publish.add_argument("--source-package-id", required=True)
    p_publish.add_argument("--raw-stem", required=True)
    p_publish.add_argument("--db-path", default="state.sqlite3")
    p_publish.set_defaults(func=cmd_publish)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
