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


def compute_backoff_delay(attempt: int, retry_after: float | None, base_delay: float = DEFAULT_BASE_DELAY_S) -> float:
    """Delay before retry `attempt` (0-indexed). Honors a server-supplied Retry-After if present."""
    if retry_after is not None:
        return retry_after
    return base_delay * (2**attempt)


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


def resolve_download(url: str) -> tuple[str, int]:
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


def fetch_range(
    url: str, start: int, end: int, *, max_retries: int = DEFAULT_MAX_RETRIES
) -> RangeResponse:
    """Fetch bytes [start, end] (inclusive) via a single Range request, with polite retry on 429."""
    req = _request(url, range_header=f"bytes={start}-{end}")
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return RangeResponse(status=resp.status, body=resp.read(), headers=dict(resp.headers))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                delay = compute_backoff_delay(attempt, float(retry_after) if retry_after else None)
                time.sleep(delay)
                attempt += 1
                continue
            raise


def fetch_json(url: str, *, max_retries: int = DEFAULT_MAX_RETRIES) -> dict:
    """GET a URL and parse the response body as JSON, with polite retry on 429."""
    req = _request(url)
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                delay = compute_backoff_delay(attempt, float(retry_after) if retry_after else None)
                time.sleep(delay)
                attempt += 1
                continue
            raise


def fetch_tail(url: str, total_size: int, n_bytes: int) -> RangeResponse:
    """Fetch the last `n_bytes` of a known-size remote file (for zip_inspect's EOCD scan)."""
    start = max(0, total_size - n_bytes)
    return fetch_range(url, start, total_size - 1)


def download_to_file(
    url: str, dest_path: str, *, chunk_size: int = 1024 * 1024, max_retries: int = DEFAULT_MAX_RETRIES
) -> int:
    """Stream a full download to `dest_path`, following redirects, retrying on 429. Returns bytes written."""
    req = _request(url)
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
                written = 0
                while chunk := resp.read(chunk_size):
                    f.write(chunk)
                    written += len(chunk)
                return written
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                delay = compute_backoff_delay(attempt, float(retry_after) if retry_after else None)
                time.sleep(delay)
                attempt += 1
                continue
            raise
