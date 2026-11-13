"""
Two things the earnings-call critique correctly said were missing: does the
topic-overlap metric actually discriminate real matches from fake ones
(not just picking up generic words like "amendment act"), and what does
the coverage/error tradeoff look like as the confidence threshold moves.

Real natural "contradicted" cases are rare in civic speech -- council
members don't often misstate a bill number on the record, which is itself
worth reporting -- so contradictions are constructed: every real citation
that was discussed with vocabulary matching its own official title (a
positive) is also paired with a title swapped in from a different,
randomly chosen bill elsewhere in the corpus (a negative, wrong by
construction). The overlap metric is recomputed against the SAME spoken
context for both, so this isolates whether the metric tracks the content
of the bill rather than generic legislative phrasing in the sentence.

Run from dc-council/dc_etl/:
  python3 validate_citation_binding.py
"""
import json
import os
import random

from score_citations import significant_words

HERE = os.path.dirname(os.path.abspath(__file__))


def topic_overlap(sentence, title):
    s_words = significant_words(sentence)
    t_words = significant_words(title)
    if not t_words:
        return 0.0
    return len(s_words & t_words) / len(t_words)


def main():
    random.seed(42)
    rows = [json.loads(l) for l in open(os.path.join(HERE, "citations_scored.jsonl"))]
    # overlap == 0 isn't a weak match -- it's "no description given at all"
    # (689 of 1449), a separate abstention bucket, not a classifier question.
    # Only citations that got SOME description are a fair test of whether
    # the metric can tell a real description from a wrong one.
    no_context = [r for r in rows if r.get("exists") and r.get("topic_overlap", 0) == 0]
    positives = [r for r in rows if r.get("exists") and r.get("topic_overlap", 0) > 0]
    print(f"{len(no_context)} citations with no description at all (excluded from this test)")
    print(f"{len(positives)} citations with some description, to pair with swapped titles")

    all_titles = list({r["official_title"] for r in rows if r.get("official_title")})

    pos_scores, neg_scores = [], []
    for r in positives:
        pos_scores.append(r["topic_overlap"])
        wrong_title = random.choice(all_titles)
        while wrong_title == r["official_title"]:
            wrong_title = random.choice(all_titles)
        neg_scores.append(round(topic_overlap(r["context"], wrong_title), 2))

    def summary(label, scores):
        scores_sorted = sorted(scores)
        n = len(scores_sorted)
        mean = sum(scores_sorted) / n
        median = scores_sorted[n // 2]
        print(f"{label}: n={n}  mean={mean:.3f}  median={median:.3f}  "
              f"min={scores_sorted[0]:.2f}  max={scores_sorted[-1]:.2f}")

    print("\n--- Validity check: does the metric discriminate real from fake pairings? ---")
    summary("Real (correct) title", pos_scores)
    summary("Swapped (wrong) title", neg_scores)

    print("\n--- Risk-coverage curve: sweep the acceptance threshold ---")
    print(f"{'threshold':>10} {'coverage':>10} {'false_accept_rate':>20}")
    for t in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        coverage = sum(1 for s in pos_scores if s >= t) / len(pos_scores)
        false_accept = sum(1 for s in neg_scores if s >= t) / len(neg_scores)
        print(f"{t:>10.1f} {coverage:>10.1%} {false_accept:>20.1%}")

    out = {
        "n_positive": len(pos_scores),
        "n_negative": len(neg_scores),
        "positive_scores": pos_scores,
        "negative_scores": neg_scores,
        "risk_coverage": [
            {"threshold": t,
             "coverage": sum(1 for s in pos_scores if s >= t) / len(pos_scores),
             "false_accept_rate": sum(1 for s in neg_scores if s >= t) / len(neg_scores)}
            for t in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ],
    }
    with open(os.path.join(HERE, "validity_check.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote validity_check.json")


if __name__ == "__main__":
    main()
