"""Batch-process the Jクレ project's remaining ORIGINAL LAZ items.

One project, one fixed provenance determination (vertical datum, department,
license -- all confirmed once, in PLAN.md, for the whole Jクレ survey), so a
per-project batch runner can reuse the same confirm-provenance inputs for
every item rather than asking per-tile. Each item still goes through the
same ingest -> confirm-provenance -> publish sequence and the same publish
gate as a single manual run -- nothing here bypasses it.

Disk pressure (IngestBlocked) stops the whole batch rather than being
treated as a per-item failure to skip past -- if the guard tripped once,
the next item is no more likely to fit. Every other per-item failure is
logged and the batch moves on, since 272 items over a slow, real network
will have some transient failures.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from . import catalog
from .attribution import build_standard_attribution, record_attribution
from .ingest import IngestBlocked, NoRawMembersFound, ingest_arcgis_source_package
from .publish import PublishBlocked, publish_asset

DEFAULT_DELAY_SECONDS = 2.0


@dataclass(frozen=True)
class BatchItemResult:
    package_id: str
    asset_id: str | None
    outcome: str  # "published" | "blocked" | "error"
    detail: str


@dataclass
class BatchSummary:
    results: list[BatchItemResult] = field(default_factory=list)
    stopped_early: bool = False
    stop_reason: str | None = None

    @property
    def published_count(self) -> int:
        return sum(1 for r in self.results if r.outcome == "published")


def find_unpublished_jkure_packages(conn: sqlite3.Connection) -> list[str]:
    """List source_package ids under the Jクレ source_item not yet FULLY published.

    A package can hold multiple raw LAZ members (confirmed live: some zips
    hold 16 mesh sub-tiles, not 1) -- "done" means every member ingested so
    far has a published_asset, not just one of them. A never-ingested
    package (zero logical_assets) also counts as needing work.
    """
    rows = conn.execute(
        "SELECT sp.id FROM source_package sp "
        "WHERE sp.source_item_id = 'jkure' "
        "AND NOT ("
        "  EXISTS (SELECT 1 FROM source_member sm JOIN logical_asset la ON la.source_member_id = sm.id "
        "          WHERE sm.source_package_id = sp.id)"
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM source_member sm JOIN logical_asset la ON la.source_member_id = sm.id "
        "    LEFT JOIN published_asset pa ON pa.asset_id = la.asset_id "
        "    WHERE sm.source_package_id = sp.id AND pa.asset_id IS NULL"
        "  )"
        ") ORDER BY sp.id"
    ).fetchall()
    return [r[0] for r in rows]


def process_one(
    conn: sqlite3.Connection,
    package_id: str,
    work_dir: str,
    *,
    vertical_datum: str,
    organization: str,
    license_id: str,
) -> list[BatchItemResult]:
    """Run one package's every not-yet-published member through confirm-provenance -> publish.

    Never raises except IngestBlocked (propagated -- stops the whole batch,
    see module docstring). Returns one BatchItemResult per member the
    package's zip actually contains (already-published members are skipped
    by ingest_arcgis_source_package itself and simply don't appear here).
    """
    try:
        ingested = ingest_arcgis_source_package(conn, package_id, work_dir)
    except IngestBlocked:
        raise
    except NoRawMembersFound as e:
        return [BatchItemResult(package_id, None, "error", f"ingest: {e}")]
    except Exception as e:  # noqa: BLE001 -- one item's unexpected failure must not kill the batch
        return [BatchItemResult(package_id, None, "error", f"ingest: {type(e).__name__}: {e}")]

    if not ingested:
        return []  # every member in this package was already published on a prior run

    results = []
    for asset_id, raw_stem, _result in ingested:
        try:
            conn.execute(
                "UPDATE derived_asset_version SET vertical_datum = ? "
                "WHERE id = (SELECT id FROM derived_asset_version WHERE asset_id = ? ORDER BY version DESC LIMIT 1)",
                (vertical_datum, asset_id),
            )
            records = build_standard_attribution(organization_title=organization, license_id=license_id)
            record_attribution(conn, asset_id, records)
            conn.commit()
        except Exception as e:  # noqa: BLE001
            results.append(BatchItemResult(package_id, asset_id, "error", f"confirm-provenance: {type(e).__name__}: {e}"))
            continue

        try:
            url = publish_asset(conn, asset_id, source_system="arcgis", source_package_id=package_id, raw_stem=raw_stem)
            results.append(BatchItemResult(package_id, asset_id, "published", url))
        except PublishBlocked as e:
            results.append(BatchItemResult(package_id, asset_id, "blocked", str(e)))
        except Exception as e:  # noqa: BLE001
            results.append(BatchItemResult(package_id, asset_id, "error", f"publish: {type(e).__name__}: {e}"))

    return results


def run_batch(
    conn: sqlite3.Connection,
    work_dir: str,
    *,
    vertical_datum: str,
    organization: str,
    license_id: str,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    limit: int | None = None,
    on_item_done=None,
) -> BatchSummary:
    """Process every not-yet-published Jクレ package, rebuilding the catalog after each success.

    Safe to interrupt and re-run: find_unpublished_jkure_packages only ever
    looks at what's not yet published, so a re-run picks up where the last
    one stopped without redoing finished work.
    """
    summary = BatchSummary()
    package_ids = find_unpublished_jkure_packages(conn)
    if limit is not None:
        package_ids = package_ids[:limit]

    for i, package_id in enumerate(package_ids):
        try:
            item_results = process_one(
                conn,
                package_id,
                work_dir,
                vertical_datum=vertical_datum,
                organization=organization,
                license_id=license_id,
            )
        except IngestBlocked as e:
            summary.stopped_early = True
            summary.stop_reason = str(e)
            break

        any_published = False
        for result in item_results:
            summary.results.append(result)
            if on_item_done:
                on_item_done(i + 1, len(package_ids), result)
            if result.outcome == "published":
                any_published = True

        if any_published:
            try:
                catalog.publish_catalog(conn, work_dir)
            except Exception as e:  # noqa: BLE001 -- catalog rebuild failure shouldn't lose the publish result
                summary.results.append(BatchItemResult(package_id, None, "error", f"catalog: {e}"))

        if i + 1 < len(package_ids):
            time.sleep(delay_seconds)

    return summary
