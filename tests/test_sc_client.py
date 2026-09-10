import subprocess
from unittest.mock import patch

from adopt_hokkaido_lidar.sc_client import upload


def _completed(returncode, stderr=""):
    return subprocess.CompletedProcess(args=["aws"], returncode=returncode, stdout="", stderr=stderr)


def test_upload_succeeds_first_try():
    with patch("subprocess.run", return_value=_completed(0)) as mock_run:
        result = upload("/tmp/x.copc.laz", "s3://bucket/x.copc.laz", base_delay=0.01)
    assert result.ok
    assert mock_run.call_count == 1


def test_upload_retries_on_cloudflare_520_and_succeeds():
    err_520 = "upload failed: An error occurred (520) when calling the UploadPart operation: "
    with patch("subprocess.run", side_effect=[_completed(1, err_520), _completed(0)]) as mock_run:
        result = upload("/tmp/x.copc.laz", "s3://bucket/x.copc.laz", base_delay=0.01)
    assert result.ok
    assert mock_run.call_count == 2


def test_upload_does_not_retry_non_transient_failure():
    err_403 = "An error occurred (AccessDenied) when calling the PutObject operation: Forbidden"
    with patch("subprocess.run", return_value=_completed(1, err_403)) as mock_run:
        result = upload("/tmp/x.copc.laz", "s3://bucket/x.copc.laz", base_delay=0.01)
    assert not result.ok
    assert mock_run.call_count == 1


def test_upload_gives_up_after_max_retries():
    err_520 = "An error occurred (520) when calling the UploadPart operation: "
    with patch("subprocess.run", return_value=_completed(1, err_520)) as mock_run:
        result = upload("/tmp/x.copc.laz", "s3://bucket/x.copc.laz", max_retries=2, base_delay=0.01)
    assert not result.ok
    assert mock_run.call_count == 3  # initial attempt + 2 retries
