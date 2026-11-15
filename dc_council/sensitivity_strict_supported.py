"""
Sensitivity bound for the "supported" gold label bias the independent
rater2 review surfaced (README "Inter-rater check"): rater2 required the
transcript to actually CONFIRM a measure's specific content, not just
mention its topic/number alongside siblings. All 9 of rater2's
disagreements with the original gold went this direction.

That review covered only a blind 30-case sample. This script applies the
same, now-explicit standard by hand to the REST of the "supported" gold
label's 95 cases (53 supported_pool + 32 weak_pool + 10 no_context_pool
overrides) -- the pools the 30-case sample was drawn from -- and
recomputes the headline abstention-vs-forced numbers under the stricter
relabeling, as an upper/lower bound alongside the original result.

Rule applied (bright-line, not case-by-case literary judgment, so it's
reproducible): a case keeps "supported" only if the transcript states at
least one fact specific to THIS measure (a mechanism, a dollar figure, a
named confirmee tied to this exact resolution) -- not just a bill number
read aloud, pure procedural/vote text, or framing shared generically with
a sibling bill mentioned in the same breath.

This is a documented, disclosed bound, not a replacement gold standard --
it was applied by one person (me), not independently reviewed itself.

Run from dc-council/dc_etl/:
  python3 sensitivity_strict_supported.py
"""
import json

from benchmark_gold_labels import WEAK_GOLD, NO_CONTEXT_GOLD, SUPPORTED_POOL_OVERRIDES

POOL_ORDER = ["supported_pool", "weak_pool", "no_context_pool", "synthetic_contradicted"]

# Already found by the independent rater2 review (the 9 disagreements) --
# applied here too so the sensitivity bound is cumulative, not a separate
# partial count.
RATER2_CONFIRMED = {
    ("supported_pool", 8): "unverifiable",
    ("weak_pool", 37): "unverifiable",
    ("weak_pool", 16): "unverifiable",
    ("weak_pool", 5): "unverifiable",
    ("weak_pool", 14): "unverifiable",
    ("weak_pool", 2): "unverifiable",
    ("weak_pool", 27): "contradicted",  # also: correct bill, garbled street number (error_taxonomy G)
    ("no_context_pool", 44): "unverifiable",
    ("no_context_pool", 12): "unverifiable",
}

# Newly found by applying rater2's standard to the rest of the "supported"
# pools by hand (this script's own pass, Nov 15). All "no real measure-
# specific content" misses -- pure name/number reads, pure procedural
# votes, or framing shared generically with a sibling bill in the same
# breath.
NEW_STRICT_FAILS = {
    ("weak_pool", 4): "unverifiable",   # "PR26-764. Councilmember Pinto." -- no content
    ("weak_pool", 7): "unverifiable",   # distinguishing two bills, no content landed on either
    ("weak_pool", 8): "unverifiable",   # generic AV-benefits framing, not this bill's mechanism
    ("weak_pool", 9): "unverifiable",   # "PR26-736. Bundle Disposition Resolution. Councilmember Frumin." -- no content
    ("weak_pool", 11): "unverifiable",  # "I have already spoken to the bill today" -- no content in window
    ("weak_pool", 23): "unverifiable",  # generic AV policy commentary, not this bill's mechanism
    ("weak_pool", 25): "unverifiable",  # pure procedural final-reading vote, no content
    ("weak_pool", 29): "unverifiable",  # two bills read by nickname together, no content on either
    ("weak_pool", 35): "unverifiable",  # pure procedural vote ("all those in favor say aye")
    ("no_context_pool", 7): "unverifiable",   # pastor's general advocacy remarks, no bill content
    ("no_context_pool", 15): "unverifiable",  # "Bill 26-427, reporting, the Committee on Health." -- no content
}

STRICT_OVERRIDES = {**RATER2_CONFIRMED, **NEW_STRICT_FAILS}


def gold_for(pool, i, strict):
    if strict and (pool, i) in STRICT_OVERRIDES:
        return STRICT_OVERRIDES[(pool, i)]
    if pool == "supported_pool":
        return SUPPORTED_POOL_OVERRIDES.get(i, "supported")
    if pool == "synthetic_contradicted":
        return "contradicted"
    if pool == "weak_pool":
        return WEAK_GOLD[i]
    if pool == "no_context_pool":
        return NO_CONTEXT_GOLD[i]
    raise ValueError(pool)


def attach_gold(results, strict):
    idx = {p: 0 for p in POOL_ORDER}
    out = []
    for r in results:
        pool = r["pool"]
        i = idx[pool]
        idx[pool] += 1
        out.append({**r, "gold": gold_for(pool, i, strict)})
    return out


def score_abstaining(rows):
    covered = [r for r in rows if r["llm_label"] != "unverifiable"]
    errors = sum(1 for r in covered if r["llm_label"] != r["gold"])
    return {"coverage": len(covered) / len(rows), "n_covered": len(covered),
            "n_errors": errors, "error_rate": errors / len(covered) if covered else float("nan")}


def score_forced(rows):
    errors = sum(1 for r in rows if r["llm_label"] != r["gold"])
    return {"coverage": 1.0, "n_covered": len(rows), "n_errors": errors, "error_rate": errors / len(rows)}


def main():
    n_strict_total = len(STRICT_OVERRIDES)
    print(f"Strict relabeling moves {n_strict_total} of 95 'supported' cases "
          f"({n_strict_total/95:.0%}) to unverifiable/contradicted:")
    print(f"  {len(RATER2_CONFIRMED)} already confirmed by the independent rater2 review")
    print(f"  {len(NEW_STRICT_FAILS)} newly found applying the same standard to the rest of the pool\n")

    abstaining_raw = json.load(open("llm_judge_results.json"))
    forced_raw = json.load(open("llm_forced_results.json"))

    for label, strict in [("ORIGINAL gold", False), ("STRICT (sensitivity bound) gold", True)]:
        abstaining = attach_gold(abstaining_raw, strict)
        forced = attach_gold(forced_raw, strict)
        a = score_abstaining(abstaining)
        f = score_forced(forced)
        print(f"-- {label} --")
        print(f"  Abstaining (qwen2.5:7b): coverage={a['coverage']:.1%}  "
              f"error={a['error_rate']:.1%}  ({a['n_errors']}/{a['n_covered']})")
        print(f"  Forced     (qwen2.5:7b): error={f['error_rate']:.1%}  ({f['n_errors']}/{f['n_covered']})")
        print()

    out = {
        "n_relabeled": n_strict_total,
        "relabeled_from_rater2_review": len(RATER2_CONFIRMED),
        "relabeled_new_this_pass": len(NEW_STRICT_FAILS),
        "cases": {f"{p}#{i}": g for (p, i), g in STRICT_OVERRIDES.items()},
    }
    with open("sensitivity_strict_supported.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote sensitivity_strict_supported.json")


if __name__ == "__main__":
    main()
