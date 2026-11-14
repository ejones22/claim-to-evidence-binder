"""
Stress-test the validity check: random title swaps mostly produce wildly
different topics (a cannabis bill vs. a tax resolution), which is a soft
target -- real citation errors found by hand (B26-0679 "soccer stadium"
vs. its real water/sewer bill, B26-0231 vs. the Harmony Park content) are
usually the SAME category, wrong specific instance. This rebuilds the
synthetic negatives using only same-category swaps (confirmation-for-
confirmation, designation-for-designation, etc.) and checks whether the
topic-overlap metric's discrimination holds up, or whether it was
inflated by easy, off-topic negatives.

Run from dc-council/dc_etl/:
  python3 hard_negative_check.py
"""
import json
import random

from score_citations import significant_words


def category(title):
    t = title.upper()
    if "CONFIRMATION RESOLUTION" in t:
        return "confirmation"
    if "DESIGNATION ACT" in t:
        return "designation"
    if "SURPLUS DECLARATION" in t or "DISPOSITION" in t:
        return "disposition"
    if "CONTRACT" in t and "APPROVAL" in t:
        return "contract_approval"
    if "REVENUE BOND" in t:
        return "revenue_bonds"
    if "EMERGENCY" in t and "AMENDMENT ACT" in t:
        return "emergency_amendment"
    if "AMENDMENT ACT" in t:
        return "amendment_act"
    return "other"


def topic_overlap(sentence, title):
    s, t = significant_words(sentence), significant_words(title)
    return len(s & t) / len(t) if t else 0.0


def main():
    random.seed(2026)
    rows = [json.loads(l) for l in open("citations_scored.jsonl")]
    positives = [r for r in rows if r.get("exists") and r.get("topic_overlap", 0) > 0]

    by_cat = {}
    for r in rows:
        if r.get("official_title"):
            by_cat.setdefault(category(r["official_title"]), set()).add(r["official_title"])

    easy_scores, hard_scores = [], []
    skipped_no_peers = 0
    for r in positives:
        cat = category(r["official_title"])
        peers = [t for t in by_cat.get(cat, []) if t != r["official_title"]]
        if len(peers) < 2:
            skipped_no_peers += 1
            continue
        easy_title = random.choice(list({t for titles in by_cat.values() for t in titles} - {r["official_title"]}))
        hard_title = random.choice(peers)
        easy_scores.append(round(topic_overlap(r["context"], easy_title), 3))
        hard_scores.append(round(topic_overlap(r["context"], hard_title), 3))

    def summary(label, scores):
        s = sorted(scores)
        n = len(s)
        print(f"{label}: n={n}  mean={sum(s)/n:.3f}  median={s[n//2]:.3f}  "
              f"frac >= 0.3 (would false-accept at our threshold): {sum(1 for x in s if x >= 0.3)/n:.1%}")

    print(f"({skipped_no_peers} positives skipped -- fewer than 2 other titles in their category)\n")
    summary("Easy negatives (fully random swap, original method)", easy_scores)
    summary("Hard negatives (same-category swap)", hard_scores)

    out = {"n": len(easy_scores), "easy_scores": easy_scores, "hard_scores": hard_scores}
    with open("hard_negative_check.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
