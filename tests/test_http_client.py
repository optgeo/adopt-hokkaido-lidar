import urllib.error

import pytest

from adopt_hokkaido_lidar.http_client import USER_AGENT, _retry_on_transient_errors, compute_backoff_delay


def test_backoff_delay_doubles_each_attempt():
    assert compute_backoff_delay(0, None, base_delay=1.0) == 1.0
    assert compute_backoff_delay(1, None, base_delay=1.0) == 2.0
    assert compute_backoff_delay(2, None, base_delay=1.0) == 4.0


def test_backoff_delay_honors_retry_after_over_computed_value():
    assert compute_backoff_delay(3, retry_after=2.0, base_delay=1.0) == 2.0


def test_user_agent_carries_repo_url_and_no_personal_contact():
    assert "github.com/optgeo/adopt-hokkaido-lidar" in USER_AGENT
    assert "@" not in USER_AGENT  # no email address embedded, per project decision


def _http_error(code):
    return urllib.error.HTTPError("https://example/x", code, "err", {}, None)


def test_retry_on_transient_errors_retries_403_and_succeeds():
    # Regression guard for the real 2026-09-10 incident: ArcGIS's CDN
    # returned 403 for a request that succeeded moments later on manual retry.
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(403)
        return "ok"

    result = _retry_on_transient_errors(flaky, max_retries=5)
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_on_transient_errors_retries_429():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error(429)
        return "ok"

    assert _retry_on_transient_errors(flaky, max_retries=5) == "ok"


def test_retry_on_transient_errors_does_not_retry_404():
    calls = {"n": 0}

    def always_404():
        calls["n"] += 1
        raise _http_error(404)

    with pytest.raises(urllib.error.HTTPError):
        _retry_on_transient_errors(always_404, max_retries=5)
    assert calls["n"] == 1  # no retry attempted for a non-retryable code


def test_retry_on_transient_errors_gives_up_after_max_retries():
    calls = {"n": 0}

    def always_403():
        calls["n"] += 1
        raise _http_error(403)

    with pytest.raises(urllib.error.HTTPError):
        _retry_on_transient_errors(always_403, max_retries=2)
    assert calls["n"] == 3  # initial attempt + 2 retries
