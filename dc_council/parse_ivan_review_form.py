"""
Builds the two input files score_ivan_review.py needs:

  ivans_labels.json               -- the second labeler's answers, parsed
                                     from the filled-in ivan_review_form.txt
  my_labels_for_ivan_sample.json  -- the original gold labels for the same
                                     30 cases, from benchmark_gold_labels.py

The form shown to the reviewer uses redacted, non-unique ids (e.g.
"redacted_1" appears on three cases) so the sampling pool -- which hints
at the gold label -- stays hidden. Answers are therefore mapped back to
the real ids by case order: CASE n in the form is entry n-1 in
ivan_blind_sample.json. Each case's CONTEXT text is checked against the
sample entry to make sure the order really lines up.

The one gold label of "uncertain" (no_context_1) is mapped to
"unverifiable", the same convention significance_test.py uses, since
"uncertain" isn't one of the three labels the reviewer could choose.

Usage:
  python3 parse_ivan_review_form.py
  python3 score_ivan_review.py
"""
import json
import re

from benchmark_gold_labels import (
    NO_CONTEXT_GOLD,
    SUPPORTED_POOL_OVERRIDES,
    WEAK_GOLD,
)

VALID = {"supported", "contradicted", "unverifiable"}


def gold_for(sample_id):
    pool, idx = sample_id.rsplit("_", 1)
    idx = int(idx)
    if pool == "supported":
        label = SUPPORTED_POOL_OVERRIDES.get(idx, "supported")
    elif pool == "weak":
        label = WEAK_GOLD[idx]
    elif pool == "no_context":
        label = NO_CONTEXT_GOLD[idx]
    else:
        raise ValueError(f"Unexpected pool for {sample_id}")
    return "unverifiable" if label == "uncertain" else label


def parse_form(path):
    text = open(path).read()
    blocks = re.split(r"^-{20,}\s*$", text, flags=re.M)
    cases = []
    for block in blocks:
        m = re.search(r"CASE (\d+) \(id: [^)]*\)", block)
        if not m:
            continue
        ctx = re.search(r"^CONTEXT: ?(.*)$", block, flags=re.M)
        lab = re.search(r"^YOUR LABEL: *(\S*)", block, flags=re.M)
        cases.append({
            "case": int(m.group(1)),
            "context": ctx.group(1) if ctx else "",
            "label": lab.group(1).lower().strip() if lab else "",
        })
    return cases


def main():
    sample = json.load(open("ivan_blind_sample.json"))
    cases = parse_form("ivan_review_form.txt")

    if len(cases) != len(sample):
        raise SystemExit(f"Form has {len(cases)} cases, sample has {len(sample)}")

    ivans, mine = {}, {}
    for n, (case, entry) in enumerate(zip(cases, sample), start=1):
        if case["case"] != n:
            raise SystemExit(f"Case numbering out of order at position {n}")
        if case["context"].strip() != entry["context"].strip():
            raise SystemExit(f"CASE {n}: context doesn't match {entry['id']}")
        if case["label"] not in VALID:
            raise SystemExit(f"CASE {n}: invalid or blank label {case['label']!r}")
        ivans[entry["id"]] = case["label"]
        mine[entry["id"]] = gold_for(entry["id"])

    json.dump(ivans, open("ivans_labels.json", "w"), indent=2)
    json.dump(mine, open("my_labels_for_ivan_sample.json", "w"), indent=2)
    print(f"Wrote ivans_labels.json and my_labels_for_ivan_sample.json ({len(ivans)} cases)")


if __name__ == "__main__":
    main()
