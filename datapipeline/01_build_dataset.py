"""
Step 1: turn the dc_council benchmark into one flat file of cases with
stable IDs (SPEC.md section 3).

Today gold labels live in dicts keyed by "position within a pool"
(benchmark_gold_labels.py) and results are matched to them by counting
rows -- reorder a list or run a partial batch and every label after that
point silently shifts. Here each case gets a case_id ("weak-024" = the
25th case of the weak pool) and carries its own gold label, so everything
downstream joins on case_id instead.

Also builds the same-category hard-negative stress set (SPEC.md 3.2),
deterministically: hard_negative_check.py draws from a Python set, whose
iteration order changes between runs, so its exact 50 cases can't be
rebuilt.

Run from datapipeline/:
  python3 01_build_dataset.py
Writes data/benchmark.jsonl and data/stress_hard_negatives.jsonl.
"""
import json
import os
import random
from collections import Counter

import config
from benchmark_gold_labels import WEAK_GOLD, NO_CONTEXT_GOLD, SUPPORTED_POOL_OVERRIDES
from hard_negative_check import category


def gold_for(pool, i):
    # same rules as dc_council/compare_abstention.gold_for
    if pool == "supported":
        return SUPPORTED_POOL_OVERRIDES.get(i, "supported")
    if pool == "synthetic_contradicted":
        return "contradicted"
    if pool == "weak":
        return WEAK_GOLD[i]
    if pool == "no_context":
        return NO_CONTEXT_GOLD[i]
    raise ValueError(pool)


def build_benchmark():
    sample = json.load(open(config.BENCHMARK_SAMPLE_PATH))
    cases = []
    for pool in config.POOLS:
        for i, r in enumerate(sample[pool]):
            gold = gold_for(pool, i)
            is_synthetic = pool == "synthetic_contradicted"
            cases.append({
                "case_id": f"{config.POOLS[pool]}-{i:03d}",
                "pool": config.POOLS[pool],
                "clip_id": r["clip_id"],
                "normalized": r["normalized"],
                "context": r["context"],
                "title": r["swapped_title"] if is_synthetic else r["official_title"],
                "gold": gold,
                "gold_3way": "unverifiable" if gold == "uncertain" else gold,
                "is_synthetic": is_synthetic,
            })
    return cases


def build_stress_set():
    rows = [json.loads(l) for l in open(config.CITATIONS_SCORED_PATH)]
    positives = [r for r in rows if r.get("exists") and r.get("topic_overlap", 0) > 0]

    titles_by_cat = {}
    for r in rows:
        if r.get("official_title"):
            titles_by_cat.setdefault(category(r["official_title"]), set()).add(r["official_title"])
    titles_by_cat = {cat: sorted(titles) for cat, titles in titles_by_cat.items()}

    rng = random.Random(config.STRESS_SEED)
    candidates = []
    for r in positives:
        peers = [t for t in titles_by_cat[category(r["official_title"])] if t != r["official_title"]]
        if len(peers) < 2:
            continue  # same skip rule as hard_negative_check.py
        candidates.append((r, rng.choice(peers)))

    picked = rng.sample(candidates, min(config.STRESS_N, len(candidates)))
    cases = []
    for i, (r, hard_title) in enumerate(picked):
        cases.append({
            "case_id": f"stress-{i:03d}",
            "pool": "stress_hard_negative",
            "clip_id": r["clip_id"],
            "normalized": r["normalized"],
            "context": r["context"],
            "title": hard_title,
            "true_title": r["official_title"],
            "category": category(r["official_title"]),
            "gold": "contradicted",
            "gold_3way": "contradicted",
            "is_synthetic": True,
        })
    return cases, len(candidates)


def write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)

    cases = build_benchmark()
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case_id"
    write_jsonl(config.BENCHMARK_PATH, cases)

    print(f"{len(cases)} benchmark cases -> {os.path.relpath(config.BENCHMARK_PATH)}")
    print(f"  by pool: {dict(Counter(c['pool'] for c in cases))}")
    print(f"  by gold: {dict(Counter(c['gold'] for c in cases))}")
    print(f"  {len({c['clip_id'] for c in cases})} distinct meetings")

    if config.STRESS_N:
        stress, n_candidates = build_stress_set()
        write_jsonl(config.STRESS_PATH, stress)
        print(f"\n{len(stress)} same-category hard negatives (of {n_candidates} possible) "
              f"-> {os.path.relpath(config.STRESS_PATH)}")
        print(f"  by category: {dict(Counter(c['category'] for c in stress))}")


if __name__ == "__main__":
    main()
