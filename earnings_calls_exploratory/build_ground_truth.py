"""
Pairs each pulled transcript with the filed figures for its own fiscal
quarter, pulled from SEC EDGAR's XBRL companyfacts (fetch_sec_facts.py).
This is the "checkable evidence" side of the claim-to-evidence binder: a
CEO says "record revenue of $6.3B" on the call, this says what the company
actually filed for that quarter and in which document.

Handles both GAAP filers (us-gaap taxonomy) and IFRS filers (ifrs-full,
common among foreign private issuers like Nu Holdings or StoneCo).

Run from dc-council/earnings_etl/:
  python3 build_ground_truth.py
Writes one ground_truth/{event_id}.json per transcript that had a usable
match, keyed the same way as data/{event_id}.json so the two pair up.
"""
import glob
import json
import os
import re
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPTS_DIR = os.path.join(HERE, "data")
FACTS_DIR = os.path.join(HERE, "sec_facts", "raw")
OUT_DIR = os.path.join(HERE, "ground_truth")

QUARTER_RE = re.compile(r"Q(\d)\s*(\d{4})")

# label -> (concept names to try, in order, per taxonomy, unit key)
CONCEPTS = {
    "revenue": {
        "us-gaap": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax"],
        "ifrs-full": ["Revenue"],
        "unit": "USD",
    },
    "net_income": {
        "us-gaap": ["NetIncomeLoss", "ProfitLoss"],
        "ifrs-full": ["ProfitLoss"],
        "unit": "USD",
    },
    "eps_diluted": {
        "us-gaap": ["EarningsPerShareDiluted"],
        "ifrs-full": ["DilutedEarningsLossPerShare"],
        "unit": "USD/shares",
    },
    "operating_income": {
        "us-gaap": ["OperatingIncomeLoss"],
        "ifrs-full": ["ProfitLossFromOperatingActivities"],
        "unit": "USD",
    },
    "total_assets": {
        "us-gaap": ["Assets"],
        "ifrs-full": ["Assets"],
        "unit": "USD",
    },
}


def best_entries(facts, taxonomy, concept_names, unit):
    for name in concept_names:
        node = facts.get("facts", {}).get(taxonomy, {}).get(name)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if entries:
            return name, entries
    return None, []


def span_days(entry):
    if "start" not in entry or not entry.get("start"):
        return None
    s = date.fromisoformat(entry["start"])
    e = date.fromisoformat(entry["end"])
    return (e - s).days


def pick_value(entries, fp, event_date):
    # stockanalysis.com's fiscal-year label and SEC's own `fy` tag can be
    # off by one for companies with a non-calendar fiscal year -- so fy is
    # only a hint, never the gate. The real gate is: does this entry's
    # period actually fall shortly before the call happened? A figure
    # whose period ends a year away from the call is a mismatch, fy label
    # notwithstanding, and must be rejected rather than silently used.
    quarterly = fp in ("Q1", "Q2", "Q3")
    event = date.fromisoformat(event_date)
    candidates = [e for e in entries if e.get("fp") == fp
                  and e.get("form", "").startswith(("10-Q", "10-K", "20-F", "6-K"))]
    if quarterly:
        candidates = [e for e in candidates
                      if span_days(e) is None or 75 <= span_days(e) <= 100]
    else:
        candidates = [e for e in candidates
                      if span_days(e) is None or span_days(e) >= 300]

    def days_before_call(e):
        return (event - date.fromisoformat(e["end"])).days

    # the quarter must have closed before the call, and not too long before
    candidates = [e for e in candidates if -15 <= days_before_call(e) <= 120]
    if not candidates:
        return None
    candidates.sort(key=lambda e: (days_before_call(e), e.get("filed", "")))
    chosen = candidates[0]
    return {
        "value": chosen["val"],
        "fiscal_year": chosen.get("fy"),
        "fiscal_period": chosen.get("fp"),
        "form": chosen.get("form"),
        "filed": chosen.get("filed"),
        "accession": chosen.get("accn"),
        "period_end": chosen.get("end"),
        "filing_index_url": accession_url(chosen),
        "n_filings_reporting_this_figure": len(candidates),
    }


def accession_url(entry):
    accn = entry.get("accn", "").replace("-", "")
    cik = entry.get("cik")
    if not accn or not cik:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{entry['accn']}-index.htm"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    written, no_cik, no_facts, no_match = 0, 0, 0, 0

    for path in sorted(glob.glob(os.path.join(TRANSCRIPTS_DIR, "*.json"))):
        event_id = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            transcript = json.load(f)

        cik = transcript.get("cik")
        quarter_label = transcript.get("quarter_label") or ""
        event_date = transcript.get("event_date")
        m = QUARTER_RE.search(quarter_label)
        if not cik or not m or not event_date:
            no_cik += 1
            continue

        fp = f"Q{m.group(1)}"

        facts_path = os.path.join(FACTS_DIR, f"{cik}.json")
        if not os.path.exists(facts_path):
            no_facts += 1
            continue
        with open(facts_path) as f:
            facts = json.load(f)

        taxonomies = list(facts.get("facts", {}).keys())
        taxonomy = "ifrs-full" if "ifrs-full" in taxonomies and "us-gaap" not in taxonomies else "us-gaap"

        result = {}
        for label, spec in CONCEPTS.items():
            names = spec.get(taxonomy, [])
            concept_name, entries = best_entries(facts, taxonomy, names, spec["unit"])
            if not entries:
                continue
            # entries don't carry their own cik -- attach it for accession_url()
            for e in entries:
                e.setdefault("cik", cik)
            value = pick_value(entries, fp, event_date)
            if value:
                value["concept"] = f"{taxonomy}:{concept_name}"
                result[label] = value

        if not result:
            no_match += 1
            continue

        out = {
            "event_id": event_id,
            "ticker": transcript.get("ticker"),
            "cik": cik,
            "company": transcript.get("company"),
            "quarter_label": quarter_label,
            "taxonomy": taxonomy,
            "figures": result,
        }
        with open(os.path.join(OUT_DIR, f"{event_id}.json"), "w") as f:
            json.dump(out, f, indent=2)
        written += 1
        print(f"{event_id}  {transcript.get('ticker'):<6}  matched {len(result)}/5 figures: "
              f"{', '.join(result.keys())}")

    print(f"\ndone: {written} matched, {no_cik} no cik/quarter, "
          f"{no_facts} no SEC facts cached, {no_match} no figures matched")


if __name__ == "__main__":
    main()
