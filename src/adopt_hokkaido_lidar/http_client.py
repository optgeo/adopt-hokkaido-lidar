"""Polite HTTP client for source-system access (docs-src/source-system-etiquette.md).

Sets a descriptive User-Agent, retries 429/5xx with exponential backoff
honoring Retry-After when present, and never does a full-file download when
a range request will do. Uses urllib (stdlib) rather than adding a new
runtime dependency for this.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = "adopt-hokkaido-lidar/0.1 (+https://github.com/optgeo/adopt-hokkaido-lidar)"

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY_S = 1.0

# 403 is included here on purpose, not just 429/5xx: observed live during the
# Jクレ batch run (2026-09-10) as a transient failure from ArcGIS's
# CloudFront-fronted /data endpoint -- a manual retry of the exact same
# request against the exact same item succeeded within seconds. Treated as
# CDN/backend flakiness rather than a real permission denial for this
# specific endpoint; retrying costs nothing since a *genuine* 403 will just
# keep failing until max_retries is exhausted and then raise normally.
_RETRYABLE_HTTP_CODES = {403, 429}


def compute_backoff_delay(attempt: int, retry_after: float | None, base_delay: float = DEFAULT_BASE_DELAY_S) -> float:
    """Delay before retry `attempt` (0-indexed). Honors a server-supplied Retry-After if present."""
    if retry_after is not None:
        return retry_after
    return base_delay * (2**attempt)


def _retry_on_transient_errors(fn, *, max_retries: int = DEFAULT_MAX_RETRIES):
    """Call fn() (no args), retrying with backoff on _RETRYABLE_HTTP_CODES. Re-raises on exhaustion or other errors."""
    attempt = 0
    while True:
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code in _RETRYABLE_HTTP_CODES and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                delay = compute_backoff_delay(attempt, float(retry_after) if retry_after else None)
                time.sleep(delay)
                attempt += 1
                continue
            raise


@dataclass(frozen=True)
class RangeResponse:
    status: int
    body: bytes
    headers: dict[str, str]


def _request(url: str, *, range_header: str | None = None) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    if range_header:
        headers["Range"] = range_header
    return urllib.request.Request(url, headers=headers)


def resolve_download(url: str, *, max_retries: int = DEFAULT_MAX_RETRIES) -> tuple[str, int]:
    """Follow redirects for `url` and return (final_url, total_size), transferring ~1 byte.

    Used to turn an ArcGIS item's /data endpoint (which 302s to a presigned
    S3/CloudFront URL, confirmed in docs-src/discovery-report.md) into a
    URL that range-GETs work against directly, plus its declared total size
    for the disk-space guard. Deliberately uses a 1-byte Range request
    rather than a plain GET: urlopen()ing a plain GET and simply not
    calling .read() does NOT avoid the transfer -- the server still sends
    the full body over the wire. A ranged request is the only way to
    follow the redirect and learn the size without pulling real data.
    """

    def _do():
        req = _request(url, range_header="bytes=0-0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            final_url = resp.geturl()
            content_range = resp.headers.get("Content-Range")  # "bytes 0-0/<total>"
            resp.read()
        if content_range and "/" in content_range:
            total_size = int(content_range.rsplit("/", 1)[-1])
        else:
            total_size = int(resp.headers.get("Content-Length", -1))
        return final_url, total_size

    return _retry_on_transient_errors(_do, max_retries=max_retries)


def fetch_range(
    url: str, start: int, end: int, *, max_retries: int = DEFAULT_MAX_RETRIES
) -> RangeResponse:
    """Fetch bytes [start, end] (inclusive) via a single Range request, with polite retry."""

    def _do():
        req = _request(url, range_header=f"bytes={start}-{end}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return RangeResponse(status=resp.status, body=resp.read(), headers=dict(resp.headers))

    return _retry_on_transient_errors(_do, max_retries=max_retries)


def fetch_json(url: str, *, max_retries: int = DEFAULT_MAX_RETRIES) -> dict:
    """GET a URL and parse the response body as JSON, with polite retry."""

    def _do():
        req = _request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    return _retry_on_transient_errors(_do, max_retries=max_retries)


def fetch_tail(url: str, total_size: int, n_bytes: int) -> RangeResponse:
    """Fetch the last `n_bytes` of a known-size remote file (for zip_inspect's EOCD scan)."""
    start = max(0, total_size - n_bytes)
    return fetch_range(url, start, total_size - 1)


def download_to_file(
    url: str, dest_path: str, *, chunk_size: int = 1024 * 1024, max_retries: int = DEFAULT_MAX_RETRIES
) -> int:
    """Stream a full download to `dest_path`, following redirects, with polite retry. Returns bytes written."""

    def _do():
        with urllib.request.urlopen(_request(url), timeout=60) as resp, open(dest_path, "wb") as f:
            written = 0
            while chunk := resp.read(chunk_size):
                f.write(chunk)
                written += len(chunk)
            return written

    return _retry_on_transient_errors(_do, max_retries=max_retries)
