"""ArcGIS org-wide item search (network-touching -- arcgis.py stays pure).

Confirmed working query shape (docs-src/discovery-report.md): the classic
`sharing/rest/search` endpoint with `orgid:<org> AND tags:"<tag>" AND
tags:"LAZ" AND tags:"ORIGINAL"` reliably enumerates a project's mesh-tile
ORIGINAL LAZ items, each carrying licenseInfo/size/id directly -- this is
the confirmed discovery path for the Jクレ (forestry carbon-credit) project,
the current priority target (PLAN.md).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from . import http_client

ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
HOKKAIDO_OPENDATA_ORG_ID = "vtIFKqGmW1wohBxY"

_PAGE_SIZE = 100


@dataclass(frozen=True)
class ArcgisItem:
    item_id: str
    title: str
    item_type: str
    size_bytes: int
    license_info: str | None
    tags: list[str]


def search_original_laz_by_tag(tag: str, *, org_id: str = HOKKAIDO_OPENDATA_ORG_ID) -> list[ArcgisItem]:
    """Enumerate ORIGINAL LAZ items for one project tag, paginating through all results."""
    query = f'orgid:{org_id} AND tags:"{tag}" AND tags:"LAZ" AND tags:"ORIGINAL"'
    items: list[ArcgisItem] = []
    start = 1
    while True:
        url = ARCGIS_SEARCH_URL + "?" + urllib.parse.urlencode(
            {"q": query, "f": "json", "num": _PAGE_SIZE, "start": start}
        )
        data = http_client.fetch_json(url)
        for r in data.get("results", []):
            items.append(
                ArcgisItem(
                    item_id=r["id"],
                    title=r.get("title", ""),
                    item_type=r.get("type", ""),
                    size_bytes=r.get("size", -1),
                    license_info=r.get("licenseInfo"),
                    tags=r.get("tags", []),
                )
            )
        next_start = data.get("nextStart", -1)
        if next_start == -1:
            break
        start = next_start
    return items


def item_data_url(item_id: str) -> str:
    """URL that 302-redirects to a presigned download of the item's hosted file (confirmed live)."""
    return f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
