"""
Extends sensitivity_strict_supported.py's correction to every judge in the
project, not just the original qwen2.5:7b headline comparison -- including
Andreas's hosted judges (Jev, Claude Haiku 5.5, Claude Sonnet 5.5). The
"supported" gold-label bias the independent rater2 review found applies to
ALL of them equally: they were all scored against the same 200 cases and
the same gold labels, so if those labels over-credit "supported," every
judge's reported accuracy is inflated by the same mechanism, not just the
one model the original sensitivity check covered.

This only RESCORES already-collected judge outputs against the corrected
gold -- no judge is re-run, no API is called again, no additional cost.

Run from dc_council/:
  python3 sensitivity_all_judges.py
"""
import json

from sensitivity_strict_supported import STRICT_OVERRIDES, gold_for

RUNS = [
    ("qwen2.5:3b (local)", "llm_judge_results_qwen2.5-3b.json"),
    ("qwen2.5:7b (local)", "llm_judge_results.json"),
    ("qwen3.5:9b (local)", "llm_judge_results_qwen3.5-9b.json"),
    ("Jev 1.13.0 (hosted)", "jev_judge_results.json"),
    ("Claude Haiku 5.5", "claude_haiku_judge_results.json"),
    ("Claude Sonnet 5.5", "claude_sonnet_judge_results.json"),
]

POOL_ORDER = ["supported_pool", "weak_pool", "no_context_pool", "synthetic_contradicted"]


def attach_gold(results, strict):
    idx = {p: 0 for p in POOL_ORDER}
    out = []
    for r in results:
        pool = r["pool"]
        i = idx[pool]
        idx[pool] += 1
        out.append({**r, "gold": gold_for(pool, i, strict)})
    return out


def score(rows):
    covered = [r for r in rows if r["llm_label"] != "unverifiable"]
    errors = sum(1 for r in covered if r["llm_label"] != r["gold"])
    return len(rows), len(covered), errors


def main():
    print(f"Rescoring {len(RUNS)} judges' already-collected outputs under the "
          f"strict gold ({len(STRICT_OVERRIDES)} relabeled cases). No model re-run; "
          f"no new API calls.\n")
    print(f"{'judge':<22} {'n':>5} {'answered':>10} {'orig err':>10} {'strict err':>12} {'delta':>8}")
    rows_out = []
    for name, path in RUNS:
        try:
            raw = json.load(open(path))
        except FileNotFoundError:
            print(f"{name:<22} -- file not found: {path}")
            continue
        n, cov_o, err_o = score(attach_gold(raw, strict=False))
        _, cov_s, err_s = score(attach_gold(raw, strict=True))
        rate_o = err_o / cov_o if cov_o else float("nan")
        rate_s = err_s / cov_s if cov_s else float("nan")
        print(f"{name:<22} {n:>5} {cov_o:>10} {rate_o:>9.1%} {rate_s:>11.1%} {rate_s-rate_o:>+7.1%}")
        rows_out.append({"judge": name, "n": n, "answered": cov_o,
                          "orig_selective_error": rate_o, "strict_selective_error": rate_s})

    with open("sensitivity_all_judges.json", "w") as f:
        json.dump(rows_out, f, indent=2)
    print("\nwrote sensitivity_all_judges.json")


if __name__ == "__main__":
    main()
