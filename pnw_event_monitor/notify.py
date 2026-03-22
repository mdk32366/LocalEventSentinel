"""
notify.py — HTML email digest builder and SMTP sender for PNW Event Monitor
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import quote_plus
from collections import defaultdict

logger = logging.getLogger("notify")

# Category color map (fallback if not in config)
DEFAULT_COLORS = {
    "Live Music": "#1D9E75",
    "Farmers Market": "#639922",
    "Art & Gallery": "#7F77DD",
    "Theatre & Dance": "#D4537E",
    "Comedy": "#EF9F27",
    "Food & Drink Events": "#D85A30",
    "Outdoor & Nature": "#1D9E75",
    "Film Screening": "#534AB7",
    "Community Festival": "#BA7517",
    "Craft Fair": "#993556",
    "Lecture & Talk": "#185FA5",
    "Uncategorized": "#888780",
}


def _get_cat_color(cat: str, config: dict) -> str:
    cats = config.get("categories", {})
    if cat in cats:
        return cats[cat].get("color", DEFAULT_COLORS.get(cat, "#888780"))
    return DEFAULT_COLORS.get(cat, "#888780")


def _maps_link(location: str) -> str:
    if not location:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location)}"


def build_html_email(events: list, config: dict, is_test: bool = False) -> str:
    """Build a full HTML email digest from a list of event dicts."""
    output_cfg = config.get("output", {})
    group_by_cat = output_cfg.get("email_group_by_category", True)
    include_maps = output_cfg.get("include_map_links", True)
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")
    
    cats_in_config = config.get("categories", {})

    if group_by_cat:
        grouped = defaultdict(list)
        for e in events:
            grouped[e.get("category", "Uncategorized")].append(e)
        # Sort categories by config order
        ordered_cats = list(cats_in_config.keys()) + ["Uncategorized"]
        sections_html = ""
        for cat in ordered_cats:
            if cat not in grouped:
                continue
            color = _get_cat_color(cat, config)
            evs = sorted(grouped[cat], key=lambda x: x.get("date_parsed") or "9999")
            sections_html += _cat_section_html(cat, color, evs, include_maps)
    else:
        events_sorted = sorted(events, key=lambda x: x.get("date_parsed") or "9999")
        sections_html = "".join(
            _event_row_html(e, _get_cat_color(e.get("category", "Uncategorized"), config), include_maps)
            for e in events_sorted
        )

    test_banner = """
    <div style="background:#FFF3CD;border:1px solid #FFC107;border-radius:6px;
                padding:12px 16px;margin-bottom:24px;font-size:14px;color:#856404;">
      <strong>Test email</strong> — this is a manually triggered digest, not the scheduled weekly send.
    </div>
    """ if is_test else ""

    region_str = "Bellingham · Anacortes · San Juans · Seattle corridor"
    lookahead = output_cfg.get("email_lookahead_days", 10)

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>PNW Event Digest — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#F5F5F0;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F0;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr><td style="background:#1A1A1A;border-radius:12px 12px 0 0;padding:32px 36px;">
    <div style="font-family:Georgia,serif;font-size:11px;letter-spacing:0.15em;
                text-transform:uppercase;color:#9E9B8F;margin-bottom:6px;">
      Weekly Digest · {date_str}
    </div>
    <div style="font-size:26px;font-weight:normal;color:#FFFFFF;margin-bottom:4px;
                font-family:Georgia,serif;letter-spacing:-0.02em;">
      PNW Events
    </div>
    <div style="font-size:13px;color:#9E9B8F;">
      {region_str}
    </div>
  </td></tr>

  <!-- Sub-header -->
  <tr><td style="background:#2D2D2D;padding:14px 36px;">
    <span style="font-size:13px;color:#BDBDB0;">
      {len(events)} upcoming event{'s' if len(events) != 1 else ''} 
      over the next {lookahead} days
      {'· <em>Test send</em>' if is_test else ''}
    </span>
  </td></tr>

  <!-- Body -->
  <tr><td style="background:#FFFFFF;padding:28px 36px 8px;">
    {test_banner}
    {sections_html if events else '<p style="color:#888;font-size:15px;">No matching events found for this period.</p>'}
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#F5F5F0;border-radius:0 0 12px 12px;padding:20px 36px 28px;">
    <p style="font-size:12px;color:#9E9B8F;margin:0;line-height:1.6;">
      You're receiving this because PNW Event Monitor is running on your server.<br/>
      To adjust categories or sources, edit <code>config.yaml</code>.<br/>
      To force an immediate scan: <code>python monitor.py scan</code>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""
    return html


def _cat_section_html(cat: str, color: str, events: list, include_maps: bool) -> str:
    rows = "".join(_event_row_html(e, color, include_maps) for e in events)
    return f"""
    <div style="margin-bottom:28px;">
      <div style="display:flex;align-items:center;margin-bottom:12px;">
        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
                     background:{color};margin-right:8px;flex-shrink:0;"></span>
        <span style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;
                     letter-spacing:0.12em;text-transform:uppercase;color:#555;">
          {cat}
        </span>
        <span style="font-family:Arial,sans-serif;font-size:11px;color:#AAA;margin-left:8px;">
          ({len(events)})
        </span>
      </div>
      {rows}
    </div>
    """


def _event_row_html(event: dict, color: str, include_maps: bool) -> str:
    title = event.get("title", "Unknown event")
    date_raw = event.get("date_raw") or event.get("date_parsed") or ""
    time_raw = event.get("time_raw") or ""
    location = event.get("location") or ""
    description = event.get("description") or ""
    url = event.get("url") or ""
    source = event.get("source_name") or ""

    # Format date/time line
    when_parts = [p for p in [date_raw, time_raw] if p]
    when = " · ".join(when_parts)

    title_html = (
        f'<a href="{url}" style="color:#1A1A1A;text-decoration:none;'
        f'font-size:15px;font-weight:bold;font-family:Georgia,serif;">{title}</a>'
    ) if url else (
        f'<span style="font-size:15px;font-weight:bold;font-family:Georgia,serif;'
        f'color:#1A1A1A;">{title}</span>'
    )

    map_link = ""
    if include_maps and location:
        maps_url = _maps_link(location)
        map_link = f' <a href="{maps_url}" style="font-size:11px;color:#888;text-decoration:none;">↗ map</a>'

    desc_html = (
        f'<p style="margin:4px 0 0;font-size:13px;color:#666;font-family:Arial,sans-serif;'
        f'line-height:1.5;">{description[:200]}{"…" if len(description) > 200 else ""}</p>'
    ) if description else ""

    return f"""
    <div style="border-left:3px solid {color};padding:10px 0 10px 14px;margin-bottom:12px;">
      <div style="margin-bottom:2px;">{title_html}</div>
      <div style="font-family:Arial,sans-serif;font-size:12px;color:#888;line-height:1.5;">
        {f'<span style="color:#555;">{when}</span> · ' if when else ''}
        <span>{location}</span>{map_link}
        {f' · <span style="color:#AAA;">via {source}</span>' if source else ''}
      </div>
      {desc_html}
    </div>
    """


def send_email(html: str, subject: str, config: dict) -> bool:
    """Send the HTML email via SMTP."""
    email_cfg = config.get("email", {})
    to_addr = email_cfg.get("to", "")
    from_name = email_cfg.get("from_name", "PNW Event Monitor")
    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_cfg.get("smtp_port", 587))
    smtp_user = email_cfg.get("smtp_user", "")
    smtp_pass = email_cfg.get("smtp_pass", "")

    if not to_addr or not smtp_user or not smtp_pass:
        logger.error("Email config incomplete — check config.yaml")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{smtp_user}>"
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addr, msg.as_string())
        logger.info(f"Email sent to {to_addr}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def build_and_send_digest(events: list, config: dict, is_test: bool = False) -> bool:
    now = datetime.now()
    if is_test:
        subject = f"[TEST] PNW Event Monitor — {now.strftime('%B %d, %Y')}"
    else:
        subject = f"PNW Events this week — {now.strftime('%B %d, %Y')}"

    html = build_html_email(events, config, is_test=is_test)
    return send_email(html, subject, config)
