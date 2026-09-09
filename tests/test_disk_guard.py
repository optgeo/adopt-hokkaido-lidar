from adopt_hokkaido_lidar.disk_guard import check_free_space


def test_ok_when_plenty_of_headroom():
    result = check_free_space(free_bytes=80 * 1024**3, required_bytes=5 * 1024**3, threshold_bytes=20 * 1024**3)
    assert result.ok


def test_refuses_when_item_would_eat_into_the_reserve():
    # 25GB free, 10GB item -> only 15GB would remain, below the 20GB reserve.
    result = check_free_space(free_bytes=25 * 1024**3, required_bytes=10 * 1024**3, threshold_bytes=20 * 1024**3)
    assert not result.ok


def test_exactly_at_threshold_is_ok():
    result = check_free_space(free_bytes=25 * 1024**3, required_bytes=5 * 1024**3, threshold_bytes=20 * 1024**3)
    assert result.ok


def test_refuses_when_required_alone_exceeds_free():
    result = check_free_space(free_bytes=1024, required_bytes=2048, threshold_bytes=0)
    assert not result.ok


def test_default_threshold_is_20gib():
    from adopt_hokkaido_lidar.disk_guard import DEFAULT_MIN_FREE_BYTES

    assert DEFAULT_MIN_FREE_BYTES == 20 * 1024 * 1024 * 1024
