"""
Pulls earnings-call transcripts from stockanalysis.com: full speaker-tagged
text with per-sentence audio timestamps, plus the CIK/ticker needed to cross-
check against SEC EDGAR filings later. Same shape of problem as the DC
Council pipeline (dc_etl/fetch_captions.py) -- verbatim source text + a
timestamped link back to the original audio -- just a different domain.

robots.txt on stockanalysis.com disallows only /e/ and /p/ (and a few known
scraper bots by name); it does not block general or AI crawlers the way
fool.com's does (which explicitly disallows ClaudeBot/GPTBot/CCBot site-
wide), which is why this source was picked over Motley Fool/Seeking Alpha.

Run from dc-council/earnings_etl/:
  python3 fetch_transcripts.py [--limit N]
Writes one data/{quartr_event_id}.json per transcript + data/index.jsonl.
"""
import argparse
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://stockanalysis.com"
LISTING_URL = f"{BASE}/earnings-call-transcripts/"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; epistemics-hackathon-research/0.1; "
                  "non-commercial research prototype)"
}
SLEEP_SECONDS = 1.5

LINK_RE = re.compile(r'href="(/stocks/[a-z0-9.\-]+/transcripts/([0-9]+)-[a-z0-9\-]+/)"')
FIELD_RE = {
    "cik": re.compile(r'cik:"(\d+)"'),
    "name_full": re.compile(r'nameFull:"([^"]*)"'),
    "ticker": re.compile(r'"ticker":"([^"]*)"'),
    "fiscal_year": re.compile(r'fiscalYear:(\d+)'),
    "quarter_label": re.compile(r'quarterLabel:"([^"]*)"'),
    "event_date": re.compile(r'eventDate:"([^"]*)"'),
    "audio_url": re.compile(r'audioUrl:"([^"]*)"'),
}


def get_listing():
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    seen, paths = set(), []
    for path, event_id in LINK_RE.findall(resp.text):
        if path not in seen:
            seen.add(path)
            paths.append((path, event_id))
    return paths


def parse_transcript(path):
    url = BASE + path
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    meta = {}
    for key, pattern in FIELD_RE.items():
        m = pattern.search(html)
        meta[key] = m.group(1) if m else None

    turns = []
    for turn_div in soup.select("div.border-t.pt-5"):
        name_el = turn_div.select_one("div.font-bold")
        title_el = turn_div.select_one("div.italic")
        sentences = []
        for span in turn_div.select("span.transcript-sentence"):
            start = span.get("data-start-sec")
            end = span.get("data-end-sec")
            text = span.get_text(strip=True)
            if text:
                sentences.append({
                    "start_sec": float(start) if start else None,
                    "end_sec": float(end) if end else None,
                    "text": text,
                })
        if not sentences:
            continue
        turns.append({
            "speaker": name_el.get_text(strip=True) if name_el else None,
            "title": title_el.get_text(strip=True) if title_el else None,
            "text": " ".join(s["text"] for s in sentences),
            "sentences": sentences,
        })

    return {
        "source_url": url,
        "ticker": path.split("/")[2].upper(),
        "cik": meta["cik"],
        "company": meta["name_full"],
        "fiscal_year": meta["fiscal_year"],
        "quarter_label": meta["quarter_label"],
        "event_date": meta["event_date"],
        "audio_url": meta["audio_url"],
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "turns": turns,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    listing = get_listing()
    if args.limit:
        listing = listing[:args.limit]

    index_path = os.path.join(DATA_DIR, "index.jsonl")
    written, skipped = 0, 0
    with open(index_path, "a") as index_file:
        for path, event_id in listing:
            out_path = os.path.join(DATA_DIR, f"{event_id}.json")
            if os.path.exists(out_path):
                skipped += 1
                continue
            try:
                transcript = parse_transcript(path)
            except Exception as exc:
                print(f"FAILED {path}: {exc}")
                continue
            with open(out_path, "w") as f:
                json.dump(transcript, f, indent=2)
            index_file.write(json.dumps({
                "event_id": event_id,
                "ticker": transcript["ticker"],
                "cik": transcript["cik"],
                "company": transcript["company"],
                "quarter_label": transcript["quarter_label"],
                "event_date": transcript["event_date"],
                "n_turns": len(transcript["turns"]),
                "file": f"{event_id}.json",
            }) + "\n")
            index_file.flush()
            written += 1
            print(f"wrote {event_id}.json  {transcript['ticker']:<6} {transcript['quarter_label']}  "
                  f"{len(transcript['turns'])} turns")
            time.sleep(SLEEP_SECONDS)

    print(f"\ndone: wrote {written}, skipped {skipped} already-present, "
          f"{len(listing)} total in this listing pull")


if __name__ == "__main__":
    main()
