"""
scrapers.py — All source scraping logic for PNW Event Monitor

Source types handled:
  - eventbrite   : Eventbrite public search (no API key needed)
  - bandsintown  : Bandsintown public artist/city search
  - web          : Generic HTML scraping with heuristic event extraction
  - rss          : RSS/Atom feed parsing (for Facebook RSS bridges, etc.)
"""

import re
import time
import logging
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from urllib.parse import urlencode, quote_plus

logger = logging.getLogger("scrapers")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15


# =============================================================================
# DATE HELPERS
# =============================================================================

def try_parse_date(raw: str):
    """Return ISO date string or None."""
    if not raw:
        return None
    raw = raw.strip()
    # Strip weekday prefix like "Saturday, "
    raw = re.sub(r"^[A-Za-z]+,\s*", "", raw)
    try:
        dt = dateparser.parse(raw, fuzzy=True)
        if dt and dt.year >= datetime.now().year:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def extract_time(text: str):
    """Pull first time-like string from text."""
    m = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?|\d{1,2}\s*(?:am|pm|AM|PM))\b", text)
    return m.group(0).strip() if m else None


# =============================================================================
# EVENTBRITE SCRAPER
# =============================================================================

def scrape_eventbrite(source_cfg: dict, lookback_days: int = 14) -> list:
    """Scrape Eventbrite search results for a location."""
    location = source_cfg.get("location", "Bellingham, WA")
    events = []
    base_url = "https://www.eventbrite.com/d/"
    slug = location.lower().replace(", ", "--").replace(" ", "-").replace(",", "")
    url = f"{base_url}{slug}/events/"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Eventbrite renders cards in several possible formats
        cards = (
            soup.select("[data-testid='event-card']")
            or soup.select(".eds-event-card-content__primary-content")
            or soup.select("article")
        )

        for card in cards[:40]:
            title_el = (
                card.select_one("h2")
                or card.select_one("h3")
                or card.select_one("[data-testid='event-card-title']")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 4:
                continue

            link_el = card.select_one("a[href]")
            url_event = link_el["href"] if link_el else ""
            if url_event and not url_event.startswith("http"):
                url_event = "https://www.eventbrite.com" + url_event

            date_el = card.select_one("p[data-testid='event-card-date']") or card.select_one("time")
            date_raw = date_el.get_text(strip=True) if date_el else ""
            date_parsed = try_parse_date(date_raw) or try_parse_date(date_el.get("datetime", "") if date_el else "")
            time_raw = extract_time(date_raw)

            loc_el = card.select_one("p[data-testid='event-card-venue']") or card.select_one("[data-testid='event-card-location']")
            location_text = loc_el.get_text(strip=True) if loc_el else location

            desc_el = card.select_one("p.eds-text-bm")
            description = desc_el.get_text(strip=True) if desc_el else ""

            events.append({
                "title": title,
                "date_raw": date_raw,
                "date_parsed": date_parsed,
                "time_raw": time_raw,
                "location": location_text,
                "description": description,
                "url": url_event,
                "source_name": source_cfg["name"],
            })

    except Exception as e:
        logger.warning(f"Eventbrite error ({location}): {e}")

    return events


# =============================================================================
# BANDSINTOWN SCRAPER
# =============================================================================

def scrape_bandsintown(source_cfg: dict, lookback_days: int = 14) -> list:
    """Scrape Bandsintown events for a city using their public explore page."""
    location = source_cfg.get("location", "Bellingham, WA")
    city_slug = location.lower().replace(", wa", "").replace(" ", "-")
    events = []

    url = f"https://www.bandsintown.com/c/{quote_plus(city_slug)}-united-states?came_from=257"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("a[href*='/e/']") or soup.select("[data-testid='event-card']")
        for card in cards[:30]:
            title_el = card.select_one("p, h2, h3, span[class*='title']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            link = card.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.bandsintown.com" + link

            text = card.get_text(" ", strip=True)
            date_raw = ""
            # Look for date patterns in the card text
            m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", text)
            if m:
                date_raw = m.group(0) + f" {datetime.now().year}"
            date_parsed = try_parse_date(date_raw)
            time_raw = extract_time(text)

            events.append({
                "title": title,
                "date_raw": date_raw,
                "date_parsed": date_parsed,
                "time_raw": time_raw,
                "location": location,
                "description": "",
                "url": link,
                "source_name": source_cfg["name"],
            })

    except Exception as e:
        logger.warning(f"Bandsintown error ({location}): {e}")

    return events


# =============================================================================
# RSS / ATOM FEED SCRAPER
# =============================================================================

def scrape_rss(source_cfg: dict, lookback_days: int = 14) -> list:
    """Parse any RSS or Atom feed (including Facebook RSS bridges)."""
    url = source_cfg.get("url", "")
    events = []

    if not url or "REPLACE_WITH" in url:
        logger.info(f"RSS source '{source_cfg['name']}' has placeholder URL — skipping")
        return []

    try:
        feed = feedparser.parse(url)
        cutoff = datetime.utcnow() - timedelta(days=2)  # Only recent posts

        for entry in feed.entries[:30]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if pub:
                pub_dt = datetime(*pub[:6])
                if pub_dt < cutoff:
                    continue
                date_raw = pub_dt.strftime("%B %d, %Y")
                date_parsed = pub_dt.strftime("%Y-%m-%d")
            else:
                date_raw = ""
                date_parsed = None

            # Try to extract event date from content
            content = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Look for date patterns in post body
            m = re.search(
                r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}",
                text, re.IGNORECASE
            )
            if m:
                date_raw = m.group(0)
                date_parsed = try_parse_date(date_raw) or date_parsed

            time_raw = extract_time(text)

            # Location: look for "at [Venue]" or "Location: X"
            loc_m = re.search(r"(?:at|@|location[:\s]+)([A-Z][^,\n.]{3,40})", text)
            location = loc_m.group(1).strip() if loc_m else source_cfg["name"]

            description = text[:400] if text else ""

            events.append({
                "title": title,
                "date_raw": date_raw,
                "date_parsed": date_parsed,
                "time_raw": time_raw,
                "location": location,
                "description": description,
                "url": entry.get("link", ""),
                "source_name": source_cfg["name"],
            })

    except Exception as e:
        logger.warning(f"RSS error ({source_cfg['name']}): {e}")

    return events


# =============================================================================
# GENERIC WEB SCRAPER
# =============================================================================

# Date patterns used to detect event-like text
DATE_PATTERNS = [
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{0,4}",
    r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+\w+\s+\d{1,2}",
    r"\d{1,2}/\d{1,2}/\d{2,4}",
]
DATE_RE = re.compile("|".join(DATE_PATTERNS), re.IGNORECASE)


def _extract_events_from_soup(soup: BeautifulSoup, source_name: str, base_url: str) -> list:
    """
    Heuristic extraction: find repeated structured blocks that look like event listings.
    Works on most event calendar pages.
    """
    events = []

    # Strategy 1: Look for structured event schema markup
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            import json
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Event", "MusicEvent", "SocialEvent", "TheaterEvent"):
                    title = item.get("name", "")
                    if not title:
                        continue
                    start = item.get("startDate", "")
                    date_parsed = try_parse_date(start[:10]) if start else None
                    time_raw = start[11:16] if len(start) > 10 else None
                    loc = item.get("location", {})
                    if isinstance(loc, dict):
                        location = loc.get("name", "") or loc.get("address", {}).get("addressLocality", "")
                    else:
                        location = str(loc)
                    events.append({
                        "title": title,
                        "date_raw": start[:10],
                        "date_parsed": date_parsed,
                        "time_raw": time_raw,
                        "location": location,
                        "description": item.get("description", "")[:400],
                        "url": item.get("url", base_url),
                        "source_name": source_name,
                    })
        except Exception:
            pass

    if events:
        return events

    # Strategy 2: Find repeated card-like elements with date text
    candidates = []
    for el in soup.find_all(["article", "div", "li", "section"]):
        text = el.get_text(" ", strip=True)
        if len(text) < 20 or len(text) > 2000:
            continue
        if DATE_RE.search(text):
            # Has a date + looks like a bounded card
            children = [c for c in el.children if c.name]
            if 1 <= len(children) <= 12:
                candidates.append(el)

    # Deduplicate nested elements
    seen_texts = set()
    filtered = []
    for el in candidates:
        t = el.get_text(" ", strip=True)[:120]
        if t not in seen_texts:
            seen_texts.add(t)
            filtered.append(el)

    for el in filtered[:40]:
        text = el.get_text(" ", strip=True)

        title_el = el.find(["h1", "h2", "h3", "h4", "strong", "b"])
        title = title_el.get_text(strip=True) if title_el else text[:80]
        if len(title) < 4:
            continue

        # Find link
        link_el = el.find("a", href=True)
        url_event = ""
        if link_el:
            href = link_el["href"]
            if href.startswith("http"):
                url_event = href
            elif href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                url_event = f"{parsed.scheme}://{parsed.netloc}{href}"

        # Find date
        date_m = DATE_RE.search(text)
        date_raw = date_m.group(0) if date_m else ""
        date_parsed = try_parse_date(date_raw)
        time_raw = extract_time(text)

        # Find location (text after "at" or near the bottom of the card)
        loc_m = re.search(r"\bat\s+([A-Z][^,\n]{3,50})", text)
        location = loc_m.group(1).strip() if loc_m else ""

        # Description: everything except title
        desc = text.replace(title, "").strip()[:300]

        events.append({
            "title": title,
            "date_raw": date_raw,
            "date_parsed": date_parsed,
            "time_raw": time_raw,
            "location": location,
            "description": desc,
            "url": url_event or base_url,
            "source_name": source_name,
        })

    return events


def scrape_web(source_cfg: dict, lookback_days: int = 14) -> list:
    url = source_cfg.get("url", "")
    if not url:
        return []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
            tag.decompose()

        return _extract_events_from_soup(soup, source_cfg["name"], url)

    except Exception as e:
        logger.warning(f"Web scrape error ({source_cfg['name']}): {e}")
        return []


# =============================================================================
# DISPATCHER
# =============================================================================

def scrape_source(source_cfg: dict, lookback_days: int = 14) -> list:
    """Route to the right scraper based on type."""
    stype = source_cfg.get("type", "web")
    if not source_cfg.get("enabled", True):
        return []

    time.sleep(1.5)  # Polite delay between requests

    if stype == "eventbrite":
        return scrape_eventbrite(source_cfg, lookback_days)
    elif stype == "bandsintown":
        return scrape_bandsintown(source_cfg, lookback_days)
    elif stype == "rss":
        return scrape_rss(source_cfg, lookback_days)
    elif stype == "web":
        return scrape_web(source_cfg, lookback_days)
    else:
        logger.warning(f"Unknown source type: {stype}")
        return []
