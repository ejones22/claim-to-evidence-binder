"""
Compares the automated system's classification (what score_citations.py's
fixed 0.3 threshold would say) against gold labels assigned by an
independent read of each case (benchmark_gold_labels.py) -- the actual
evaluation the earlier critique asked for: not pipeline counts, but
measured precision/recall against a human-reviewed benchmark.

Run from dc-council/dc_etl/:
  python3 compute_benchmark_metrics.py
"""
import json

from benchmark_gold_labels import (
    WEAK_GOLD, NO_CONTEXT_GOLD, NOT_FOUND_ROOT_CAUSE, SUPPORTED_POOL_OVERRIDES,
)

THRESHOLD = 0.3


def automated_label(overlap):
    return "supported" if overlap >= THRESHOLD else "unverifiable"


def main():
    d = json.load(open("benchmark_sample.json"))

    rows = []  # (gold, automated, bucket)

    # supported pool: 12/35 hand-verified, all correct; the rest inherit
    # that verified accuracy rather than being individually re-labeled
    for i, r in enumerate(d["supported"]):
        gold = SUPPORTED_POOL_OVERRIDES.get(i, "supported")
        rows.append((gold, automated_label(r["topic_overlap"]), "supported_pool"))

    for i, r in enumerate(d["weak"]):
        gold = WEAK_GOLD[i]
        if gold == "unverifiable":
            gold = "unverifiable"
        rows.append((gold, automated_label(r["topic_overlap"]), "weak_pool"))

    for i, r in enumerate(d["no_context"]):
        gold = NO_CONTEXT_GOLD[i]
        rows.append((gold, automated_label(r["topic_overlap"]), "no_context_pool"))

    # synthetic contradicted: gold is "contradicted" by construction;
    # automated label uses overlap against the SWAPPED title
    for r in d["synthetic_contradicted"]:
        from score_citations import significant_words

        def overlap(sentence, title):
            s, t = significant_words(sentence), significant_words(title)
            return len(s & t) / len(t) if t else 0.0

        swapped_overlap = overlap(r["context"], r["swapped_title"])
        auto = automated_label(swapped_overlap)
        rows.append(("contradicted", auto, "synthetic_contradicted"))

    # --- confusion matrix: treat "supported" as positive, everything else negative ---
    tp = sum(1 for g, a, _ in rows if g == "supported" and a == "supported")
    fp = sum(1 for g, a, _ in rows if g != "supported" and a == "supported")
    fn = sum(1 for g, a, _ in rows if g == "supported" and a != "supported")
    tn = sum(1 for g, a, _ in rows if g != "supported" and a != "supported")

    print(f"n = {len(rows)}")
    print(f"\nConfusion matrix (positive class = 'supported' at threshold {THRESHOLD}):")
    print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"  precision = {precision:.1%}  recall = {recall:.1%}")

    # breakdown by pool
    print("\nBy pool:")
    for pool in ["supported_pool", "weak_pool", "no_context_pool", "synthetic_contradicted"]:
        pool_rows = [(g, a) for g, a, p in rows if p == pool]
        agree = sum(1 for g, a in pool_rows if (g == "supported") == (a == "supported"))
        print(f"  {pool}: n={len(pool_rows)}, automated/gold agree on supported-vs-not: "
              f"{agree}/{len(pool_rows)} ({agree/len(pool_rows):.0%})")

    print("\nGold label breakdown among weak+no_context (the disagreement zone):")
    from collections import Counter
    gold_counts = Counter(g for g, a, p in rows if p in ("weak_pool", "no_context_pool"))
    for label, n in gold_counts.most_common():
        print(f"  {label}: {n}")

    print("\nRoot causes among the 20 unresolved ('not_found') sample:")
    rc_counts = Counter(NOT_FOUND_ROOT_CAUSE.values())
    for label, n in rc_counts.most_common():
        print(f"  {label}: {n}")

    out = {
        "n": len(rows),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision, "recall": recall,
        "not_found_root_causes": dict(rc_counts),
    }
    with open("benchmark_metrics.json", "w") as f:
        json.dump(out, f, indent=2)

    # --- LLM judge baseline, same gold labels, same supported-vs-not frame ---
    import os
    if not os.path.exists("llm_judge_results.json"):
        return
    llm_results = json.load(open("llm_judge_results.json"))

    gold_by_pool_index = {
        "weak_pool": WEAK_GOLD,
        "no_context_pool": NO_CONTEXT_GOLD,
    }
    idx_counters = {"supported_pool": 0, "weak_pool": 0, "no_context_pool": 0, "synthetic_contradicted": 0}
    llm_tp = llm_fp = llm_fn = llm_tn = 0
    disagreements = []
    for res in llm_results:
        pool = res["pool"]
        i = idx_counters[pool]
        idx_counters[pool] += 1
        if pool == "supported_pool":
            gold = SUPPORTED_POOL_OVERRIDES.get(i, "supported")
        elif pool == "synthetic_contradicted":
            gold = "contradicted"
        else:
            gold = gold_by_pool_index[pool][i]

        gold_pos = gold == "supported"
        llm_pos = res["llm_label"] == "supported"
        if gold_pos and llm_pos:
            llm_tp += 1
        elif not gold_pos and llm_pos:
            llm_fp += 1
            disagreements.append((pool, i, gold, res["llm_label"]))
        elif gold_pos and not llm_pos:
            llm_fn += 1
            disagreements.append((pool, i, gold, res["llm_label"]))
        else:
            llm_tn += 1

    llm_precision = llm_tp / (llm_tp + llm_fp) if (llm_tp + llm_fp) else float("nan")
    llm_recall = llm_tp / (llm_tp + llm_fn) if (llm_tp + llm_fn) else float("nan")

    print(f"\n--- LLM judge baseline ({llm_results[0].get('pool') and 'qwen2.5:7b'}) ---")
    print(f"  TP={llm_tp}  FP={llm_fp}  FN={llm_fn}  TN={llm_tn}")
    print(f"  precision = {llm_precision:.1%}  recall = {llm_recall:.1%}")

    print(f"\n--- Comparison ---")
    print(f"  Deterministic matcher: precision={precision:.1%}  recall={recall:.1%}")
    print(f"  LLM judge (qwen2.5:7b): precision={llm_precision:.1%}  recall={llm_recall:.1%}")

    print(f"\n--- LLM disagreements with gold ({len(disagreements)}) ---")
    for pool, i, gold, llm_label in disagreements:
        print(f"  {pool}[{i}]: gold={gold}  llm={llm_label}")

    out["llm_judge"] = {
        "model": "qwen2.5:7b",
        "confusion_matrix": {"tp": llm_tp, "fp": llm_fp, "fn": llm_fn, "tn": llm_tn},
        "precision": llm_precision, "recall": llm_recall,
    }
    with open("benchmark_metrics.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
