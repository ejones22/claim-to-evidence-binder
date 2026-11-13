"""
Pulls SEC EDGAR's XBRL "company facts" for every CIK seen in data/*.json
(the transcripts fetch_transcripts.py already pulled) -- this is the ground
truth the claim-scorer checks earnings-call claims against: filed revenue,
net income, EPS, etc., each tagged to the exact filing it came from.

SEC's fair-access policy (sec.gov/os/webmaster-faq, "Developers" section)
asks every automated client for a descriptive User-Agent with a contact
method, and caps traffic around 10 req/sec. We stay far under that (one
request every ~0.4s) and use a generic, honest contact string rather than
a real person's address, since this is a non-commercial research script.

Run from dc-council/earnings_etl/:
  python3 fetch_sec_facts.py
Writes one sec_facts/raw/{cik}.json per company (cached; reruns skip what's
already there) + sec_facts/index.jsonl.
"""
import glob
import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "sec_facts", "raw")
HEADERS = {
    "User-Agent": "epistemics-hackathon-research contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}
SLEEP_SECONDS = 0.4


def unique_ciks():
    ciks = {}
    for path in glob.glob(os.path.join(TRANSCRIPTS_DIR, "*.json")):
        with open(path) as f:
            d = json.load(f)
        if d.get("cik"):
            ciks[d["cik"]] = d.get("ticker")
    return ciks


def fetch_facts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ciks = unique_ciks()
    print(f"{len(ciks)} unique CIKs to fetch")

    index_path = os.path.join(HERE, "sec_facts", "index.jsonl")
    written, skipped, missing = 0, 0, 0
    with open(index_path, "a") as index_file:
        for cik, ticker in ciks.items():
            out_path = os.path.join(OUT_DIR, f"{cik}.json")
            if os.path.exists(out_path):
                skipped += 1
                continue
            try:
                facts = fetch_facts(cik)
            except Exception as exc:
                print(f"FAILED {ticker} (cik {cik}): {exc}")
                continue
            if facts is None:
                print(f"no XBRL facts for {ticker} (cik {cik}) -- likely a foreign "
                      f"private issuer filing 20-F/6-K without XBRL companyfacts")
                missing += 1
                index_file.write(json.dumps({"cik": cik, "ticker": ticker, "status": "no_xbrl"}) + "\n")
                index_file.flush()
                time.sleep(SLEEP_SECONDS)
                continue
            with open(out_path, "w") as f:
                json.dump(facts, f)
            taxonomies = facts.get("facts", {})
            n_concepts = sum(len(v) for v in taxonomies.values())
            index_file.write(json.dumps({
                "cik": cik,
                "ticker": ticker,
                "entity_name": facts.get("entityName"),
                "taxonomies": {k: len(v) for k, v in taxonomies.items()},
                "status": "ok",
            }) + "\n")
            index_file.flush()
            written += 1
            print(f"wrote {cik}.json  {ticker:<6}  {n_concepts} concepts "
                  f"({', '.join(taxonomies.keys()) or 'none'})")
            time.sleep(SLEEP_SECONDS)

    print(f"\ndone: wrote {written}, skipped {skipped} already-present, "
          f"{missing} with no XBRL data, {len(ciks)} total")


if __name__ == "__main__":
    main()
