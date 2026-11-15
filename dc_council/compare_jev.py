"""
Scores jev_judge.py's results against the same gold labels as the Ollama
judges, on the same benchmark cases, and asks the question Jev was brought
in for: are its probabilities calibrated enough to replace the hand-picked
topic_overlap cutoff with a principled one?

Four views, all on the same cases:
  - head-to-head: coverage / error rate on answered cases, same scoring as
    compare_abstention.py ("unverifiable" is an abstention, not an error);
    also includes Claude Haiku 5.5 from claude_batch_judge.py
  - calibration (Jev only): confidence in the chosen label vs how often it is right
  - risk-coverage (Jev only): answer only when P(chosen) >= t
  - router: deterministic matcher accepts topic_overlap >= 0.6, the judge
    handles everything below

Gold "uncertain" is scored as "unverifiable" here.

Run from dc_council/:
  python3 compare_jev.py
Writes jev_comparison.json.
"""
import json
from collections import Counter

from compare_abstention import attach_gold
from score_citations import significant_words

JUDGES = [
    ("jev-1.13.0", "jev_judge_results.json"),
    ("qwen2.5:7b", "llm_judge_results.json"),
    ("qwen3.5:9b", "llm_judge_results_qwen3.5-9b.json"),
    ("claude-haiku-5-5", "claude_haiku_judge_results.json"),
    ("claude-sonnet-5-5", "claude_sonnet_judge_results.json"),
]
ROUTER_THRESHOLD = 0.6
CALIBRATION_BINS = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.01)]
RISK_THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9]


def overlap(sentence, title):
    """topic_overlap: share of the title's significant words found in the sentence (0 if the title has none)."""
    s, t = significant_words(sentence), significant_words(title)
    return len(s & t) / len(t) if t else 0.0


def gold(r):
    """Gold label of a row, with "uncertain" folded into "unverifiable"."""
    return "unverifiable" if r["gold"] == "uncertain" else r["gold"]


def score(rows, label_of=lambda r: r["llm_label"]):
    """
    Score rows against gold. "unverifiable" counts as abstaining: coverage
    and error_rate are over answered rows only, while exact_3way_accuracy
    is over all rows. label_of picks the label so callers can apply a
    router or confidence threshold.
    """
    covered = [r for r in rows if label_of(r) != "unverifiable"]
    errors = sum(1 for r in covered if label_of(r) != gold(r))
    return {"n": len(rows), "n_answered": len(covered), "n_errors": errors,
            "coverage": len(covered) / len(rows),
            "error_rate": errors / len(covered) if covered else float("nan"),
            "exact_3way_accuracy": sum(1 for r in rows if label_of(r) == gold(r)) / len(rows)}


def routed_label(r):
    """Router label: "supported" if the deterministic matcher is confident enough, else the judge's label."""
    if overlap(r["context"], r["title"]) >= ROUTER_THRESHOLD:
        return "supported"
    return r["llm_label"]


def main():
    """
    Print and write jev_comparison.json: head-to-head and router scores for
    every judge, then Jev's confusion matrix, calibration and risk-coverage.
    Jev's case count sets n; other judges are cut to their first n rows
    (same order), so a partial Jev run is compared fairly.
    """
    jev = attach_gold(json.load(open("jev_judge_results.json")))
    n = len(jev)
    if n < 200:
        print(f"note: jev_judge_results.json has only {n} cases -- all judges scored on those {n}")

    out = {"n": n, "head_to_head": {}, "router": {}}
    print(f"{'judge (same %d cases)' % n:28}{'answered':>10}{'errors':>8}{'err rate':>10}{'3-way acc':>11}")
    for name, path in JUDGES:
        rows = attach_gold(json.load(open(path)))[:n]
        s = score(rows)
        out["head_to_head"][name] = s
        out["router"][name] = score(rows, routed_label)
        print(f"{name:28}{s['n_answered']:>10}{s['n_errors']:>8}{s['error_rate']:>10.1%}"
              f"{s['exact_3way_accuracy']:>11.1%}")

    print("\nJev label vs gold:")
    confusion = {}
    for g in ["supported", "contradicted", "unverifiable"]:
        confusion[g] = dict(Counter(r["llm_label"] for r in jev if gold(r) == g))
        print(f"  gold {g:13} {confusion[g]}")
    out["jev_confusion"] = confusion

    print("\nCalibration: confidence in chosen label vs how often it is right")
    out["calibration"] = []
    for lo, hi in CALIBRATION_BINS:
        b = [r for r in jev if lo <= max(r["jev_probabilities"].values()) < hi]
        if not b:
            continue
        right = sum(1 for r in b if r["llm_label"] == gold(r)) / len(b)
        mean_p = sum(max(r["jev_probabilities"].values()) for r in b) / len(b)
        out["calibration"].append({"lo": lo, "hi": min(hi, 1.0), "n": len(b),
                                   "fraction_right": right, "mean_confidence": mean_p})
        print(f"  P(chosen) {lo:.1f}-{min(hi, 1):.1f}: n={len(b):3}  right={right:.0%}  mean P={mean_p:.2f}")

    print("\nRisk-coverage: answer only when P(chosen) >= t (thresholds NOT cross-validated)")
    out["risk_coverage"] = []
    for t in RISK_THRESHOLDS:
        s = score(jev, lambda r: r["llm_label"]
                  if max(r["jev_probabilities"].values()) >= t else "unverifiable")
        out["risk_coverage"].append({"threshold": t, **s})
        print(f"  t={t:.1f}  answered={s['n_answered']:3} ({s['coverage']:.0%})  "
              f"errors={s['n_errors']:2}  err={s['error_rate']:.1%}")

    print(f"\nRouter: matcher accepts topic_overlap >= {ROUTER_THRESHOLD}, judge handles the rest")
    for name, s in out["router"].items():
        print(f"  {name:12} answered={s['n_answered']:3}  errors={s['n_errors']:2}  err={s['error_rate']:.1%}")

    with open("jev_comparison.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote jev_comparison.json")


if __name__ == "__main__":
    main()
