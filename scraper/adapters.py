"""Per-ATS adapters. Each adapter fetches a company's open roles and returns a
list of normalized job dicts:

    {
        "id":         str,   # stable, provider-assigned id
        "title":      str,
        "location":   str,
        "url":        str,   # link a human can open and apply
        "updated_at": str,   # ISO-ish timestamp or "" if the provider omits it
    }

Adapters use only the standard library so the scraper runs under cron with no
`pip install` step.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "jobs-scrapper/1.0 (+personal job-tracker)"
TIMEOUT = 30


class FetchError(RuntimeError):
    """Raised when a provider can't be reached or returns unusable data."""


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise FetchError(f"{url}: {exc}") from exc


def _norm(job_id, title, location, url, updated_at, offices=None) -> dict:
    return {
        "id": str(job_id),
        "title": (title or "").strip(),
        "location": (location or "").strip(),
        "url": url or "",
        "updated_at": updated_at or "",
        # Provider-supplied office/region groupings (e.g. Greenhouse's "US",
        # "Ireland Locations"). More reliable than the free-text location for
        # country filtering. Empty for providers that don't expose it.
        "offices": offices or [],
    }


def greenhouse(cfg: dict) -> list[dict]:
    """Greenhouse public Job Board API. No auth required.
    Covers the vast majority of tech companies."""
    slug = cfg["slug"]
    # content=true also returns each job's `offices` (country/region grouping),
    # which the bare listing omits and which the location filter relies on.
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = _get_json(url)
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = [o.get("name", "") for o in j.get("offices", [])]
        out.append(_norm(j.get("id"), j.get("title"), loc,
                         j.get("absolute_url"), j.get("updated_at"), offices))
    return out


def lever(cfg: dict) -> list[dict]:
    """Lever public postings API. No auth required."""
    slug = cfg["slug"]
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = _get_json(url)
    out = []
    for j in data:
        cats = j.get("categories") or {}
        # Lever createdAt is epoch millis; keep as string for stable diffing.
        out.append(_norm(j.get("id"), j.get("text"), cats.get("location"),
                         j.get("hostedUrl"), str(j.get("createdAt", ""))))
    return out


def eightfold(cfg: dict) -> list[dict]:
    """Eightfold AI careers API (e.g. Netflix). Paginated via start/num."""
    base = cfg.get("base_url", "").rstrip("/")
    domain = cfg["domain"]
    # Eightfold ignores `num` and returns a fixed page (~10), so we advance
    # `start` by however many we actually got rather than by a requested size.
    start = 0
    out = []
    while True:
        qs = urllib.parse.urlencode(
            {"domain": domain, "start": start, "num": 50})
        data = _get_json(f"{base}/api/apply/v2/jobs?{qs}")
        positions = data.get("positions", [])
        if not positions:
            break
        for p in positions:
            url = p.get("canonicalPositionUrl") or p.get("positionUrl") or ""
            out.append(_norm(p.get("id"), p.get("name"), p.get("location"),
                             url, str(p.get("t_create", ""))))
        start += len(positions)
        if start >= data.get("count", 0):
            break
    return out


def ashby(cfg: dict) -> list[dict]:
    """Ashby public Job Board API. No auth required."""
    org = cfg["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    data = _get_json(url)
    out = []
    for j in data.get("jobs", []):
        addr = (j.get("address") or {}).get("postalAddress") or {}
        # Country/region are more reliable than the free-text location for
        # country filtering, same role Greenhouse's `offices` plays.
        offices = [v for v in (addr.get("addressCountry"), addr.get("addressRegion")) if v]
        out.append(_norm(j.get("id"), j.get("title"), j.get("location"),
                         j.get("jobUrl"), j.get("publishedAt"), offices))
    return out


ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "eightfold": eightfold,
    "ashby": ashby,
}


def fetch(cfg: dict) -> list[dict]:
    provider = cfg.get("provider")
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        raise FetchError(f"unknown provider {provider!r} for {cfg.get('company')}")
    return adapter(cfg)
