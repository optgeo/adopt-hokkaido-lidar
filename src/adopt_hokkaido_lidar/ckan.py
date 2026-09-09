"""Parsing helpers for geospatial.jp CKAN package_show responses.

CKAN packages vary a lot in what they contain (docs-src/discovery-report.md
Section 3): some have an ORIGINAL LAZ zip, most don't. This module's job is
detection, not assumption -- it reports *candidates* and never claims a
package is pipeline-eligible on its own.

IMPORTANT (learned the hard way on h25oribegawasabou): a resource named
"オリジナルデータ" / "original.zip" is only a *stage-1* candidate based on
CKAN metadata alone. It can turn out to contain plain-text XYZ point CSVs
instead of actual .laz/.las files -- CKAN's resource name says nothing about
what's actually inside the zip. `find_original_laz_candidates` narrows down
which resource is worth inspecting; confirming what it actually contains
requires fetching and parsing the zip's central directory
(zip_inspect.parse_central_directory + classify_member_format) before any
asset is treated as pipeline-eligible.
"""

from __future__ import annotations

from dataclasses import dataclass

# Observed CKAN resource-name / filename markers for the "original" package
# (docs-src/discovery-report.md Section 3.1, h25oribegawasabou example).
# Kept as a small, explicit allowlist rather than a fuzzy heuristic, so a
# false negative (missed original) is far more likely than a false positive.
_ORIGINAL_NAME_MARKERS = ("オリジナルデータ", "original")
_ORIGINAL_FILENAME_MARKERS = ("original.zip",)


@dataclass(frozen=True)
class CkanResource:
    name: str
    format: str
    url: str


@dataclass(frozen=True)
class CkanPackage:
    name: str
    license_id: str | None
    organization_title: str | None
    notes: str
    resources: list[CkanResource]


def parse_package(package_show_result: dict) -> CkanPackage:
    """Parse the `result` object of a CKAN package_show response."""
    org = package_show_result.get("organization") or {}
    resources = [
        CkanResource(
            name=r.get("name", ""),
            format=r.get("format", ""),
            url=r.get("url", ""),
        )
        for r in package_show_result.get("resources", [])
    ]
    return CkanPackage(
        name=package_show_result.get("name", ""),
        license_id=package_show_result.get("license_id"),
        organization_title=org.get("title"),
        notes=package_show_result.get("notes") or "",
        resources=resources,
    )


def find_original_laz_candidates(package: CkanPackage) -> list[CkanResource]:
    """Return resources that look like an ORIGINAL LAZ zip.

    Matches on resource name OR the filename tail of the resource URL.
    Returns an empty list when nothing matches -- callers must treat that
    as "no original found for this package" (docs-src/provenance-policy.md),
    not as an error to guess past.
    """
    candidates = []
    for res in package.resources:
        if res.format.upper() != "ZIP":
            continue
        name_hit = any(marker in res.name for marker in _ORIGINAL_NAME_MARKERS)
        filename = res.url.rsplit("/", 1)[-1].lower()
        filename_hit = any(marker in filename for marker in _ORIGINAL_FILENAME_MARKERS)
        if name_hit or filename_hit:
            candidates.append(res)
    return candidates
