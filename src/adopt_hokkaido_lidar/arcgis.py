"""Parsing helpers for ArcGIS Web Map JSON and the coverage-index GeoJSON.

These operate on already-fetched JSON (dict) input. Network access lives
elsewhere (Phase 1 HTTP client) so these functions stay pure and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class OperationalLayer:
    layer_id: str
    title: str
    layer_type: str
    item_id: str | None
    url: str | None


def parse_operational_layers(webmap_json: dict) -> list[OperationalLayer]:
    """Extract operationalLayers from an ArcGIS Web Map JSON payload."""
    layers = []
    for layer in webmap_json.get("operationalLayers", []):
        layers.append(
            OperationalLayer(
                layer_id=layer.get("id", ""),
                title=layer.get("title", ""),
                layer_type=layer.get("layerType", ""),
                item_id=layer.get("itemId"),
                url=layer.get("url"),
            )
        )
    return layers


# HP link classification. "unknown" is the deliberate default for anything
# that doesn't match a known pattern -- never silently bucket the unfamiliar
# into an existing category.
HP_KIND_CKAN = "ckan"
HP_KIND_ARCGIS_HUB_SEARCH = "arcgis_hub_search"
HP_KIND_EMPTY = "empty"
HP_KIND_UNKNOWN = "unknown"


def classify_hp_link(hp_url: str | None) -> str:
    """Classify a coverage-feature's HP link by destination host/path shape.

    Known shapes confirmed by direct inspection (docs-src/discovery-report.md):
      - https://www.geospatial.jp/ckan/dataset/<slug>          -> ckan
      - https://<hub-site>/search?tags=... or ?q=...            -> arcgis_hub_search
      - "" / None                                                -> empty
    Anything else is reported as "unknown" rather than guessed.
    """
    if not hp_url:
        return HP_KIND_EMPTY
    parsed = urlparse(hp_url)
    if parsed.netloc == "www.geospatial.jp" and "/ckan/dataset/" in parsed.path:
        return HP_KIND_CKAN
    if "hub.arcgis.com" in parsed.netloc and parsed.path == "/search":
        return HP_KIND_ARCGIS_HUB_SEARCH
    return HP_KIND_UNKNOWN


def ckan_dataset_slug(hp_url: str) -> str:
    """Extract the CKAN dataset slug from a classified CKAN HP link.

    Raises ValueError if the URL isn't actually a CKAN dataset link --
    callers must classify first and only call this for HP_KIND_CKAN.
    """
    if classify_hp_link(hp_url) != HP_KIND_CKAN:
        raise ValueError(f"not a CKAN dataset URL: {hp_url!r}")
    parsed = urlparse(hp_url)
    marker = "/ckan/dataset/"
    idx = parsed.path.index(marker) + len(marker)
    slug = parsed.path[idx:].strip("/")
    if not slug:
        raise ValueError(f"CKAN dataset URL has no slug: {hp_url!r}")
    return slug


@dataclass(frozen=True)
class CoverageFeature:
    advisory_no: str
    project_name: str
    hp_url: str | None
    hp_kind: str


def parse_coverage_features(coverage_geojson: dict) -> list[CoverageFeature]:
    """Extract and classify the 72 project-coverage features."""
    out = []
    for feat in coverage_geojson.get("features", []):
        props = feat.get("properties", {})
        hp = props.get("HP") or None
        out.append(
            CoverageFeature(
                advisory_no=str(props.get("助言番号", "")),
                project_name=str(props.get("事業名", "")),
                hp_url=hp,
                hp_kind=classify_hp_link(hp),
            )
        )
    return out
