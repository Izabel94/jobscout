"""Pin session-only cookies with a 30-day expiry so closing the CDP Chrome
doesn't wipe Upwork/LinkedIn login — equivalent to a site's "Stay signed in"."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import BrowserContext


def pin_session_cookies(context: BrowserContext, url: str, *, days: int = 30) -> int:
    """Returns the count of cookies re-pinned. Idempotent — already-persistent cookies are skipped."""
    cookies = context.cookies(url)
    expires_at = time.time() + days * 24 * 3600
    pinned: list[dict[str, Any]] = []
    for c in cookies:
        if c.get("expires", -1) not in (-1, 0):
            continue
        new_cookie: dict[str, Any] = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path") or "/",
            "expires": expires_at,
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
            "sameSite": c.get("sameSite") or "Lax",
        }
        pinned.append(new_cookie)
    if pinned:
        # add_cookies upserts by (name, domain, path); extends expiry without touching values.
        context.add_cookies(pinned)
    return len(pinned)
