# Nothing Phone (3) White 16GB/512GB — Amazon India Stock Tracker

Checks the Amazon.in listing every 15 minutes via GitHub Actions and
sends a Telegram message the moment it comes back in stock.

- **Product:** Nothing Phone (3), White, 16GB RAM / 512GB Storage
- **ASIN:** `B0F7R82LHJ`
- **URL:** https://www.amazon.in/dp/B0F7R82LHJ

## 1. Create your Telegram bot

1. Open Telegram, search for **@BotFather**, and start a chat.
2. Send `/newbot`, give it a name (e.g. `NP3 Stock Bot`) and a username
   ending in `bot` (e.g. `np3_stock_alert_bot`).
3. BotFather replies with an **HTTP API token** — looks like
   `123456789:AAExampleTokenString`. Save it, this is your
   `TELEGRAM_BOT_TOKEN`.
4. Send your new bot any message (e.g. "hi") so it can message you back
   — bots can't message you first.
5. Get your **chat ID**: open this URL in a browser (replace
   `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Look for `"chat":{"id":123456789, ...}` in the JSON response — that
   number is your `TELEGRAM_CHAT_ID`.

## 2. Create the GitHub repo

1. Create a new **private** GitHub repo (e.g. `np3-tracker`).
2. Upload these files, keeping the folder structure:
   ```
   tracker.py
   requirements.txt
   state.json
   .github/workflows/track.yml
   ```

## 3. Add your secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name          | Value                          |
|-----------------------|---------------------------------|
| `TELEGRAM_BOT_TOKEN`  | token from BotFather            |
| `TELEGRAM_CHAT_ID`    | your chat ID                    |

## 4. Enable Actions & test

1. Go to the **Actions** tab, enable workflows if prompted.
2. Open **"Nothing Phone 3 Stock Tracker"** → **Run workflow** to trigger
   it manually and confirm it works (check the run logs, and check that
   you receive a Telegram test message if the phone happens to be in
   stock).
3. After that it runs automatically every 15 minutes via the cron
   schedule — no further action needed.

## How it works

- `tracker.py` fetches the Amazon.in page with browser-like headers
  (no paid scraping API needed) and parses the buy box / availability
  text with BeautifulSoup.
- It compares the current status to the last known status in
  `state.json` and only messages you when the product **transitions
  from out-of-stock to in-stock**, so you don't get spammed every 15
  minutes.
- The workflow commits the updated `state.json` back to the repo after
  each run so state persists between runs.

## Notes & tuning

- **Alert frequency:** change the cron in `track.yml`
  (`*/15 * * * *` = every 15 min). Don't go below every 5 minutes —
  GitHub Actions free-tier scheduling isn't guaranteed to the minute,
  and too-frequent hits increase the chance Amazon blocks the IP.
- **Periodic reminders while in stock:** set the `REMINDER_EVERY_N_RUNS`
  env var in `track.yml` to a nonzero number (e.g. `20`) if you also
  want a "still in stock" nudge every N runs, not just on the initial
  transition.
- **If Amazon starts blocking requests** (you'll see repeated
  `[attempt N] status=503` or captcha messages in the Action logs),
  the free-tier options are:
  - Rotate through a few more realistic User-Agent strings (already
    included) and slow the schedule down.
  - Add a scraping proxy — ScraperAPI, ScrapingBee, and ScrapeOps all
    have free tiers (~1,000 requests/month), which comfortably covers
    a 15-minute schedule. If you want, this can be added later as a
    fallback without much change to the script.
- **False positives/negatives:** Amazon's HTML changes periodically.
  If alerts stop matching reality, the `#availability` / button
  selectors in `parse_availability()` may need a quick update — the
  script prints its raw availability text and price in the Action
  logs on every run, which makes this easy to debug.
