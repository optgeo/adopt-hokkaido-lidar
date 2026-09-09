"""Pre-extraction ZIP safety checks: Zip Slip, path traversal, symlinks, zip bombs.

Every ORIGINAL LAZ package is a ZIP downloaded from a source we don't control.
These checks run against zipfile.ZipInfo metadata *before* any extraction --
extraction itself must never begin until a member list has passed all of them.
"""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass

# A symlink's Unix mode bits, as packed into ZipInfo.external_attr's high 16 bits.
_S_IFLNK = 0o120000
_S_IFMT = 0o170000

DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024  # 20 GiB
DEFAULT_MAX_COMPRESSION_RATIO = 100  # uncompressed / compressed


@dataclass(frozen=True)
class ZipSafetyViolation:
    member: str
    reason: str


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & _S_IFMT) == _S_IFLNK


def _escapes_root(member_name: str) -> bool:
    # Reject absolute paths outright; normalize the rest and check it can't
    # climb above the extraction root.
    if member_name.startswith("/") or member_name.startswith("\\"):
        return True
    normalized = posixpath.normpath(member_name)
    return normalized == ".." or normalized.startswith("../")


def check_members(
    infos: list[zipfile.ZipInfo],
    *,
    max_total_uncompressed_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
) -> list[ZipSafetyViolation]:
    """Check a ZIP's member list for unsafe entries.

    Returns a list of violations (empty = safe to extract). Never raises for
    a "normal" unsafe zip -- callers decide whether to abort; this only
    collects facts.
    """
    violations: list[ZipSafetyViolation] = []
    total_uncompressed = 0

    for info in infos:
        name = info.filename

        if _escapes_root(name):
            violations.append(ZipSafetyViolation(name, "path escapes extraction root (Zip Slip / traversal)"))
            continue

        if _is_symlink(info):
            violations.append(ZipSafetyViolation(name, "symlink entry"))
            continue

        total_uncompressed += info.file_size

        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > max_compression_ratio:
                violations.append(
                    ZipSafetyViolation(
                        name,
                        f"compression ratio {ratio:.0f}:1 exceeds limit {max_compression_ratio}:1 (possible zip bomb)",
                    )
                )

    if total_uncompressed > max_total_uncompressed_bytes:
        violations.append(
            ZipSafetyViolation(
                "<archive total>",
                f"total uncompressed size {total_uncompressed} bytes exceeds limit {max_total_uncompressed_bytes}",
            )
        )

    return violations
