"""
Re-scores the held-out test split (05_evaluate.py's leaderboard.md) under
the stricter "supported" gold label from dc_council/sensitivity_strict_
supported.py -- the correction the independent rater2 review's standard
implies once applied to the rest of the supported pools. Every judge in
the leaderboard (Andreas's hosted judges included) was scored against the
same 200 cases and the same gold labels, so this bias isn't specific to
any one judge or to the original qwen2.5:7b baseline -- it applies equally
to every row in leaderboard.md.

Rescoring only -- no judge is re-run, no API is called. Reads the same
results/runs/*.jsonl files 05_evaluate.py already produced.

Run from datapipeline/:
  python3 05b_sensitivity_strict_gold.py
"""
import json
import os

import config
from metrics import coverage, selective_error

import sys
sys.path.insert(0, config.DC_COUNCIL_DIR)
from sensitivity_strict_supported import STRICT_OVERRIDES

POOL_SHORT = {"supported_pool": "supported", "weak_pool": "weak", "no_context_pool": "no_context"}

# case_id -> strict gold_3way, for the cases the correction touches
STRICT_BY_CASE_ID = {
    f"{POOL_SHORT[pool]}-{i:03d}": label
    for (pool, i), label in STRICT_OVERRIDES.items()
}


def load_benchmark():
    cases = {}
    for line in open(config.BENCHMARK_PATH):
        r = json.loads(line)
        cases[r["case_id"]] = r
    return cases


def load_splits():
    return json.load(open(config.SPLITS_PATH))["assignments"]


def main():
    cases = load_benchmark()
    assignments = load_splits()
    test_ids = {cid for cid, split in assignments.items() if split == "test"}

    print(f"Test split: {len(test_ids)} cases. Strict relabeling touches "
          f"{len(STRICT_BY_CASE_ID)} cases project-wide, "
          f"{sum(1 for c in STRICT_BY_CASE_ID if c in test_ids)} of them in test.\n")

    print(f"{'judge':<38} {'n':>5} {'answered':>9} {'orig sel.err':>13} {'strict sel.err':>15} {'delta':>8}")
    out = []
    for fn in sorted(os.listdir(config.RUNS_DIR)):
        if not fn.endswith(".jsonl") or "forced" in fn:
            continue  # abstain-mode only: selective error needs an abstain option
        judge = fn[:-len(".jsonl")].replace("__", "/")
        rows = [json.loads(l) for l in open(os.path.join(config.RUNS_DIR, fn))]
        test_rows = [r for r in rows if r["case_id"] in test_ids]
        if not test_rows:
            continue

        orig_rows = [{**r, "gold": cases[r["case_id"]]["gold_3way"]} for r in test_rows]
        strict_rows = [{**r, "gold": STRICT_BY_CASE_ID.get(r["case_id"], cases[r["case_id"]]["gold_3way"])}
                       for r in test_rows]

        cov = coverage(orig_rows)
        err_o = selective_error(orig_rows)
        err_s = selective_error(strict_rows)
        n_answered = round(cov * len(test_rows))
        print(f"{judge:<38} {len(test_rows):>5} {n_answered:>9} {err_o:>12.1%} {err_s:>14.1%} {err_s-err_o:>+7.1%}")
        out.append({"judge": judge, "n_test": len(test_rows), "answered": n_answered,
                     "orig_selective_error": err_o, "strict_selective_error": err_s})

    with open(os.path.join(config.RESULTS_DIR, "sensitivity_strict_gold_test.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote results/sensitivity_strict_gold_test.json")


if __name__ == "__main__":
    main()
