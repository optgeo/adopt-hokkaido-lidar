import zipfile

from adopt_hokkaido_lidar.zip_safety import check_members


def _info(name, file_size=100, compress_size=100, symlink=False):
    info = zipfile.ZipInfo(name)
    info.file_size = file_size
    info.compress_size = compress_size
    if symlink:
        # Unix symlink mode (0o120000) packed into the high 16 bits of external_attr,
        # matching how zipfile itself encodes st_mode for Unix-created archives.
        info.external_attr = (0o120777 << 16)
    return info


def test_safe_members_pass_clean():
    infos = [_info("ORIGINAL/12od01.laz"), _info("ORIGINAL/12od02.laz")]
    assert check_members(infos) == []


def test_detects_zip_slip_absolute_path():
    infos = [_info("/etc/passwd")]
    violations = check_members(infos)
    assert len(violations) == 1
    assert "escapes extraction root" in violations[0].reason


def test_detects_path_traversal():
    infos = [_info("../../etc/passwd")]
    violations = check_members(infos)
    assert len(violations) == 1
    assert "escapes extraction root" in violations[0].reason


def test_detects_symlink():
    infos = [_info("ORIGINAL/sneaky", symlink=True)]
    violations = check_members(infos)
    assert len(violations) == 1
    assert "symlink" in violations[0].reason


def test_detects_zip_bomb_by_compression_ratio():
    # 1 GiB uncompressed from 1 KiB compressed -> ratio far past the default limit.
    infos = [_info("ORIGINAL/bomb.laz", file_size=1024**3, compress_size=1024)]
    violations = check_members(infos)
    assert len(violations) == 1
    assert "compression ratio" in violations[0].reason


def test_detects_total_size_over_limit():
    infos = [_info("ORIGINAL/big.laz", file_size=50, compress_size=50)]
    violations = check_members(infos, max_total_uncompressed_bytes=10)
    assert any("total uncompressed size" in v.reason for v in violations)


def test_normal_subdirectory_name_is_not_flagged_as_traversal():
    # ".." must only be rejected as a full path segment, not as a substring
    # of a legitimate directory/file name.
    infos = [_info("ORIGINAL/12..od01.laz")]
    assert check_members(infos) == []
