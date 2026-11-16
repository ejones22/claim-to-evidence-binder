"""
Apples-to-apples judge comparison: restricts every judge to the exact SAME
set of test-split cases -- the ones every judge in the comparison actually
answered (none abstained) -- instead of comparing each judge's selective
error on its own, different set of covered cases. Coverage varies a lot
across judges (58%-74%), so the leaderboard's ranking partly reflects WHICH
cases each judge chose to answer, not just how well it answered them.

Reports both the original and strict (sensitivity_strict_supported.py)
gold, so the shared-cases comparison and the label-bias correction are
shown together rather than as two separate, harder-to-reconcile tables.

Rescoring only -- no judge is re-run, no API is called.

Run from datapipeline/:
  python3 05c_shared_cases_comparison.py
"""
import json
import os
import sys

import config
from metrics import mcnemar_exact

sys.path.insert(0, config.DC_COUNCIL_DIR)
from sensitivity_strict_supported import STRICT_OVERRIDES

POOL_SHORT = {"supported_pool": "supported", "weak_pool": "weak", "no_context_pool": "no_context"}
STRICT_BY_CASE_ID = {f"{POOL_SHORT[p]}-{i:03d}": lab for (p, i), lab in STRICT_OVERRIDES.items()}

JUDGES = [
    "legacy__qwen2.5:7b__abstain",
    "legacy__qwen3.5:9b__abstain",
    "jev__jev-1.13.0__abstain",
    "adaption__qwen3.5-397b__abstain",
    "anthropic__claude-haiku-5-5__abstain",
    "anthropic__claude-sonnet-5-5__abstain",
    "decision__d3:4b-q8_0__abstain",
]


def load_run(name):
    return {r["case_id"]: r for r in (json.loads(l) for l in open(os.path.join(config.RUNS_DIR, name + ".jsonl")))}


def main():
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(config.BENCHMARK_PATH)}
    test_ids = {cid for cid, sp in json.load(open(config.SPLITS_PATH))["assignments"].items() if sp == "test"}

    runs = {j: load_run(j) for j in JUDGES}

    # cases every judge both HAS a result for on the test split, AND answered (didn't abstain)
    shared = set(test_ids)
    for j, rows in runs.items():
        answered = {cid for cid, r in rows.items() if cid in test_ids and r["label"] != "unverifiable"}
        shared &= answered

    print(f"Test split: {len(test_ids)} cases. Shared cases every judge answered: {len(shared)}\n")
    print(f"{'judge':<38} {'orig err (shared)':>18} {'strict err (shared)':>20}")

    results = {}
    for j in JUDGES:
        rows = runs[j]
        orig_wrong = strict_wrong = 0
        for cid in shared:
            r = rows[cid]
            orig_gold = cases[cid]["gold_3way"]
            strict_gold = STRICT_BY_CASE_ID.get(cid, orig_gold)
            if r["label"] != orig_gold:
                orig_wrong += 1
            if r["label"] != strict_gold:
                strict_wrong += 1
        n = len(shared)
        orig_rate, strict_rate = orig_wrong / n, strict_wrong / n
        results[j] = {"n": n, "orig_error": orig_rate, "strict_error": strict_rate,
                      "rows": [{"case_id": cid, "label": rows[cid]["label"]} for cid in shared]}
        print(f"{j:<38} {orig_rate:>17.1%} {strict_rate:>19.1%}")

    # McNemar's: Haiku vs Sonnet specifically, on the shared cases, under strict gold --
    # does Haiku's edge over Sonnet (once relabeled) hold up as more than noise?
    def rows_with_gold(j, gold_map):
        return [{"case_id": cid, "gold": gold_map(cid), "label": runs[j][cid]["label"]} for cid in shared]

    strict_gold_fn = lambda cid: STRICT_BY_CASE_ID.get(cid, cases[cid]["gold_3way"])
    haiku_rows = rows_with_gold("anthropic__claude-haiku-5-5__abstain", strict_gold_fn)
    sonnet_rows = rows_with_gold("anthropic__claude-sonnet-5-5__abstain", strict_gold_fn)
    mc = mcnemar_exact(haiku_rows, sonnet_rows)
    print(f"\nMcNemar's, Haiku vs Sonnet on the {len(shared)} shared cases, strict gold: "
          f"n10={mc['n10']} n01={mc['n01']} p={mc['p_value']}")

    out = {"n_shared": len(shared), "shared_case_ids": sorted(shared),
           "results": {j: {"n": v["n"], "orig_error": v["orig_error"], "strict_error": v["strict_error"]}
                       for j, v in results.items()},
           "mcnemar_haiku_vs_sonnet_strict": mc}
    with open(os.path.join(config.RESULTS_DIR, "shared_cases_comparison.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote results/shared_cases_comparison.json")


if __name__ == "__main__":
    main()
