"""Daily Apple Podcasts chart + rating tracker for one show, across every Apple storefront.

Usage:
  python scripts/tracker.py            # fetch, save history, build report, email it
  python scripts/tracker.py --no-email # same, but skip sending
"""
import argparse
import json
import os
import re
import smtplib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).parent))
from countries import COUNTRIES, FLAGS  # noqa: E402
from report import build_report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
HISTORY_PATH = ROOT / "docs" / "data" / "history.json"
REPORT_PATH = ROOT / "docs" / "latest-report.html"
TZ = ZoneInfo("America/Boise")

SESSION = requests.Session()
SESSION.headers["User-Agent"] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def get(url, tries=3):
    for attempt in range(tries):
        try:
            r = SESSION.get(url, timeout=25)
            if r.status_code == 200:
                return r
            if r.status_code in (400, 404):
                return None  # storefront/chart doesn't exist
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    return None


# ---------- charts ----------

def fetch_chart(country, genre_id):
    """Return (status, rank). status: 'ok' | 'unavailable'. rank None = not in the chart."""
    limit = CONFIG.get("chart_limit", 200)
    url = f"https://itunes.apple.com/{country}/rss/toppodcasts/limit={limit}/genre={genre_id}/json"
    r = get(url)
    if r is None:
        return "unavailable", None
    try:
        feed = r.json().get("feed", {})
    except ValueError:
        return "unavailable", None
    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    for i, e in enumerate(entries, start=1):
        pid = e.get("id", {}).get("attributes", {}).get("im:id")
        if pid == CONFIG["podcast_id"]:
            return "ok", i
    return "ok", None


# ---------- ratings ----------

def _num(s):
    s = s.strip().replace(",", "").replace(" ", "").replace("\xa0", "")
    mult = 1
    if s[-1:].upper() == "K":
        mult, s = 1000, s[:-1]
    elif s[-1:].upper() == "M":
        mult, s = 1_000_000, s[:-1]
    return int(round(float(s.replace(" ", "")) * mult))


def parse_rating(html):
    # 1) Structured data embedded in the page (any language).
    for m in re.finditer(r'"ratingCount"\s*:\s*(\d+)', html):
        window = html[max(0, m.start() - 400): m.end() + 400]
        v = re.search(r'"(?:ratingAverage|averageRating|ratingValue|value)"\s*:\s*([0-5](?:\.\d+)?)', window)
        if v:
            return {"avg": round(float(v.group(1)), 2), "count": int(m.group(1))}
    m = re.search(r'"ratingValue"\s*:\s*"?([0-5](?:\.\d+)?)"?.{0,200}?"(?:ratingCount|reviewCount)"\s*:\s*"?(\d+)', html, re.S)
    if m:
        return {"avg": float(m.group(1)), "count": int(m.group(2))}
    # 2) Visible text fallback (English storefronts): "5.0 (304)" / "304 Ratings".
    m = re.search(r'([0-5][.,]\d)\s*\(([\d.,]+\s*[KkMm]?)\)', html)
    if m:
        return {"avg": float(m.group(1).replace(",", ".")), "count": _num(m.group(2))}
    m1 = re.search(r'([0-5][.,]\d)\s*out of 5', html)
    m2 = re.search(r'([\d.,]+\s*[KkMm]?)\s*Ratings?', html)
    if m1 and m2:
        return {"avg": float(m1.group(1).replace(",", ".")), "count": _num(m2.group(1))}
    return None


def fetch_rating(country):
    url = f"https://podcasts.apple.com/{country}/podcast/id{CONFIG['podcast_id']}"
    r = get(url)
    if r is None:
        return "unavailable", None
    return "ok", parse_rating(r.text)


# ---------- main ----------

def load_history():
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {"runs": [], "charts": {}, "ratings": {}, "unavailable": {}}


def send_email(subject, html):
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("REPORT_TO") or user
    if not (user and pw):
        print("Email skipped: GMAIL_USER / GMAIL_APP_PASSWORD not set.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, f"Podcast Chart Tracker <{user}>", to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw.replace(" ", ""))
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"Report emailed to {to}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true")
    args = ap.parse_args()

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    hist = load_history()
    codes = list(COUNTRIES)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for chart in CONFIG["charts"]:
            gid = chart["genre_id"]
            results = list(pool.map(lambda c: fetch_chart(c, gid), codes))
            ok = 0
            for code, (status, rank) in zip(codes, results):
                if status == "unavailable":
                    hist["unavailable"].setdefault(gid, {})[code] = today
                    continue
                ok += 1
                hist["unavailable"].get(gid, {}).pop(code, None)
                series = hist["charts"].setdefault(gid, {}).setdefault(code, {})
                if rank:
                    series[today] = rank
                else:
                    series.pop(today, None)  # only ranks are stored; absence = not charting
                    if not series:
                        hist["charts"][gid].pop(code)
            charting = sum(1 for c in codes if hist["charts"].get(gid, {}).get(c, {}).get(today))
            hist.setdefault("checked", {}).setdefault(gid, {})[today] = ok
            print(f"{chart['name']}: checked {ok} storefronts, charting in {charting}")
            if ok == 0:
                sys.exit("No chart data came back from Apple; not saving this run.")

        if CONFIG.get("track_ratings", True):
            results = list(pool.map(fetch_rating, codes))
            got = 0
            for code, (status, rating) in zip(codes, results):
                if status == "ok" and rating:
                    got += 1
                    hist["ratings"].setdefault(code, {})[today] = rating
            print(f"Ratings: found ratings in {got} storefronts")

    if today not in hist["runs"]:
        hist["runs"].append(today)
    hist["runs"].sort()
    hist["updated"] = datetime.now(TZ).isoformat(timespec="minutes")
    hist["config"] = CONFIG
    hist["countries"] = COUNTRIES
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(hist, separators=(",", ":"), sort_keys=True))

    subject, html = build_report(hist, today, CONFIG, COUNTRIES, FLAGS)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(subject)
    if not args.no_email:
        send_email(subject, html)


if __name__ == "__main__":
    main()
