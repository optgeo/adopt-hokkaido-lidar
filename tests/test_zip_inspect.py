import io
import zipfile

import pytest

from adopt_hokkaido_lidar.zip_inspect import (
    RAW_FORMAT_LAS,
    RAW_FORMAT_TEXT_CSV,
    RAW_FORMAT_UNKNOWN,
    CentralDirectoryNotFound,
    classify_member_format,
    find_eocd,
    find_raw_point_members,
    parse_central_directory,
)


def _build_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _tail(zip_bytes: bytes, n: int = 4096) -> bytes:
    # Mirrors what a range GET of "the last n bytes" would return.
    return zip_bytes[-n:] if len(zip_bytes) > n else zip_bytes


def test_find_eocd_matches_zipfile_reality():
    zip_bytes = _build_zip({"ORIGINAL/": b"", "ORIGINAL/a.laz": b"x" * 1000, "ORIGINAL/b_org.txt": b"1,2,3\n" * 100})
    cd_size, cd_offset, total_entries = find_eocd(_tail(zip_bytes))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert total_entries == len(zf.infolist())


def test_find_eocd_raises_when_tail_too_short_to_contain_it():
    zip_bytes = _build_zip({"a.laz": b"x" * 1000})
    # Only the first 10 bytes -- nowhere near the EOCD record at the end.
    with pytest.raises(CentralDirectoryNotFound):
        find_eocd(zip_bytes[:10])


def test_parse_central_directory_matches_zipfile_names_and_sizes():
    entries = {
        "ORIGINAL/": b"",
        "ORIGINAL/12he811.laz": b"L" * 5000,
        "ORIGINAL/13nc012_org.txt": b"1,-68413.45,-100500.66,89.41,1\r\n" * 200,
        "ORIGINAL/readme.pdf": b"P" * 300,
    }
    zip_bytes = _build_zip(entries)
    members = parse_central_directory(_tail(zip_bytes))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        expected = {i.filename: i.file_size for i in zf.infolist()}

    assert {m.name: m.uncompressed_size for m in members} == expected


def test_parse_central_directory_directory_entry_flagged():
    zip_bytes = _build_zip({"ORIGINAL/": b"", "ORIGINAL/a.laz": b"x" * 100})
    members = parse_central_directory(_tail(zip_bytes))
    by_name = {m.name: m for m in members}
    assert by_name["ORIGINAL/"].is_directory
    assert not by_name["ORIGINAL/a.laz"].is_directory


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("ORIGINAL/12he811.laz", RAW_FORMAT_LAS),
        ("ORIGINAL/12HE811.LAZ", RAW_FORMAT_LAS),  # case-insensitive
        ("ORIGINAL/legacy.las", RAW_FORMAT_LAS),
        ("ORIGINAL/13nc012_org.txt", RAW_FORMAT_TEXT_CSV),
        ("ORIGINAL/points.csv", RAW_FORMAT_TEXT_CSV),
        ("ORIGINAL/readme.pdf", RAW_FORMAT_UNKNOWN),
        ("ORIGINAL/", RAW_FORMAT_UNKNOWN),
    ],
)
def test_classify_member_format(filename, expected):
    assert classify_member_format(filename) == expected


def test_find_raw_point_members_excludes_directories_and_unknown_formats():
    zip_bytes = _build_zip(
        {
            "ORIGINAL/": b"",
            "ORIGINAL/a.laz": b"x" * 100,
            "ORIGINAL/a_org.txt": b"1,2,3\n" * 10,
            "ORIGINAL/readme.pdf": b"P" * 50,
        }
    )
    members = parse_central_directory(_tail(zip_bytes))
    raw_points = find_raw_point_members(members)
    names = {m.name for m in raw_points}
    assert names == {"ORIGINAL/a.laz", "ORIGINAL/a_org.txt"}


def test_find_raw_point_members_empty_when_zip_has_neither_laz_nor_text():
    # Models the real failure mode this module exists to catch: a resource
    # named "original.zip" that, once actually inspected, contains neither
    # LAZ/LAS nor recognizable text point data.
    zip_bytes = _build_zip({"ORIGINAL/": b"", "ORIGINAL/report.pdf": b"P" * 100})
    members = parse_central_directory(_tail(zip_bytes))
    assert find_raw_point_members(members) == []
