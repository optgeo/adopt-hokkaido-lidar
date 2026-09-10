"""Source Cooperative client: thin wrapper around the AWS CLI's S3 commands.

Uses the `source-coop` AWS profile, whose credentials come from
`credential_process = source-coop creds` in ~/.aws/config (docs-src, PLAN.md
"Source Cooperative読み書きアクセス") -- no key material is read, stored, or
passed by this module; it only ever names the profile.

Every call goes through subprocess with an explicit argv list, never
shell=True, matching the same constraint applied to PDAL invocation.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass

SC_ENDPOINT_URL = "https://data.source.coop"
SC_PROFILE = "source-coop"

_BASE_ARGS = ["aws", "s3", "--profile", SC_PROFILE, "--endpoint-url", SC_ENDPOINT_URL]

DEFAULT_UPLOAD_MAX_RETRIES = 1
DEFAULT_UPLOAD_BASE_DELAY_S = 2.0

# Observed live during the Jクレ batch (2026-09-10): `aws s3 cp` occasionally
# fails a multipart UploadPart with a Cloudflare 520 ("Web server returned an
# unknown error"), which is CloudFront/Cloudflare-edge flakiness in front of
# Source Cooperative's storage, not a real problem with the object or
# credentials. AWS CLI's own internal retry doesn't seem to absorb this case
# reliably, so retry the whole `cp` at this layer instead.
_RETRYABLE_STDERR_PATTERN = re.compile(r"\((?:520|52[1-9]|59\d)\)|Could not connect|Connection reset")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _run(args: list[str]) -> CommandResult:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def upload(
    local_path: str,
    s3_url: str,
    *,
    max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
    base_delay: float = DEFAULT_UPLOAD_BASE_DELAY_S,
) -> CommandResult:
    """Upload one file, retrying on a transient-looking failure (see _RETRYABLE_STDERR_PATTERN).

    A retried upload re-runs the whole `aws s3 cp`, including any part
    already sent for a multipart transfer -- there's no cheap way to resume
    a partial multipart upload through the plain CLI, so a large file's
    retry does re-send bytes. Accepted as the simple, correct option here;
    revisit only if this turns out to be the actual bottleneck.
    """
    attempt = 0
    while True:
        result = _run([*_BASE_ARGS, "cp", local_path, s3_url])
        if result.ok or attempt >= max_retries or not _RETRYABLE_STDERR_PATTERN.search(result.stderr):
            return result
        time.sleep(base_delay * (2**attempt))
        attempt += 1


def remove(s3_url: str) -> CommandResult:
    return _run([*_BASE_ARGS, "rm", s3_url])


def list_prefix(s3_url: str) -> CommandResult:
    return _run([*_BASE_ARGS, "ls", s3_url])


def head_object_size(s3_url: str) -> int | None:
    """Return the object's Content-Length via `aws s3api head-object`, or None if it doesn't exist.

    Used as the (deliberately limited) post-upload check: confirms the
    object exists and has the expected size. This is NOT a byte-exact
    checksum verification -- `aws s3 cp` multiparts uploads above its
    default threshold, so the S3 ETag is not simply the object's MD5/SHA256
    for a file this size, and re-downloading the whole object just to hash
    it again would defeat the point of a lightweight verification step.
    The locally-computed sha256 is what's kept as the durable source of
    truth, alongside the object, in checksum.sha256 (docs-src/provenance-policy.md).
    """
    if not s3_url.startswith("s3://"):
        raise ValueError(f"expected an s3:// url, got {s3_url!r}")
    bucket, _, key = s3_url[len("s3://") :].partition("/")
    proc = subprocess.run(
        [
            "aws",
            "s3api",
            "head-object",
            "--profile",
            SC_PROFILE,
            "--endpoint-url",
            SC_ENDPOINT_URL,
            "--bucket",
            bucket,
            "--key",
            key,
            "--query",
            "ContentLength",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return int(proc.stdout.strip())
