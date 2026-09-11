#!/usr/bin/env python3
"""
Amazon India stock tracker for:
  Nothing Phone (3), White, 16GB RAM / 512GB Storage
  ASIN: B0F7R82LHJ

Sends a Telegram alert whenever the product becomes available
(transitions from out-of-stock -> in-stock), plus an optional
periodic "still in stock" reminder every REMINDER_EVERY_N_RUNS runs.

State (last known status) is persisted to state.json so alerts are
only sent on genuine changes, not on every run.
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---- Config -----------------------------------------------------------

ASIN = "B0F7R82LHJ"
PRODUCT_URL = f"https://www.amazon.in/dp/{ASIN}"
PRODUCT_LABEL = "Nothing Phone (3) White 16GB/512GB"

STATE_FILE = Path(__file__).parent / "state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Send a reminder even if still in stock, once every N runs (0 = never)
REMINDER_EVERY_N_RUNS = int(os.environ.get("REMINDER_EVERY_N_RUNS", "0"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 "
    "Safari/604.1",
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.google.com/",
    }


def fetch_page(url, max_retries=4):
    """Fetch a page with retries + jittered backoff. Returns HTML or None."""
    session = requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=get_headers(), timeout=20)
            if resp.status_code == 200 and "captcha" not in resp.text.lower()[:5000]:
                return resp.text
            print(
                f"[attempt {attempt}] status={resp.status_code} "
                f"len={len(resp.text)} (possible block/captcha)"
            )
        except requests.RequestException as e:
            print(f"[attempt {attempt}] request error: {e}")

        if attempt < max_retries:
            sleep_s = (2 ** attempt) + random.uniform(0, 1.5)
            time.sleep(sleep_s)
    return None


def parse_availability(html):
    """
    Returns a dict: {"in_stock": bool, "price": str|None, "title": str|None,
                      "reason": str}
    """
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(strip=True) if title_el else None

    price = None
    price_el = soup.select_one(".a-price .a-offscreen")
    if price_el:
        price = price_el.get_text(strip=True)

    # Amazon's out-of-stock / unavailable signals
    unavailable_markers = [
        "currently unavailable",
        "we don't know when or if this item will be back in stock",
        "out of stock",
    ]

    availability_el = soup.select_one("#availability")
    availability_text = (
        availability_el.get_text(" ", strip=True).lower() if availability_el else ""
    )

    buybox_present = bool(
        soup.select_one("#add-to-cart-button")
        or soup.select_one("#buy-now-button")
        or soup.select_one("#one-click-button")
    )

    is_unavailable_text = any(m in availability_text for m in unavailable_markers)

    in_stock = buybox_present and not is_unavailable_text

    reason = (
        f"availability_text='{availability_text}' "
        f"buybox_present={buybox_present}"
    )

    return {
        "in_stock": in_stock,
        "price": price,
        "title": title,
        "reason": reason,
    }


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing; skipping notification.")
        print("Message would have been:\n", text)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except requests.RequestException as e:
        print(f"Telegram send error: {e}")
        return False


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_in_stock": False, "consecutive_checks": 0, "consecutive_failures": 0}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    state = load_state()

    html = fetch_page(PRODUCT_URL)

    if html is None:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        save_state(state)
        print(
            f"Could not fetch page after retries "
            f"(consecutive_failures={state['consecutive_failures']})."
        )
        # Don't alert on fetch failure by default — Amazon blocking a bot
        # is common and not the same as being out of stock. Uncomment
        # below if you want to be notified when the checker itself breaks.
        #
        # if state["consecutive_failures"] in (5, 20):
        #     send_telegram_message(
        #         f"⚠️ Tracker has failed to fetch the page "
        #         f"{state['consecutive_failures']} times in a row. "
        #         f"It may be getting blocked by Amazon."
        #     )
        sys.exit(0)

    state["consecutive_failures"] = 0

    result = parse_availability(html)
    print(json.dumps(result, indent=2))

    was_in_stock = state.get("last_in_stock", False)
    now_in_stock = result["in_stock"]

    state["consecutive_checks"] = state.get("consecutive_checks", 0) + 1

    should_alert = False
    header = None

    if now_in_stock and not was_in_stock:
        should_alert = True
        header = "✅ BACK IN STOCK"
    elif (
        now_in_stock
        and REMINDER_EVERY_N_RUNS > 0
        and state["consecutive_checks"] % REMINDER_EVERY_N_RUNS == 0
    ):
        should_alert = True
        header = "🔔 Still in stock (reminder)"

    if should_alert:
        price_line = f"\n💰 Price: {result['price']}" if result["price"] else ""
        message = (
            f"{header}\n"
            f"📱 {PRODUCT_LABEL}{price_line}\n"
            f"🔗 {PRODUCT_URL}"
        )
        sent = send_telegram_message(message)
        print(f"Alert sent: {sent}")

    if not now_in_stock and was_in_stock:
        print("Product went out of stock again.")

    state["last_in_stock"] = now_in_stock
    save_state(state)


if __name__ == "__main__":
    main()
