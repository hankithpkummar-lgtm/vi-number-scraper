---
title: VI Number Scraper
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
license: mit
---

# VI Number Scraper

Automatic VI (Vodafone-Idea) VIP/Fancy number scraper with numerology validation, Google Sheet sync, and real-time dashboard.

## Features

- **24/7 Auto-Scrape** — Workers run continuously, scraping VI numbers around the clock
- **Numerology Validation** — Filters numbers by Chaldean numerology (root, compound, planet)
- **Google Sheet Sync** — Auto-pushes found numbers to Google Sheets in real-time
- **Premium Dashboard** — Full admin panel with live stats, numbers table, sync status
- **JWT Auth** — Secure login-protected dashboard
- **AutoRAM Scaling** — Dynamically adjusts workers based on available memory

## How to Use

1. Open the dashboard: `https://[your-space].hf.space/dashboard`
2. Login with your credentials
3. Monitor scraping in real-time
4. Numbers auto-sync to Google Sheet

## Configuration

Set these environment variables in your HF Space settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `GAS_URL` | Yes | Google Apps Script URL for sheet sync |
| `SCRAPER_USERNAME` | No | VI portal login (optional, page is public) |
| `SCRAPER_PASSWORD` | No | VI portal password |
| `NUM_WORKERS` | No | Worker count (default: 12, min: 12) |
| `MAX_WORKERS` | No | Max workers for auto-scaling (default: 24) |
| `AUTO_START_WORKERS` | No | Auto-start on boot (default: true) |
| `HEADLESS` | No | Run browsers headless (default: true) |

## Local Development

```bash
# Start locally
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7860

# Login at http://localhost:7860/login
# Default credentials: hankith / arvind@2012
```

## License

MIT
