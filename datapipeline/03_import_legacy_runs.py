"""
Step 3: bring the runs dc_council/ already made (qwen2.5:7b, qwen2.5:3b,
qwen3.5:9b, abstain + forced) into the pipeline's run format, so they're
baselines on the leaderboard without re-running them (SPEC.md 4.6).

The legacy result files are lists in pool order, and the legacy scorers
attach gold by counting position. Here every row is matched to its case
by (pool, context, title) instead, and the import fails if any row
matches zero or more than one case -- a wrong join is worse than none.

The qwen2.5:3b files only cover the original 120-case benchmark; they're
imported as-is and 05_evaluate.py reports them as partial ("missing").

Run from datapipeline/:
  python3 03_import_legacy_runs.py
Writes results/runs/legacy__*.jsonl.
"""
import json
import os
from collections import defaultdict

import config

LEGACY_POOL = {  # pool name inside the legacy result files -> case pool
    "supported_pool": "supported",
    "weak_pool": "weak",
    "no_context_pool": "no_context",
    "synthetic_contradicted": "synthetic_contradicted",
}


def main():
    os.makedirs(config.RUNS_DIR, exist_ok=True)
    cases = [json.loads(l) for l in open(config.BENCHMARK_PATH)]
    by_key = defaultdict(list)
    for c in cases:
        by_key[(c["pool"], c["context"], c["title"])].append(c["case_id"])

    for name, judge in config.JUDGES.items():
        if judge["backend"] != "legacy":
            continue
        legacy = json.load(open(os.path.join(config.DC_COUNCIL_DIR, judge["file"])))
        rows, seen = [], set()
        for r in legacy:
            matches = by_key[(LEGACY_POOL[r["pool"]], r["context"], r["title"])]
            if len(matches) != 1:
                raise RuntimeError(f"{judge['file']}: legacy row matches {len(matches)} cases "
                                   f"(pool={r['pool']}, title={r['title'][:60]!r})")
            case_id = matches[0]
            if case_id in seen:
                raise RuntimeError(f"{judge['file']}: two legacy rows map to {case_id}")
            seen.add(case_id)
            rows.append({
                "case_id": case_id, "judge": name, "backend": "legacy",
                "model": judge["model"], "mode": judge["mode"],
                "label": r["llm_label"], "probabilities": None, "raw": None,
                # only the hosted dc_council judges record per-case usage
                # ({"input_tokens", "output_tokens"}); None for older runs and local
                # models, which 05_evaluate.row_cost then prices another way
                "prompt_sha": None, "latency_s": None, "usage": r.get("usage"),
                "timestamp": None, "source_file": f"dc_council/{judge['file']}",
            })

        with open(config.run_path(name), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"{name:30} {len(rows):>4}/{len(cases)} cases  <- dc_council/{judge['file']}")


if __name__ == "__main__":
    main()
