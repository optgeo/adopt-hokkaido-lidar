"""Inspect a remote ZIP's member list without downloading the whole archive.

A resource being named "original.zip" / "オリジナルデータ" does NOT mean it
contains .laz files -- confirmed the hard way on h25oribegawasabou, whose
"original.zip" turned out to contain plain-text XYZ point CSVs, not LAZ.
The only reliable way to know is to read the ZIP's central directory, which
sits at the end of the file and is tiny (a few KB) even for a many-GB
archive -- fetchable with one or two HTTP range requests, never a full
download. This module does the *parsing* half (pure, offline, unit-tested
against zipfile-constructed fixtures); the range-request fetching half
belongs to Phase 1's HTTP client, not here.
"""

from __future__ import annotations

from dataclasses import dataclass

EOCD_SIGNATURE = b"PK\x05\x06"
CENTRAL_DIR_SIGNATURE = b"PK\x01\x02"

RAW_FORMAT_LAS = "las"
RAW_FORMAT_TEXT_CSV = "text_csv"
RAW_FORMAT_UNKNOWN = "unknown"

_LAS_EXTENSIONS = (".laz", ".las")
_TEXT_EXTENSIONS = (".txt", ".csv")


@dataclass(frozen=True)
class ZipMember:
    name: str
    compression_method: int
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int

    @property
    def is_directory(self) -> bool:
        return self.name.endswith("/") and self.uncompressed_size == 0


class CentralDirectoryNotFound(ValueError):
    """Raised when no End-Of-Central-Directory record is found in the given tail bytes.

    Usually means the caller didn't fetch enough of the file's tail --
    EOCD is always in the last 65KB+22 bytes (ZIP comment can be up to 65535
    bytes), so a short read near the very end of a huge file can miss it.
    """


def find_eocd(tail_bytes: bytes) -> tuple[int, int, int]:
    """Locate the End-Of-Central-Directory record in a buffer covering the file's tail.

    Returns (central_dir_size, central_dir_offset_from_file_start, total_entries).
    """
    idx = tail_bytes.rfind(EOCD_SIGNATURE)
    if idx == -1:
        raise CentralDirectoryNotFound("no EOCD record found in the given tail bytes; fetch more of the file's end")
    total_entries = int.from_bytes(tail_bytes[idx + 10 : idx + 12], "little")
    cd_size = int.from_bytes(tail_bytes[idx + 12 : idx + 16], "little")
    cd_offset = int.from_bytes(tail_bytes[idx + 16 : idx + 20], "little")
    return cd_size, cd_offset, total_entries


def parse_central_directory(tail_bytes: bytes) -> list[ZipMember]:
    """Parse every central-directory file header found in the given buffer.

    `tail_bytes` must be a buffer covering at least the full central
    directory plus the EOCD record (i.e. everything from central_dir_offset
    to end-of-file) -- typically obtained by range-fetching a fixed-size
    tail (e.g. the last 256KB) and, if find_eocd's reported cd_size exceeds
    what was fetched, re-fetching exactly [cd_offset, end-of-file).

    Entries are returned in on-disk order (this is also insertion order for
    ordinary zip writers, but that's not guaranteed by the format itself).
    """
    members: list[ZipMember] = []
    pos = 0
    while True:
        pos = tail_bytes.find(CENTRAL_DIR_SIGNATURE, pos)
        if pos == -1:
            break
        comp_method = int.from_bytes(tail_bytes[pos + 10 : pos + 12], "little")
        comp_size = int.from_bytes(tail_bytes[pos + 20 : pos + 24], "little")
        uncomp_size = int.from_bytes(tail_bytes[pos + 24 : pos + 28], "little")
        name_len = int.from_bytes(tail_bytes[pos + 28 : pos + 30], "little")
        extra_len = int.from_bytes(tail_bytes[pos + 30 : pos + 32], "little")
        comment_len = int.from_bytes(tail_bytes[pos + 32 : pos + 34], "little")
        local_offset = int.from_bytes(tail_bytes[pos + 42 : pos + 46], "little")
        name = tail_bytes[pos + 46 : pos + 46 + name_len].decode("utf-8", errors="replace")
        members.append(
            ZipMember(
                name=name,
                compression_method=comp_method,
                compressed_size=comp_size,
                uncompressed_size=uncomp_size,
                local_header_offset=local_offset,
            )
        )
        pos += 46 + name_len + extra_len + comment_len
    return members


def classify_member_format(filename: str) -> str:
    """Classify a zip member by its extension.

    Deliberately extension-only (not content-sniffed) at this stage --
    good enough to route to the right PDAL reader stage (readers.las vs
    readers.text) later, without pretending to more certainty than a
    filename actually gives. Anything unrecognized comes back as
    RAW_FORMAT_UNKNOWN rather than being guessed into one of the two.
    """
    lower = filename.lower()
    if lower.endswith(_LAS_EXTENSIONS):
        return RAW_FORMAT_LAS
    if lower.endswith(_TEXT_EXTENSIONS):
        return RAW_FORMAT_TEXT_CSV
    return RAW_FORMAT_UNKNOWN


def find_raw_point_members(members: list[ZipMember]) -> list[ZipMember]:
    """Filter a member list down to non-directory entries with a recognized raw-point format."""
    return [
        m
        for m in members
        if not m.is_directory and classify_member_format(m.name) != RAW_FORMAT_UNKNOWN
    ]
