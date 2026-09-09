"""Disk-space guard for the sequential ingest loop.

Approved design (PLAN.md, 2026-09-09): this machine has one internal disk
with a thin free-space margin shared with other active work, and no second
volume to fall back to. The pipeline must never assume it can hold the full
corpus locally -- it processes one item at a time and deletes local files
right after a verified upload. This module is the check that enforces the
threshold before a new download starts, rather than relying on discipline
alone.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

DEFAULT_MIN_FREE_BYTES = 20 * 1024 * 1024 * 1024  # 20 GiB, per PLAN.md


@dataclass(frozen=True)
class DiskSpaceCheck:
    free_bytes: int
    required_bytes: int
    threshold_bytes: int
    ok: bool


def check_free_space(
    free_bytes: int, required_bytes: int, threshold_bytes: int = DEFAULT_MIN_FREE_BYTES
) -> DiskSpaceCheck:
    """Decide whether it's safe to start a new download given known free space.

    Pure function over already-measured free space, so it's testable without
    touching a real filesystem. Fails safe: ok is True only when free space
    comfortably covers both the item itself and the threshold reserve --
    an item large enough to eat into the reserve is refused even if it
    would technically fit.
    """
    ok = free_bytes - required_bytes >= threshold_bytes
    return DiskSpaceCheck(
        free_bytes=free_bytes, required_bytes=required_bytes, threshold_bytes=threshold_bytes, ok=ok
    )


def check_free_space_at(
    path: str, required_bytes: int, threshold_bytes: int = DEFAULT_MIN_FREE_BYTES
) -> DiskSpaceCheck:
    """Real filesystem variant: measure free space at `path` via shutil.disk_usage."""
    free_bytes = shutil.disk_usage(path).free
    return check_free_space(free_bytes, required_bytes, threshold_bytes)
