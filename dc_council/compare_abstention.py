"""
The actual headline result: does letting the verifier abstain (llm_judge_
baseline.py, 3-way) lower its error rate on the judgments it DOES make,
compared to a system forced to always commit (llm_forced_baseline.py,
2-way), run on the exact same 120 cases with the exact same model?

"Error" here means: the system's non-abstained answer disagrees with gold,
OR (for the forced system specifically) it confidently answered a case
gold says was genuinely unverifiable -- claiming certainty the evidence
didn't support is exactly the failure mode abstention exists to prevent.

Run from dc-council/dc_etl/:
  python3 compare_abstention.py
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
    """3-way: 'unverifiable' is a deliberate non-answer, not a wrong answer."""
    covered = [r for r in rows if r["llm_label"] != "unverifiable"]
    errors = [r for r in covered if r["llm_label"] != r["gold"]]
    coverage = len(covered) / len(rows)
    error_rate = len(errors) / len(covered) if covered else float("nan")
    return coverage, error_rate, len(covered), len(errors)


def score_forced(rows):
    """2-way: every answer counts as covered. Gold 'uncertain'/'unverifiable'
    cases are errors by construction -- the system claimed a confidence the
    evidence didn't support, which is exactly what abstention is for."""
    errors = [r for r in rows if r["llm_label"] != r["gold"]]
    coverage = 1.0
    error_rate = len(errors) / len(rows)
    return coverage, error_rate, len(rows), len(errors)


def main():
    abstaining = attach_gold(json.load(open("llm_judge_results.json")))
    forced = attach_gold(json.load(open("llm_forced_results.json")))

    a_cov, a_err, a_n, a_errs = score_abstaining(abstaining)
    f_cov, f_err, f_n, f_errs = score_forced(forced)

    print("Same model (qwen2.5:7b), same 120 cases, same context+title inputs.\n")
    print(f"{'':25} {'coverage':>10} {'error rate':>12} {'errors/covered':>16}")
    print(f"{'Abstaining (3-way)':25} {a_cov:>10.1%} {a_err:>12.1%} {a_errs:>8}/{a_n}")
    print(f"{'Forced (2-way)':25} {f_cov:>10.1%} {f_err:>12.1%} {f_errs:>8}/{f_n}")

    print(f"\nAbstaining drops coverage by {1 - a_cov:.1%} of cases,")
    print(f"and in exchange cuts the error rate on what it DOES judge "
          f"from {f_err:.1%} to {a_err:.1%}.")

    # breakdown: of the forced system's errors, how many were on genuinely
    # unverifiable gold cases (claimed confidence with no real basis) vs.
    # genuinely wrong calls on a determinate case?
    forced_errors = [r for r in forced if r["llm_label"] != r["gold"]]
    on_unverifiable = sum(1 for r in forced_errors if r["gold"] in ("unverifiable", "uncertain"))
    on_wrong_side = len(forced_errors) - on_unverifiable
    print(f"\nOf the forced system's {len(forced_errors)} errors:")
    print(f"  {on_unverifiable} were confidently answering a case with no real evidence")
    print(f"  {on_wrong_side} were picking the wrong side of a determinate case")

    out = {
        "abstaining": {"coverage": a_cov, "error_rate": a_err, "n_covered": a_n, "n_errors": a_errs},
        "forced": {"coverage": f_cov, "error_rate": f_err, "n_covered": f_n, "n_errors": f_errs,
                   "errors_on_unverifiable": on_unverifiable, "errors_on_wrong_side": on_wrong_side},
    }
    with open("abstention_comparison.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
