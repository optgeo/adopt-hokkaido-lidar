"""PDAL pipeline construction and invocation.

Two source formats are known so far (docs-src/discovery-report.md Section
3.1a/3.2): binary LAS/LAZ (readers.las) and plain-text XYZ point CSV
(readers.text, confirmed format "id,X,Y,Z,class" on the one CKAN sample
inspected). Pipeline JSON is built as data (a pure function, unit-tested);
actual invocation always goes through subprocess with an explicit argv list
-- never shell=True, per the startup spec's security constraints.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

READER_LAS = "readers.las"
READER_TEXT = "readers.text"

_READER_BY_FORMAT = {
    "las": READER_LAS,
    "text_csv": READER_TEXT,
}


def build_copc_pipeline(
    input_path: str,
    output_path: str,
    source_format: str,
    *,
    text_header: str | None = None,
    override_srs: str | None = None,
) -> dict:
    """Build a PDAL pipeline (as a dict, ready for json.dumps) converting one raw point file to COPC.

    `source_format` must be 'las' or 'text_csv' (adopt_hokkaido_lidar.zip_inspect's
    RAW_FORMAT_* constants) -- anything else raises rather than guessing a reader.

    `text_header` is required for text_csv sources: PDAL's readers.text has
    no way to infer column order from a headerless CSV, and the one real
    sample found (docs-src/discovery-report.md Section 3.1a) had none
    (bare "id,X,Y,Z,class" rows) -- the caller must supply the confirmed
    column order explicitly rather than this module assuming one.

    `override_srs` is deliberately separate from "trust whatever's in the
    file": readers.las auto-detects an embedded CRS on its own, so this is
    only for the text_csv case (no embedded CRS at all) or for a human
    override after investigating a suspicious embedded CRS -- it is never
    set automatically.
    """
    if source_format not in _READER_BY_FORMAT:
        raise ValueError(f"unknown source_format {source_format!r}; expected one of {list(_READER_BY_FORMAT)}")

    reader_stage: dict = {"type": _READER_BY_FORMAT[source_format], "filename": input_path}

    if source_format == "text_csv":
        if not text_header:
            raise ValueError("text_header is required for text_csv sources (no embedded schema to infer from)")
        reader_stage["header"] = text_header

    if override_srs:
        reader_stage["override_srs"] = override_srs

    writer_stage = {
        "type": "writers.copc",
        "filename": output_path,
    }

    return {"pipeline": [reader_stage, writer_stage]}


@dataclass(frozen=True)
class PipelineResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_pipeline(pipeline: dict, *, pdal_executable: str = "pdal") -> PipelineResult:
    """Run a PDAL pipeline via subprocess, feeding the JSON on stdin.

    Uses an explicit argv list (no shell=True) and pipes the pipeline JSON
    directly rather than writing a temp file the pipeline's own filenames
    could collide with.
    """
    proc = subprocess.run(
        [pdal_executable, "pipeline", "--stdin"],
        input=json.dumps(pipeline),
        capture_output=True,
        text=True,
        check=False,
    )
    return PipelineResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def probe_metadata(input_path: str, *, pdal_executable: str = "pdal") -> dict:
    """Run `pdal info --metadata` on a (possibly header-only, truncated) point file.

    Used to read an embedded CRS from just the first few KB of a LAS/LAZ
    file without downloading the whole thing -- see
    docs-src/discovery-report.md Section 3 for how this was used to find
    the embedded (and possibly outdated) JGD2000 CRS on the Jクレ sample.
    A truncated file is expected to still yield header/VLR metadata even
    though point-data reads would fail; callers should not ask this
    function for point statistics.
    """
    proc = subprocess.run(
        [pdal_executable, "info", "--metadata", input_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pdal info failed (exit {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)
