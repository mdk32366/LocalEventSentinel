#!/usr/bin/env python3
"""
monitor.py — PNW Event Monitor
Main entry point. Run this file directly.

Usage:
  python monitor.py                        # Start continuous background monitor
  python monitor.py scan                   # Run one scan, print results to screen
  python monitor.py scan --email           # Run scan + email results immediately
  python monitor.py scan --force-email     # Email even if no new events
  python monitor.py query                  # Show upcoming events from database
  python monitor.py query --cat "Live Music"
  python monitor.py query --days 7         # Events in next 7 days
  python monitor.py query --since 3        # Events found in last 3 days
  python monitor.py status                 # Show scan history and stats
  python monitor.py test-email             # Send a test email with current DB events
"""

import sys
import os
import time
import logging
import argparse
import yaml
import schedule
from datetime import datetime, timedelta
from pathlib import Path

# Local modules
from database import init_db, upsert_event, query_events, mark_emailed, purge_old, log_scan, get_scan_history
from scrapers import scrape_source
from filters import filter_and_enrich
from notify import build_and_send_digest, build_html_email

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "monitor.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("monitor")

# ---------------------------------------------------------------------------
# CONFIG LOADER
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# CORE SCAN ENGINE
# ---------------------------------------------------------------------------

def run_scan(config: dict, quiet: bool = False) -> dict:
    """
    Run a full scan of all enabled sources.
    Returns a summary dict.
    """
    sources = config.get("sources", [])
    schedule_cfg = config.get("schedule", {})
    lookback_days = schedule_cfg.get("lookback_days", 14)

    started_at = datetime.utcnow().isoformat()
    sources_ok = 0
    sources_err = 0
    all_raw = []

    if not quiet:
        print(f"\n{'='*60}")
        print(f"  PNW Event Monitor — Scan started {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  {sum(1 for s in sources if s.get('enabled', True))} active sources")
        print(f"{'='*60}")

    for source in sources:
        if not source.get("enabled", True):
            continue
        name = source.get("name", "unknown")
        if not quiet:
            print(f"  Scanning: {name} ...", end="", flush=True)
        try:
            raw = scrape_source(source, lookback_days)
            all_raw.extend(raw)
            sources_ok += 1
            if not quiet:
                print(f" {len(raw)} events found")
        except Exception as e:
            sources_err += 1
            logger.error(f"Source error ({name}): {e}")
            if not quiet:
                print(f" ERROR: {e}")

    # Filter and categorize
    filtered = filter_and_enrich(all_raw, config)

    # Insert into DB
    new_count = 0
    new_events = []
    for event in filtered:
        if upsert_event(event):
            new_count += 1
            new_events.append(event)

    finished_at = datetime.utcnow().isoformat()

    if not quiet:
        print(f"\n  Raw events: {len(all_raw)} → Filtered: {len(filtered)} → New: {new_count}")
        print(f"  Scan complete in {(datetime.utcnow() - datetime.fromisoformat(started_at)).seconds}s")
        print(f"{'='*60}\n")

    # Purge old events
    retention = schedule_cfg.get("retention_days", 90)
    purge_old(retention)

    # Log to DB
    log_scan(started_at, finished_at, sources_ok, sources_err, len(filtered), new_count)

    return {
        "sources_ok": sources_ok,
        "sources_err": sources_err,
        "raw_count": len(all_raw),
        "filtered_count": len(filtered),
        "new_count": new_count,
        "new_events": new_events,
    }


# ---------------------------------------------------------------------------
# CLI COMMANDS
# ---------------------------------------------------------------------------

def cmd_scan(args, config):
    result = run_scan(config)
    new_events = result["new_events"]

    if args.email or (new_events and not args.no_email):
        # For on-demand scan: email results if requested
        if args.email:
            output_cfg = config.get("output", {})
            days = output_cfg.get("email_lookahead_days", 10)
            events_to_email = query_events(days_ahead=days)
            if events_to_email:
                ok = build_and_send_digest(events_to_email, config, is_test=True)
                if ok:
                    mark_emailed([e["id"] for e in events_to_email if e.get("id")])
                    print(f"  Email sent with {len(events_to_email)} events.")
                else:
                    print("  Email send failed — check logs and config.yaml SMTP settings.")
            else:
                print("  No upcoming events in database to email.")


def cmd_query(args, config):
    days = getattr(args, "days", 14)
    cat = getattr(args, "cat", None)
    since = getattr(args, "since", None)

    events = query_events(category=cat, days_ahead=days, since_days=since)

    if not events:
        print(f"\n  No events found matching your filters.\n")
        return

    print(f"\n{'='*60}")
    title_parts = [f"Upcoming events (next {days} days)"]
    if cat:
        title_parts.append(f"Category: {cat}")
    if since:
        title_parts.append(f"Found in last {since} days")
    print(f"  {' | '.join(title_parts)}")
    print(f"  {len(events)} event(s)")
    print(f"{'='*60}")

    current_cat = None
    for ev in events:
        cat_name = ev.get("category", "Uncategorized")
        if cat_name != current_cat:
            current_cat = cat_name
            print(f"\n  ── {cat_name} ──")

        date = ev.get("date_raw") or ev.get("date_parsed") or "Date unknown"
        time_raw = ev.get("time_raw") or ""
        when = f"{date}" + (f" at {time_raw}" if time_raw else "")
        loc = ev.get("location") or "Location unknown"
        url = ev.get("url") or ""

        print(f"\n  📅  {ev['title']}")
        print(f"      {when}")
        print(f"      📍 {loc}")
        if url:
            print(f"      🔗 {url}")

    print(f"\n{'='*60}\n")


def cmd_status(args, config):
    history = get_scan_history(10)
    events = query_events(days_ahead=30)

    print(f"\n{'='*60}")
    print(f"  PNW Event Monitor — Status")
    print(f"{'='*60}")
    print(f"\n  Events in next 30 days: {len(events)}")
    print(f"\n  Recent scans:")
    if not history:
        print("    No scans recorded yet.")
    for h in history:
        ts = h["started_at"][:16].replace("T", " ")
        print(f"    {ts}  +{h['events_new']} new  ({h['sources_ok']} ok / {h['sources_err']} err)")
    print()


def cmd_test_email(args, config):
    output_cfg = config.get("output", {})
    days = output_cfg.get("email_lookahead_days", 10)
    events = query_events(days_ahead=days)
    to_addr = config.get("email", {}).get("to", "?")

    if not events:
        print(f"\n  No upcoming events in database. Run a scan first: python monitor.py scan\n")
        return

    print(f"\n  Sending test digest ({len(events)} events) to {to_addr} ...")
    ok = build_and_send_digest(events, config, is_test=True)
    if ok:
        print("  Test email sent successfully!\n")
    else:
        print("  Failed to send. Check logs/monitor.log and SMTP settings in config.yaml.\n")


# ---------------------------------------------------------------------------
# SCHEDULER (continuous mode)
# ---------------------------------------------------------------------------

def scheduled_scan(config: dict):
    """Called by schedule library — reload config fresh each time."""
    fresh_config = load_config()
    result = run_scan(fresh_config, quiet=True)
    logger.info(
        f"Scheduled scan done: {result['new_count']} new events "
        f"({result['sources_ok']} sources ok, {result['sources_err']} errors)"
    )


def scheduled_email(config: dict):
    """Send the weekly digest email."""
    fresh_config = load_config()
    output_cfg = fresh_config.get("output", {})
    days = output_cfg.get("email_lookahead_days", 10)
    events = query_events(days_ahead=days, emailed=False)

    if not events:
        logger.info("Weekly email: no new events to send")
        return

    ok = build_and_send_digest(events, fresh_config)
    if ok:
        mark_emailed([e["id"] for e in events if e.get("id")])
        logger.info(f"Weekly digest sent: {len(events)} events")
    else:
        logger.error("Weekly digest send failed")


def run_continuous(config: dict):
    """Set up and run the continuous scheduler loop."""
    schedule_cfg = config.get("schedule", {})
    interval_hours = schedule_cfg.get("scan_interval_hours", 12)
    email_cfg = config.get("email", {})
    send_day = email_cfg.get("send_day", "tuesday").lower()
    send_time = email_cfg.get("send_time", "08:00")

    logger.info(f"Starting continuous monitor (scan every {interval_hours}h, "
                f"email every {send_day} at {send_time})")

    # Run first scan immediately on startup
    scheduled_scan(config)

    # Schedule recurring scans
    schedule.every(interval_hours).hours.do(scheduled_scan, config)

    # Schedule weekly email
    day_map = {
        "monday": schedule.every().monday,
        "tuesday": schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday": schedule.every().thursday,
        "friday": schedule.every().friday,
        "saturday": schedule.every().saturday,
        "sunday": schedule.every().sunday,
    }
    day_scheduler = day_map.get(send_day, schedule.every().tuesday)
    day_scheduler.at(send_time).do(scheduled_email, config)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user.")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PNW Event Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command")

    # scan
    p_scan = subparsers.add_parser("scan", help="Run a scan now")
    p_scan.add_argument("--email", action="store_true", help="Also email results after scanning")
    p_scan.add_argument("--no-email", action="store_true", help="Never email, screen only")

    # query
    p_query = subparsers.add_parser("query", help="Query the event database")
    p_query.add_argument("--cat", type=str, default=None, help="Filter by category name")
    p_query.add_argument("--days", type=int, default=14, help="Days ahead to show (default 14)")
    p_query.add_argument("--since", type=int, default=None, help="Only events found in last N days")

    # status
    subparsers.add_parser("status", help="Show scan history and database stats")

    # test-email
    subparsers.add_parser("test-email", help="Send a test email with current database events")

    args = parser.parse_args()

    # Init
    init_db()
    config = load_config()

    if args.command == "scan":
        cmd_scan(args, config)
    elif args.command == "query":
        cmd_query(args, config)
    elif args.command == "status":
        cmd_status(args, config)
    elif args.command == "test-email":
        cmd_test_email(args, config)
    else:
        # No subcommand = continuous mode
        run_continuous(config)


if __name__ == "__main__":
    main()
