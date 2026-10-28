"""Filter fetched roles down to the ones worth tracking.

Two independent filters, both driven by config.json's ``filters`` block:

    * us_only   — keep only roles located in the United States
    * work_arrangement — keep roles matching any, remote, hybrid, or onsite
  * keywords  — keep only roles whose title matches one of the keywords

Location strings are wildly inconsistent across ATSes ("USA - Remote",
"Los Gatos,California,United States of America", "San Francisco, CA",
"Toronto, ON, CA"). We classify with an *allowlist*: a role is US if it carries
a US signal (country token, full state name, or US state code). Anything with no
US signal (Berlin, Tokyo, London) is simply not US — no country blocklist needed.

The one genuine ambiguity is the code "CA": California vs Canada. Canadian
province codes (ON, BC, AB, …) are never US state codes, so the only special
case is to reject "CA" when Canadian markers are present in the same string.
"""

from __future__ import annotations

import re

US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
}

# All 50 + DC. Note: "CA" is handled separately because it collides with Canada.
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI",
    "WY", "DC",
}

# Major US cities that frequently appear with no state/country qualifier
# (e.g. Stripe lists "Seattle" or "San Francisco" alone). Limited to well-known,
# low-collision names — deliberately excluding ambiguous ones like Cambridge,
# Birmingham, or Manchester that are just as likely to mean the UK.
US_CITIES = {
    "san francisco", "south san francisco", "new york", "new-york", "brooklyn",
    "los angeles", "seattle", "chicago", "boston", "austin", "denver",
    "atlanta", "portland", "dallas", "houston", "san diego", "san jose",
    "philadelphia", "minneapolis", "nashville", "phoenix", "miami", "detroit",
    "palo alto", "mountain view", "sunnyvale", "bellevue",
}
# Uppercase city abbreviations (matched case-sensitively, like state codes).
US_CITY_CODES = {"SF", "NYC", "SEA"}

US_COUNTRY = re.compile(r"\b(?:united states|u\.?s\.?a\.?|u\.?s\.?|america)\b",
                        re.I)
STATE_NAME = re.compile(r"\b(?:" + "|".join(US_STATE_NAMES) + r")\b", re.I)
US_CITY = re.compile(r"\b(?:" + "|".join(re.escape(c) for c in US_CITIES)
                     + r")\b", re.I)
# 2-letter codes appear uppercase in ATS data; match them case-sensitively so
# we don't pick up lowercase words like "or", "in", "me".
CODE = re.compile(r"\b([A-Z]{2})\b")
CANADA_MARKERS = re.compile(
    r"\b(?:canada|toronto|vancouver|montreal|ottawa|calgary|edmonton|"
    r"winnipeg|ontario|quebec|alberta|british columbia|"
    r"on|bc|ab|qc|ns|mb|sk|nl|pe)\b", re.I)


def is_us(location: str) -> bool:
    if not location:
        return False
    if US_COUNTRY.search(location):
        return True
    if STATE_NAME.search(location):
        return True
    if US_CITY.search(location):
        return True
    codes = set(CODE.findall(location))
    if codes & ((US_STATE_CODES | US_CITY_CODES) - {"CA"}):
        return True
    # "CA" counts as California only when nothing Canadian is in the string.
    if "CA" in codes and not CANADA_MARKERS.search(location):
        return True
    return False


def _compile_keywords(keywords: list[str]) -> re.Pattern | None:
    if not keywords:
        return None
    alts = "|".join(re.escape(k.strip()) for k in keywords if k.strip())
    # Word boundaries so "ui" matches "UI Engineer" but not "build"/"guide",
    # and "web" matches "Web Developer" but not "webhook".
    return re.compile(r"\b(?:" + alts + r")\b", re.I)


def work_arrangement(location: str, description: str = "") -> str:
    """Classify from keywords anywhere in the location or description."""
    value = f"{location or ''} {description or ''}".lower()
    # A specific recurring office schedule means the role is hybrid, even if
    # the description does not include Ashby's separate "Location Type" field.
    days_per_week = r"(?:[1-5]|one|two|three|four|five)\s+days?\s+(?:(?:a|per)\s+week|/week)"
    office = r"(?:in[- ]office|on[- ]?site|at (?:the )?office)"
    if (re.search(rf"\b{office}\b.{{0,40}}\b{days_per_week}\b", value)
            or re.search(rf"\b{days_per_week}\b.{{0,40}}\b{office}\b", value)):
        return "hybrid"
    if re.search(r"\bremote\b", value):
        return "remote"
    if re.search(r"\bhybrid\b", value):
        return "hybrid"
    if re.search(r"\b(?:on[- ]?site|in[- ]office|office[- ]based)\b", value):
        return "onsite"
    return "unknown"


def make_filter(filters: dict | None):
    """Return a predicate ``job -> bool`` for the configured filters.

    A None/empty config means keep everything (backwards compatible).
    """
    filters = filters or {}
    us_only = filters.get("us_only", False)
    arrangement = filters.get("work_arrangement", "any")
    if arrangement not in {"any", "remote", "hybrid", "onsite"}:
        arrangement = "any"
    kw = _compile_keywords(filters.get("keywords", []))

    def keep(job: dict) -> bool:
        if kw is not None and not kw.search(job.get("title", "")):
            return False
        loc = job.get("location", "")
        if arrangement != "any" and work_arrangement(loc, job.get("description", "")) != arrangement:
            return False
        if us_only:
            # Office/region tags (Greenhouse) are the most reliable US signal and
            # resolve cases the free-text location can't, like "N/A".
            if any(is_us(o) for o in job.get("offices", [])):
                return True
            if not is_us(loc):
                return False
        return True

    return keep
