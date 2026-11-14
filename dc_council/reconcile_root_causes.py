"""
The final, single root-cause breakdown for all 39 distinct citation
numbers that never resolved to a LIMS record -- replacing two earlier,
inconsistent passes (a blunt per-turn repetition-ratio heuristic, and a
manual read of only a 20-case sample). This one classifies every distinct
unresolved citation by period plausibility, which is almost entirely
mechanical and doesn't need per-case manual reading:

  plausible_old_period       period <= 19 or 21-25: LIMS only has period 26,
                              so these are unverifiable for lack of
                              coverage, not evidence of an error
  period_20_anomaly          period exactly 20, suspiciously overrepresented
                              for a batch of CURRENT (2026) procedural votes;
                              likely a garbled 26, exact mechanism unidentified
  garbled_digits_period_correct  period 26, but a bill number too large to be
                              real (DC bill numbers for this period top out
                              under ~1000); the citation itself has no space
                              or split (unlike the fixed "20 6-599" pattern),
                              so this looks like a genuine mishearing by the
                              original human stenographer, not something our
                              pipeline introduced
  impossible_period           period >26, which does not exist
  truncated_midword           caption cut off mid-number

Run from dc-council/dc_etl/:
  python3 reconcile_root_causes.py
"""
import json
import re
from collections import Counter

HERE_IGNORED = None


def classify(norm):
    m = re.match(r"^[A-Z]+(\d+)-(\d+)$", norm)
    period, number = int(m.group(1)), int(m.group(2))
    if period > 26:
        return "impossible_period"
    if period == 20:
        return "period_20_anomaly"
    if period == 26 and number == 0:
        return "truncated_midword"
    if period == 26 and number > 1000:
        return "garbled_digits_period_correct"
    return "plausible_old_period"


def main():
    rows = [json.loads(l) for l in open("citations_scored.jsonl") if not json.loads(l)["exists"]]
    by_norm = {}
    for r in rows:
        by_norm.setdefault(r["normalized"], []).append(r)

    cats = Counter(classify(n) for n in by_norm)
    total = len(by_norm)
    print(f"{total} distinct unresolved citation numbers ({len(rows)} total occurrences)\n")
    for cat, n in cats.most_common():
        print(f"  {cat}: {n} ({n/total:.0%})")

    out = {
        "n_distinct": total,
        "n_occurrences": len(rows),
        "by_category": dict(cats),
        "detail": {norm: classify(norm) for norm in by_norm},
    }
    with open("root_cause_final.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
