"""Source Cooperative client: thin wrapper around the AWS CLI's S3 commands.

Uses the `source-coop` AWS profile, whose credentials come from
`credential_process = source-coop creds` in ~/.aws/config (docs-src, PLAN.md
"Source Cooperative読み書きアクセス") -- no key material is read, stored, or
passed by this module; it only ever names the profile.

Every call goes through subprocess with an explicit argv list, never
shell=True, matching the same constraint applied to PDAL invocation.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

SC_ENDPOINT_URL = "https://data.source.coop"
SC_PROFILE = "source-coop"

_BASE_ARGS = ["aws", "s3", "--profile", SC_PROFILE, "--endpoint-url", SC_ENDPOINT_URL]


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


def upload(local_path: str, s3_url: str) -> CommandResult:
    return _run([*_BASE_ARGS, "cp", local_path, s3_url])


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
