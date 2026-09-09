"""CLI entry point: `python -m adopt_hokkaido_lidar <verb>`.

Runnable directly without `just`; the justfile is a thin wrapper around this.
Only the verbs implemented so far are wired in -- unimplemented verbs from
the startup spec's full command surface will be added as their underlying
modules land.
"""

from __future__ import annotations

import argparse
import sys
import time

from . import arcgis_search, batch, catalog, db, ingest, publish
from .attribution import build_standard_attribution, record_attribution

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
    try:
        items = ingest.ingest_arcgis_source_package(conn, args.item_id, args.work_dir)
    except (ValueError, ingest.NoRawMembersFound) as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"ingested {len(items)} member(s) from {args.item_id}:")
    for asset_id, raw_stem, result in items:
        print(f"  {asset_id}: {result.point_count} points, sha256={result.sha256}, crs={result.crs_wkt}")
        print(f"    raw_stem for publish: {raw_stem}")
    return 0


def cmd_build_catalog(args: argparse.Namespace) -> int:
    conn = db.connect(args.db_path)
    try:
        pmtiles_url, manifest_url = catalog.publish_catalog(conn, args.work_dir)
    finally:
        conn.close()
    print(f"published catalog: {pmtiles_url}")
    print(f"published manifest: {manifest_url}")
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


def cmd_process_jkure_batch(args: argparse.Namespace) -> int:
    """Ingest -> confirm-provenance -> publish every remaining Jクレ item, one at a time.

    Safe to interrupt (Ctrl-C) and re-run -- picks up wherever it left off,
    since it only ever looks at what's not yet published.
    """
    conn = db.connect(args.db_path)

    def on_item_done(i: int, total: int, result) -> None:
        print(f"[{i}/{total}] {result.package_id} -> {result.outcome}: {result.detail}")

    try:
        summary = batch.run_batch(
            conn,
            args.work_dir,
            vertical_datum=args.vertical_datum,
            organization=args.organization,
            license_id=args.license,
            delay_seconds=args.delay_seconds,
            limit=args.limit,
            on_item_done=on_item_done,
        )
    finally:
        conn.close()

    print(f"\npublished {summary.published_count} / {len(summary.results)} attempted")
    if summary.stopped_early:
        print(f"STOPPED EARLY: {summary.stop_reason}", file=sys.stderr)
        return 3
    errors = [r for r in summary.results if r.outcome == "error"]
    if errors:
        print(f"{len(errors)} item(s) errored (see log above) -- re-run to retry", file=sys.stderr)
        return 1
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

    p_catalog = sub.add_parser("build-catalog", help="Rebuild and upload catalog/index.pmtiles + manifest.jsonl.")
    p_catalog.add_argument("--db-path", default="state.sqlite3")
    p_catalog.add_argument("--work-dir", default=".work")
    p_catalog.set_defaults(func=cmd_build_catalog)

    p_batch = sub.add_parser(
        "process-jkure-batch", help="Ingest+confirm+publish every remaining Jクレ item, one at a time."
    )
    p_batch.add_argument("--vertical-datum", required=True)
    p_batch.add_argument("--organization", required=True)
    p_batch.add_argument("--license", required=True)
    p_batch.add_argument("--delay-seconds", type=float, default=batch.DEFAULT_DELAY_SECONDS)
    p_batch.add_argument("--limit", type=int, default=None, help="Process at most this many items, then stop.")
    p_batch.add_argument("--db-path", default="state.sqlite3")
    p_batch.add_argument("--work-dir", default=".work")
    p_batch.set_defaults(func=cmd_process_jkure_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
