"""
Step 2: split the benchmark into train / val / test (SPEC.md 3.3).

Until now every number was computed on all 200 cases -- the same cases
the prompts, the 0.3 overlap threshold and the gold adjudication were
developed on. The moment we tune anything (an abstention threshold, a
model choice, a few-shot example) we need cases we didn't tune on.

Two constraints:
  - GROUPED by meeting (clip_id): cases from one meeting share speakers,
    agenda and sometimes the exact same context window (4 synthetic cases
    reuse a real case's context), so a meeting never spans two splits.
  - STRATIFIED by gold_3way, approximately: meetings are visited largest
    first (seeded shuffle breaks ties) and each goes to whichever split
    still needs the most of the labels that meeting contains.

train is small on purpose -- nothing is trained, it's only a pool of
few-shot examples. val is for choosing thresholds/models. test is the
number we report.

Run from datapipeline/:
  python3 02_make_splits.py
Writes data/splits.json.
"""
import json
import os
import random
from collections import Counter, defaultdict

import config

SPLITS = list(config.SPLIT_RATIOS)


def load_cases():
    return [json.loads(l) for l in open(config.BENCHMARK_PATH)]


def assign_groups(cases):
    groups = defaultdict(list)
    for c in cases:
        groups[c["clip_id"]].append(c)

    label_totals = Counter(c["gold_3way"] for c in cases)
    target = {s: {lab: config.SPLIT_RATIOS[s] * n for lab, n in label_totals.items()} for s in SPLITS}
    current = {s: Counter() for s in SPLITS}

    order = sorted(groups)
    random.Random(config.SPLIT_SEED).shuffle(order)
    order.sort(key=lambda g: len(groups[g]), reverse=True)  # stable: keeps shuffle among ties

    assignment = {}
    for g in order:
        labels = Counter(c["gold_3way"] for c in groups[g])

        def need(s):
            # how much this split still wants these labels, relative to its target
            return sum(n * (target[s][lab] - current[s][lab]) / target[s][lab]
                       for lab, n in labels.items())

        best = max(SPLITS, key=need)
        current[best].update(labels)
        for c in groups[g]:
            assignment[c["case_id"]] = best
    return assignment


def main():
    cases = load_cases()
    assignment = assign_groups(cases)

    # checks from SPEC.md section 9
    assert set(assignment) == {c["case_id"] for c in cases}
    split_of_clip = defaultdict(set)
    for c in cases:
        split_of_clip[c["clip_id"]].add(assignment[c["case_id"]])
    assert all(len(s) == 1 for s in split_of_clip.values()), "a meeting spans two splits"

    summary = {}
    print(f"{'split':6} {'cases':>6} {'share':>6} {'meetings':>9}   gold_3way counts")
    for s in SPLITS:
        in_split = [c for c in cases if assignment[c["case_id"]] == s]
        labels = Counter(c["gold_3way"] for c in in_split)
        meetings = len({c["clip_id"] for c in in_split})
        summary[s] = {"n": len(in_split), "meetings": meetings, "gold_3way": dict(labels),
                      "pools": dict(Counter(c["pool"] for c in in_split))}
        print(f"{s:6} {len(in_split):>6} {len(in_split)/len(cases):>6.0%} {meetings:>9}   "
              + "  ".join(f"{lab}={labels[lab]}" for lab in config.LABELS_ABSTAIN))

    out = {"seed": config.SPLIT_SEED, "ratios": config.SPLIT_RATIOS, "group_key": "clip_id",
           "assignments": dict(sorted(assignment.items())), "summary": summary}
    with open(config.SPLITS_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {os.path.relpath(config.SPLITS_PATH)}")


if __name__ == "__main__":
    main()
