# PNW Event Monitor

A powerful, self-hosted event monitoring and aggregation system for the Pacific Northwest. Automatically scrapes events from multiple sources, filters by your interests and location, and sends you a beautiful weekly email digest.

**Features:**
- 🔍 Multi-source event scraping (Eventbrite, Bandsintown, RSS feeds, generic web scraping)
- 🎯 Smart filtering by geographic location and interest categories
- 📧 Beautiful HTML email digests delivered on your schedule
- 🎨 Color-coded event categories for easy scanning
- 🤖 Runs 24/7 as a background service
- ⚙️ Fully configurable—no code changes needed
- 💾 Local SQLite database for event tracking
- 📊 Scan history and statistics

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Running as a Service](#running-as-a-service)
- [Contributing](#contributing)

---

## Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- An email account (Gmail, SendGrid, or other SMTP provider)

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mdk32366/LocalEventSentinel.git
   cd LocalEventSentinel/pnw_event_monitor
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```
   - On Windows: `venv\Scripts\activate`
   - On macOS/Linux: `source venv/bin/activate`

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your settings:**
   Edit `config.yaml` with your email settings and interests (see [Configuration](#configuration))

5. **Test it:**
   ```bash
   python monitor.py scan
   ```

6. **Set up automated digests:**
   ```bash
   python monitor.py
   ```
   This starts the background monitor that sends digests on your schedule.

---

## Installation

### System Requirements

- **OS:** Windows, macOS, or Linux
- **Python:** 3.8+
- **Disk Space:** ~50 MB (mostly for dependencies)
- **Internet:** Required for scraping and email

### Detailed Setup

1. **Clone and navigate:**
   ```bash
   git clone https://github.com/mdk32366/LocalEventSentinel.git
   cd LocalEventSentinel/pnw_event_monitor
   ```

2. **Set up Python environment:**
   ```bash
   python -m venv venv
   ```
   
   Activate it:
   - **Windows (PowerShell):** `venv\Scripts\Activate.ps1`
   - **Windows (CMD):** `venv\Scripts\activate.bat`
   - **macOS/Linux:** `source venv/bin/activate`

3. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database:**
   ```bash
   python -c "from database import init_db; init_db()"
   ```

---

## Configuration

All configuration is in **`config.yaml`**. No code changes needed!

### Email Settings

```yaml
email:
  to: "your@email.com"           # Your email address
  from_name: "PNW Event Monitor" # Sender name
  send_day: "tuesday"            # Day to send digest: monday–sunday
  send_time: "08:00"             # Time in 24-hr format (HH:MM), local timezone
  smtp_host: "smtp.gmail.com"    # SMTP server
  smtp_port: 587
  smtp_user: "sender@gmail.com"  # Email account to send from
  smtp_pass: "xxxx xxxx xxxx xxxx"  # App password (see below)
```

#### Gmail Setup (Recommended)

1. Enable [2-Step Verification](https://myaccount.google.com/security) on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Copy the 16-character password (spaces ignored) to `config.yaml` as `smtp_pass`

#### Other Email Providers

- **SendGrid:**
  ```yaml
  smtp_host: "smtp.sendgrid.net"
  smtp_port: 587
  smtp_user: "apikey"
  smtp_pass: "SG.your_api_key_here"
  ```

- **Office 365:**
  ```yaml
  smtp_host: "smtp.office365.com"
  smtp_port: 587
  smtp_user: "your@outlook.com"
  ```

- **Custom SMTP:** Use your provider's SMTP settings

### Interest Categories

Add, remove, or edit categories to match your interests. Each category has keywords (case-insensitive) and a color for emails.

```yaml
categories:
  Live Music:
    keywords: [concert, live music, band, jazz, bluegrass, folk, acoustic, ...]
    color: "#1D9E75"

  Farmers Market:
    keywords: [farmers market, farm stand, market day, ...]
    color: "#639922"
  
  # Add more as needed...
```

**Built-in categories:**
- Live Music
- Farmers Market
- Art & Gallery
- Theatre & Dance
- Comedy
- Food & Drink Events
- Outdoor & Nature
- Film Screening
- Community Festival
- Craft Fair
- Lecture & Talk

### Geographic Filter

Only keep events mentioning these locations. Events with no location info always pass through.

```yaml
geography:
  enabled: true
  keywords:
    - bellingham
    - whatcom
    - anacortes
    - fidalgo
    - la conner
    - mount vernon
    - friday harbor
    - san juan islands
    # Add more locations as needed
```

Set `enabled: false` to disable geographic filtering entirely.

---

## Usage

### Commands

#### Scan for new events (one-time)
```bash
python monitor.py scan
```
Immediately scrapes all sources, filters events, updates the database, and prints results.

#### Scan and email immediately
```bash
python monitor.py scan --email
```
Runs a scan and sends results via email right away (doesn't wait for scheduled time).

#### Force email even if no new events
```bash
python monitor.py scan --force-email
```
Sends email with current database contents.

#### Query events from database
```bash
python monitor.py query
```
Shows upcoming events.

Query with filters:
```bash
python monitor.py query --cat "Live Music"     # Only Live Music events
python monitor.py query --days 7               # Next 7 days
python monitor.py query --since 3              # Found in last 3 days
```

#### View scan history and statistics
```bash
python monitor.py status
```
Shows when the last scan ran, how many new events, and scan history.

#### Send test email
```bash
python monitor.py test-email
```
Sends an email with current database contents (useful for testing setup).

#### Start background monitor (24/7)
```bash
python monitor.py
```
Runs continuously, performing scheduled scans and sending digests. Press `Ctrl+C` to stop.

---

## Architecture

### Data Flow

```
Sources (Eventbrite, Bandsintown, RSS, etc.)
          ↓
    Scraper Module (scrapers.py)
          ↓
    Filter & Enrich (filters.py)
          ↓
    Database (database.py)
          ↓
    Email Digest (notify.py)
          ↓
    Your Inbox
```

### Core Modules

**`monitor.py`**
- Main entry point
- Scheduling engine (for recurring scans and digests)
- Command-line interface

**`scrapers.py`**
- Eventbrite search scraping
- Bandsintown artist/city search
- Generic HTML event extraction
- RSS/Atom feed parsing

**`filters.py`**
- Keyword-based categorization
- Geographic location filtering
- Event enrichment

**`database.py`**
- SQLite event storage
- Query interface
- Scan history tracking

**`notify.py`**
- HTML email template generation
- SMTP email sending
- Formatting and styling

**`config.yaml`**
- Single configuration file (no code changes needed)

---

## Running as a Service

### Linux / Raspberry Pi (systemd)

1. **Edit** `scripts/pnw-monitor.service` to match your setup:
   ```ini
   User=pi                                      # Your username
   WorkingDirectory=/home/pi/pnw_event_monitor  # Full path to project dir
   ExecStart=/home/pi/pnw_event_monitor/venv/bin/python monitor.py
   ```

2. **Copy to systemd:**
   ```bash
   sudo cp scripts/pnw-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start pnw-monitor
   sudo systemctl enable pnw-monitor  # Auto-start on boot
   ```

4. **Check status:**
   ```bash
   sudo systemctl status pnw-monitor
   ```

5. **View logs:**
   ```bash
   sudo journalctl -u pnw-monitor -f
   ```

### Windows (Task Scheduler)

1. **Create a batch script** (e.g., `run_monitor.bat`):
   ```batch
   @echo off
   cd "C:\path\to\pnw_event_monitor"
   venv\Scripts\python.exe monitor.py
   ```

2. **Open Task Scheduler** and create a new task:
   - **Trigger:** At system startup or on a schedule
   - **Action:** Run `run_monitor.bat`
   - **Settings:** Run with highest privileges, allow on-demand triggers

### macOS (LaunchAgent)

Create `~/Library/LaunchAgents/local.pnw-monitor.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>local.pnw-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>/path/to/monitor.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/logs/monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/logs/monitor-error.log</string>
</dict>
</plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/local.pnw-monitor.plist
```

---

## Troubleshooting

### Email not sending?

1. Check email credentials in `config.yaml`
2. Test with `python monitor.py test-email`
3. Verify SMTP host and port are correct for your provider
4. Check `logs/monitor.log` for error details
5. For Gmail: ensure you're using an App Password, not your login password

### No events being found?

1. Run `python monitor.py scan` and check the console output
2. Verify interest categories and keywords in `config.yaml`
3. Check geographic filter settings (try disabling it temporarily)
4. Review `logs/monitor.log` for scraping errors

### Database issues?

1. The database is created automatically at `data/events.db`
2. To reset: delete `data/events.db` and restart
3. Query the database: `python monitor.py query`

### Memory or CPU usage?

- Adjust scan frequency in `config.yaml` (longer intervals = less resource usage)
- Purge old events: events older than 60 days are automatically removed

### Having trouble on Raspberry Pi?

- Ensure you're using Python 3.8+ (check with `python --version`)
- Install additional system dependencies: `sudo apt install python3-dev`
- Use `sudo journalctl -u pnw-monitor -f` to debug systemd service

---

## File Structure

```
pnw_event_monitor/
├── config.yaml                   # Configuration (edit this!)
├── monitor.py                    # Main entry point
├── database.py                   # SQLite database layer
├── scrapers.py                   # Event scrapers
├── filters.py                    # Filtering & categorization
├── notify.py                     # Email digest generation
├── requirements.txt              # Python dependencies
├── scripts/
│   ├── pnw-monitor.service      # Linux systemd service file
│   └── oracle_cloud_setup.sh    # Optional cloud setup
├── data/                         # Events database (created on first run)
├── logs/                         # Application logs (created on first run)
└── templates/                    # Email templates (if customization needed)
```

---

## Performance Notes

- **Scan time:** 30–90 seconds depending on sources and internet speed
- **Database:** Stores ~1000s of events; efficient queries
- **Email size:** ~50–300 KB depending on event count
- **Memory:** ~50–100 MB during operation
- **CPU:** Minimal when idle; brief spike during scans

---

## Privacy & Security

- **Data:** Events are stored only locally in SQLite
- **Email:** Uses encrypted SMTP connections (TLS/SSL)
- **Credentials:** Store email passwords carefully in `config.yaml`
- **No tracking:** No analytics, no external dashboards

⚠️ **Keep `config.yaml` private!** It contains your email credentials.

---

## Limitations & Future Ideas

### Current Limitations
- Events are scraped from web sources; accuracy depends on source data
- Duplicate detection is basic (title + date matching)
- Email delivery depends on your SMTP provider's reliability

### Future Ideas
- Mobile app or web dashboard
- Event recommendations based on RSVP history
- Multi-user support with individual preferences
- Calendar integration (Google Calendar, Outlook)
- Push notifications
- Event photo/image inclusion

---

## Contributing

Have ideas or found bugs? Contributions are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

### Areas for Contribution
- New event sources (Meetup, Ticketmaster, local event sites)
- Better event deduplication
- Additional geographic regions
- UI/web dashboard
- Mobile app
- Improved email templates
- Performance optimizations

---

## License

This project is provided as-is for personal use. Modify and distribute freely.

---

## Support

For issues, questions, or ideas:
1. Check [Troubleshooting](#troubleshooting)
2. Review `logs/monitor.log` for error details
3. Open an issue on GitHub

---

## Acknowledgments

Built with:
- [requests](https://requests.readthedocs.io/) – HTTP library
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) – HTML parsing
- [feedparser](https://feedparser.readthedocs.io/) – RSS/Atom parsing
- [schedule](https://schedule.readthedocs.io/) – Job scheduling
- [PyYAML](https://pyyaml.org/) – Configuration loading

---

**Happy event hunting! 🎉**
