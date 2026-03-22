"""
filters.py — Keyword matching, categorization, and geographic filtering
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("filters")


def categorize_event(event: dict, categories: dict) -> Optional[str]:
    """
    Match event title + description against category keyword lists.
    Returns the first matching category name, or None.
    """
    searchable = " ".join([
        event.get("title", ""),
        event.get("description", ""),
        event.get("location", ""),
    ]).lower()

    best_cat = None
    best_count = 0

    for cat_name, cat_cfg in categories.items():
        keywords = cat_cfg.get("keywords", [])
        count = sum(1 for kw in keywords if kw.lower() in searchable)
        if count > best_count:
            best_count = count
            best_cat = cat_name

    return best_cat if best_count > 0 else None


def passes_geo_filter(event: dict, geo_cfg: dict) -> bool:
    """
    Return True if the event location matches geographic keywords,
    or if geo filtering is disabled, or if the event has no location info.
    """
    if not geo_cfg.get("enabled", True):
        return True

    location = (event.get("location") or "").lower()
    description = (event.get("description") or "").lower()
    title = (event.get("title") or "").lower()
    combined = f"{location} {description} {title}"

    if not location:
        return True  # No location info — don't exclude

    keywords = [kw.lower() for kw in geo_cfg.get("keywords", [])]
    return any(kw in combined for kw in keywords)


def is_future_event(event: dict, lookback_days: int = 14) -> bool:
    """
    Return True if the event's parsed date is in the future or unknown.
    Events with no date are kept (we can't tell).
    """
    from datetime import datetime, timedelta
    date_parsed = event.get("date_parsed")
    if not date_parsed:
        return True
    try:
        event_dt = datetime.strptime(date_parsed, "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=1)  # Allow yesterday's events
        return event_dt >= cutoff
    except Exception:
        return True


def clean_title(title: str) -> str:
    """Strip HTML entities, excess whitespace, and common noise from titles."""
    if not title:
        return ""
    # Remove HTML entities
    title = re.sub(r"&amp;", "&", title)
    title = re.sub(r"&[a-z]+;", "", title)
    # Collapse whitespace
    title = " ".join(title.split())
    # Strip trailing punctuation clutter
    title = title.strip("•·|–—-").strip()
    return title[:200]


def filter_and_enrich(raw_events: list, config: dict) -> list:
    """
    Apply all filters and add category to each event.
    Returns list of events that passed all filters.
    """
    categories = config.get("categories", {})
    geo_cfg = config.get("geography", {})
    lookback_days = config.get("schedule", {}).get("lookback_days", 14)

    seen_titles = set()
    results = []

    for event in raw_events:
        title = clean_title(event.get("title", ""))
        if not title or len(title) < 4:
            continue

        # Clean title
        event["title"] = title

        # Dedup by title+date within this batch
        key = f"{title.lower()}|{event.get('date_parsed', '')}"
        if key in seen_titles:
            continue
        seen_titles.add(key)

        # Geographic filter
        if not passes_geo_filter(event, geo_cfg):
            logger.debug(f"Geo filter excluded: {title}")
            continue

        # Date filter (skip past events)
        if not is_future_event(event, lookback_days):
            logger.debug(f"Past event excluded: {title} ({event.get('date_parsed')})")
            continue

        # Categorize
        cat = categorize_event(event, categories)
        if cat:
            event["category"] = cat
        else:
            event["category"] = "Uncategorized"

        results.append(event)

    return results
