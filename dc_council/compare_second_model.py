"""
Same abstention-vs-forced comparison as compare_abstention.py, run against
qwen2.5:3b's results instead of qwen2.5:7b's -- does the pattern hold with
a smaller, different model? (qwen3.5:9b was tried first but is a
"thinking" model at ~54s/call -- 240 calls would take 3+ hours, so this
robustness check uses qwen2.5:3b instead.)

Run from dc-council/dc_etl/:
  python3 compare_second_model.py
"""
import json

from benchmark_gold_labels import WEAK_GOLD, NO_CONTEXT_GOLD, SUPPORTED_POOL_OVERRIDES

POOL_ORDER = ["supported_pool", "weak_pool", "no_context_pool", "synthetic_contradicted"]


def gold_for(pool, i):
    if pool == "supported_pool":
        return SUPPORTED_POOL_OVERRIDES.get(i, "supported")
    if pool == "synthetic_contradicted":
        return "contradicted"
    if pool == "weak_pool":
        return WEAK_GOLD[i]
    if pool == "no_context_pool":
        return NO_CONTEXT_GOLD[i]
    raise ValueError(pool)


def attach_gold(results):
    idx = {p: 0 for p in POOL_ORDER}
    out = []
    for r in results:
        pool = r["pool"]
        i = idx[pool]
        idx[pool] += 1
        out.append({**r, "gold": gold_for(pool, i)})
    return out


def score_abstaining(rows):
    covered = [r for r in rows if r["llm_label"] != "unverifiable"]
    errors = [r for r in covered if r["llm_label"] != r["gold"]]
    return len(covered) / len(rows), (len(errors) / len(covered) if covered else float("nan")), len(covered), len(errors)


def score_forced(rows):
    errors = [r for r in rows if r["llm_label"] != r["gold"]]
    return 1.0, len(errors) / len(rows), len(rows), len(errors)


def main():
    abstaining = attach_gold(json.load(open("llm_judge_results_qwen3.5-9b.json")))
    forced = attach_gold(json.load(open("llm_forced_results_qwen3.5-9b.json")))

    a_cov, a_err, a_n, a_errs = score_abstaining(abstaining)
    f_cov, f_err, f_n, f_errs = score_forced(forced)

    print("qwen3.5:9b (robustness check: larger model, thinking suppressed), same 120 cases, same prompts as the qwen2.5:7b run.\n")
    print(f"{'':25} {'coverage':>10} {'error rate':>12} {'errors/covered':>16}")
    print(f"{'Abstaining (3-way)':25} {a_cov:>10.1%} {a_err:>12.1%} {a_errs:>8}/{a_n}")
    print(f"{'Forced (2-way)':25} {f_cov:>10.1%} {f_err:>12.1%} {f_errs:>8}/{f_n}")

    # same-cases comparison, as in significance_test.py
    covered_idx = [i for i, r in enumerate(abstaining) if r["llm_label"] != "unverifiable"]
    forced_same = [forced[i] for i in covered_idx]
    same_errors = sum(1 for r in forced_same if r["llm_label"] != r["gold"])
    print(f"\nForced, restricted to the same {len(covered_idx)} cases abstaining covered: "
          f"{same_errors}/{len(covered_idx)} = {same_errors/len(covered_idx):.1%} error rate")
    print(f"(compare to abstaining's {a_err:.1%} on those same cases -- "
          f"tests selection-effect vs. per-judgment-quality, same as the qwen2.5:7b analysis)")


if __name__ == "__main__":
    main()
