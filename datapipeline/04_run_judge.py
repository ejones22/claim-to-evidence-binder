"""
Step 4: run one judge from config.JUDGES over a split (SPEC.md section 5).

Replaces the one-script-per-model pattern in dc_council/
(llm_judge_baseline.py, run_second_model.py, ...): the judge's backend,
model and mode come from the registry, and every result row carries its
case_id so nothing depends on row order.

Resumable: cases already in the judge's results file are skipped, so an
interrupted run continues where it stopped. Errors stop the run (after
retries) instead of writing a placeholder -- rerun to resume. Rows from a
different prompt version are never mixed into the same file (prompt_sha
check; use --overwrite to start the file over).

Run from datapipeline/:
  python3 04_run_judge.py --list
  python3 04_run_judge.py --judge adaption/deepseek-v4-flash/abstain
  python3 04_run_judge.py --judge decision/d3:9b/forced --split val --limit 5
  python3 04_run_judge.py --judge decision/d3:9b/forced --split stress
Appends to results/runs/<judge>.jsonl.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone

import config
from backends import BACKENDS, ALLOWED, prompt_sha, release

VALID_LABELS = set(config.LABELS_ABSTAIN) | {"parse_error"}


def load_split_cases(split):
    if split == "stress":
        return [json.loads(l) for l in open(config.STRESS_PATH)]
    cases = [json.loads(l) for l in open(config.BENCHMARK_PATH)]
    if split == "all":
        return cases
    assignments = json.load(open(config.SPLITS_PATH))["assignments"]
    return [c for c in cases if assignments[c["case_id"]] == split]


def load_existing(path, sha, overwrite):
    if overwrite or not os.path.exists(path):
        return {}
    rows = [json.loads(l) for l in open(path)]
    other = {r["prompt_sha"] for r in rows} - {sha}
    if other:
        raise SystemExit(f"{path} has rows from another prompt version {sorted(other)} "
                         f"(current {sha}); pass --overwrite to start over")
    return {r["case_id"]: r for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", help="name from config.JUDGES")
    ap.add_argument("--split", default="all", choices=["train", "val", "test", "all", "stress"])
    ap.add_argument("--limit", type=int, help="only run the first N not-yet-done cases")
    ap.add_argument("--overwrite", action="store_true", help="discard this judge's existing results")
    ap.add_argument("--list", action="store_true", help="list runnable judges and exit")
    args = ap.parse_args()

    if args.list or not args.judge:
        for name, j in config.JUDGES.items():
            if j["backend"] != "legacy":
                print(f"  {name:40} backend={j['backend']:16} model={j['model']}")
        return

    judge = config.JUDGES[args.judge]
    if judge["backend"] == "legacy":
        raise SystemExit("legacy judges are imported by 03_import_legacy_runs.py, not run")
    call = BACKENDS[judge["backend"]]
    sha = prompt_sha(judge)

    os.makedirs(config.RUNS_DIR, exist_ok=True)
    path = config.run_path(args.judge)
    done = load_existing(path, sha, args.overwrite)
    if args.overwrite and os.path.exists(path):
        os.remove(path)

    cases = load_split_cases(args.split)
    todo = [c for c in cases if c["case_id"] not in done]
    if args.limit is not None:
        todo = todo[:args.limit]
    n_done = sum(1 for c in cases if c["case_id"] in done)
    print(f"{args.judge}: {len(cases)} cases in '{args.split}', {n_done} already done, "
          f"running {len(todo)}  (prompt_sha={sha})")

    t_start = time.time()
    # try/finally: the local model is unloaded however the run ends --
    # finished, crashed, or Ctrl-C
    try:
        with open(path, "a") as f:
            for i, c in enumerate(todo, start=1):
                t0 = time.time()
                out = call(judge, c["context"], c["title"])
                if out["label"] not in VALID_LABELS or (out["label"] != "parse_error"
                                                       and out["label"] not in ALLOWED[judge["mode"]]):
                    raise RuntimeError(f"backend returned label {out['label']!r} for {c['case_id']}")
                row = {
                    "case_id": c["case_id"], "judge": args.judge, "backend": judge["backend"],
                    "model": judge["model"], "mode": judge["mode"],
                    "label": out["label"], "probabilities": out["probabilities"], "raw": out["raw"],
                    "prompt_sha": sha, "latency_s": round(time.time() - t0, 3), "usage": out["usage"],
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                f.write(json.dumps(row) + "\n")
                f.flush()  # each row is on disk before the next call, so a crash loses nothing
                if i % 10 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}  ({(time.time() - t_start) / i:.1f}s/case)")
    finally:
        release(judge)

    print(f"done -> {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
