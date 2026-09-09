from adopt_hokkaido_lidar.http_client import USER_AGENT, compute_backoff_delay


def test_backoff_delay_doubles_each_attempt():
    assert compute_backoff_delay(0, None, base_delay=1.0) == 1.0
    assert compute_backoff_delay(1, None, base_delay=1.0) == 2.0
    assert compute_backoff_delay(2, None, base_delay=1.0) == 4.0


def test_backoff_delay_honors_retry_after_over_computed_value():
    assert compute_backoff_delay(3, retry_after=2.0, base_delay=1.0) == 2.0


def test_user_agent_carries_repo_url_and_no_personal_contact():
    assert "github.com/optgeo/adopt-hokkaido-lidar" in USER_AGENT
    assert "@" not in USER_AGENT  # no email address embedded, per project decision
