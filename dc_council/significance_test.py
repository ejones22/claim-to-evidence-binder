"""
Is the abstention result (compare_abstention.py) actually significant, or
within noise for n=120? Two complementary tests:

1. McNemar's exact test, restricted to the 76 cases the abstaining system
   was willing to judge -- same model, same items, only the prompt differs
   (abstain allowed vs not). This isolates whether letting the model say
   "I don't know" changes its answer QUALITY on cases it judges either way,
   controlling for item selection.
2. Bootstrap 95% CIs on each system's error rate (10,000 resamples), to
   see whether the abstaining system's 11.8% and the forced system's 36.7%
   (on the full 120, and separately on just the 76 both judge) are
   distinguishable or could plausibly be the same rate under resampling.

Run from dc-council/dc_etl/:
  python3 significance_test.py
"""
import json
import random

from scipy.stats import binomtest

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


def bootstrap_error_rate(rows, covered_only, n_resamples=10000, seed=0):
    rng = random.Random(seed)
    n = len(rows)
    rates = []
    for _ in range(n_resamples):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        if covered_only:
            sample = [r for r in sample if r["llm_label"] != "unverifiable"]
            if not sample:
                continue
            errors = sum(1 for r in sample if r["llm_label"] != r["gold"])
            rates.append(errors / len(sample))
        else:
            errors = sum(1 for r in sample if r["llm_label"] != r["gold"])
            rates.append(errors / len(sample))
    rates.sort()
    lo = rates[int(0.025 * len(rates))]
    hi = rates[int(0.975 * len(rates))]
    return sum(rates) / len(rates), lo, hi


def main():
    abstaining = attach_gold(json.load(open("llm_judge_results.json")))
    forced = attach_gold(json.load(open("llm_forced_results.json")))

    # --- McNemar's, restricted to the cases abstaining actually judged ---
    covered_idx = [i for i, r in enumerate(abstaining) if r["llm_label"] != "unverifiable"]
    print(f"Cases both systems judge (abstaining chose to answer): {len(covered_idx)}")

    n01 = n10 = n00 = n11 = 0  # [abstaining_correct][forced_correct]
    for i in covered_idx:
        a_correct = abstaining[i]["llm_label"] == abstaining[i]["gold"]
        f_correct = forced[i]["llm_label"] == forced[i]["gold"]
        if a_correct and f_correct:
            n11 += 1
        elif a_correct and not f_correct:
            n10 += 1  # abstaining right, forced wrong
        elif not a_correct and f_correct:
            n01 += 1  # abstaining wrong, forced right
        else:
            n00 += 1

    print(f"\nOn these {len(covered_idx)} cases (both systems answered):")
    print(f"  both correct: {n11}  both wrong: {n00}")
    print(f"  abstaining right, forced wrong: {n10}")
    print(f"  abstaining wrong, forced right: {n01}")

    discordant = n10 + n01
    if discordant > 0:
        result = binomtest(min(n10, n01), discordant, 0.5, alternative="two-sided")
        print(f"\nMcNemar's exact test on {discordant} discordant pairs: p = {result.pvalue:.4f}")
    else:
        print("\nNo discordant pairs -- McNemar's test undefined")

    # --- bootstrap CIs ---
    a_mean, a_lo, a_hi = bootstrap_error_rate(abstaining, covered_only=True)
    f_mean, f_lo, f_hi = bootstrap_error_rate(forced, covered_only=False)
    # forced, restricted to the same 76 cases abstaining covered (apples to apples)
    forced_same_cases = [forced[i] for i in covered_idx]
    f2_mean, f2_lo, f2_hi = bootstrap_error_rate(forced_same_cases, covered_only=False)

    print(f"\nBootstrap 95% CIs (10,000 resamples):")
    print(f"  Abstaining, error rate on covered cases:      {a_mean:.1%}  [{a_lo:.1%}, {a_hi:.1%}]")
    print(f"  Forced, error rate on ALL {len(forced)} cases:            {f_mean:.1%}  [{f_lo:.1%}, {f_hi:.1%}]")
    print(f"  Forced, error rate on the SAME 76 covered cases: {f2_mean:.1%}  [{f2_lo:.1%}, {f2_hi:.1%}]")
    overlap = not (a_hi < f2_lo or f2_hi < a_lo)
    print(f"  CIs for abstaining vs. forced-on-same-cases overlap: {overlap}")

    out = {
        "mcnemar": {"n10_abstain_right_forced_wrong": n10, "n01_abstain_wrong_forced_right": n01,
                    "n_discordant": discordant,
                    "p_value": result.pvalue if discordant > 0 else None},
        "bootstrap": {
            "abstaining_covered": {"mean": a_mean, "ci95": [a_lo, a_hi]},
            "forced_all_120": {"mean": f_mean, "ci95": [f_lo, f_hi]},
            "forced_same_76": {"mean": f2_mean, "ci95": [f2_lo, f2_hi]},
        },
    }
    with open("significance_results.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
