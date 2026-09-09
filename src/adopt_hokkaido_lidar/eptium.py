"""Eptium "open in Eptium" URL construction.

Eptium is a third-party COPC viewer, unrelated to this project. The map UI
must only build this URL on an explicit user click (never auto-load it),
per the startup spec -- that behavior lives in the web app, not here; this
module is just the pure URL builder.
"""

from __future__ import annotations

from urllib.parse import quote


def eptium_url(copc_url: str) -> str:
    """Build an Eptium viewer URL for a published COPC object URL.

    The COPC URL is percent-encoded as a single opaque query value --
    Eptium fetches it directly, so it must round-trip exactly.
    """
    if not copc_url.startswith(("https://", "http://")):
        raise ValueError(f"copc_url must be an absolute http(s) URL: {copc_url!r}")
    return f"https://eptium.com/?copc={quote(copc_url, safe='')}"
