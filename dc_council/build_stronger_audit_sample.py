"""
A stronger independent audit, addressing the gaps a critique of the first
one named: (1) the original rater2 review excluded originally-contradicted
cases entirely and only sampled 30 cases total, and (2) the "strict"
relabeling (sensitivity_strict_supported.py) was done by one person, not
independently checked.

Produces two separate blind samples, as the critique asked -- a targeted
diagnostic should not be averaged into a random-sample agreement number:

  1. stronger_audit_sample.json (~60 cases): a FRESH random sample from
     natural (non-synthetic) cases NOT already touched by any review --
     not rater2's original 30, not the 20 cases sensitivity_strict_
     supported.py already relabeled. Stratified across the three natural
     gold labels, with ALL remaining natural "contradicted" cases included
     (there are only ~10 project-wide, too few to subsample).
  2. strict_relabel_diagnostic_sample.json (20 cases): every case
     sensitivity_strict_supported.py's STRICT_OVERRIDES touched, shown
     blind the same way, so an independent reviewer can check whether that
     one-person relabeling pass was itself right -- reported separately,
     never pooled with (1)'s agreement rate.

Both files redact original labels, pool identity, and case order (shuffled,
non-unique "redacted_N" ids) the same way rater2_blind_sample.json did.

Run from dc_council/:
  python3 build_stronger_audit_sample.py
"""
import json
import random

from benchmark_gold_labels import WEAK_GOLD, NO_CONTEXT_GOLD, SUPPORTED_POOL_OVERRIDES
from sensitivity_strict_supported import STRICT_OVERRIDES

RANDOM_SEED = 2026
TARGET_N = 60
ALREADY_REVIEWED = {  # rater2's original 30 (id format: "{pool}_{index}")
    'supported_1', 'no_context_1', 'weak_37', 'supported_8', 'weak_16', 'weak_1',
    'weak_38', 'no_context_44', 'no_context_26', 'supported_43', 'weak_5',
    'no_context_12', 'no_context_14', 'weak_13', 'supported_7', 'supported_47',
    'no_context_38', 'supported_14', 'supported_17', 'no_context_34', 'weak_34',
    'weak_27', 'no_context_35', 'supported_15', 'no_context_45', 'supported_40',
    'no_context_41', 'supported_6', 'weak_14', 'weak_2',
}
POOL_KEY = {"supported_pool": "supported", "weak_pool": "weak", "no_context_pool": "no_context"}
STRICT_RELABELED = {f"{POOL_KEY[p]}_{i}" for (p, i) in STRICT_OVERRIDES}


def gold_for(pool, i):
    if pool == "supported":
        return SUPPORTED_POOL_OVERRIDES.get(i, "supported")
    if pool == "weak":
        return WEAK_GOLD[i]
    if pool == "no_context":
        return NO_CONTEXT_GOLD[i]
    raise ValueError(pool)


def all_natural_cases():
    sample = json.load(open("benchmark_sample.json"))
    out = []
    for pool in ("supported", "weak", "no_context"):
        for i, r in enumerate(sample[pool]):
            gold = gold_for(pool, i)
            gold_3way = "unverifiable" if gold == "uncertain" else gold
            out.append({"id": f"{pool}_{i}", "pool": pool, "index": i,
                        "context": r["context"], "official_title": r["official_title"],
                        "gold": gold, "gold_3way": gold_3way})
    return out


def blind(cases, rng):
    """Same redaction scheme as rater2_blind_sample.json: shuffle order,
    replace each real id with a non-unique 'redacted_N' so repeats can't
    be told apart by id, and drop the gold label and pool entirely."""
    shuffled = cases[:]
    rng.shuffle(shuffled)
    out = []
    for c in shuffled:
        out.append({"id": f"redacted_{rng.randint(1, len(shuffled))}",
                    "context": c["context"], "official_title": c["official_title"]})
    return out, shuffled  # shuffled (with real ids) kept for the answer key


def main():
    rng = random.Random(RANDOM_SEED)
    cases = all_natural_cases()
    by_id = {c["id"]: c for c in cases}

    excluded = ALREADY_REVIEWED | STRICT_RELABELED
    pool = [c for c in cases if c["id"] not in excluded]
    print(f"{len(cases)} natural cases total, {len(excluded)} already touched by "
          f"some review, {len(pool)} available for a fresh sample.")

    by_label = {"contradicted": [], "supported": [], "unverifiable": []}
    for c in pool:
        by_label[c["gold_3way"]].append(c)
    for k, v in by_label.items():
        print(f"  available {k}: {len(v)}")

    # all remaining natural contradicted cases (too few to subsample),
    # then split the rest between supported/unverifiable roughly by their
    # relative prevalence in the full natural pool
    chosen = list(by_label["contradicted"])
    remaining_slots = TARGET_N - len(chosen)
    s_pool, u_pool = by_label["supported"], by_label["unverifiable"]
    s_share = len(s_pool) / (len(s_pool) + len(u_pool))
    n_s = min(len(s_pool), round(remaining_slots * s_share))
    n_u = min(len(u_pool), remaining_slots - n_s)
    chosen += rng.sample(s_pool, n_s)
    chosen += rng.sample(u_pool, n_u)
    print(f"\nChosen for the fresh sample: {len(chosen)} "
          f"(contradicted={len(by_label['contradicted'])}, supported={n_s}, unverifiable={n_u})")

    fresh_blind, fresh_key = blind(chosen, rng)
    diag_cases = [by_id[cid] for cid in STRICT_RELABELED]
    diag_blind, diag_key = blind(diag_cases, rng)

    with open("stronger_audit_sample.json", "w") as f:
        json.dump(fresh_blind, f, indent=2)
    with open("strict_relabel_diagnostic_sample.json", "w") as f:
        json.dump(diag_blind, f, indent=2)
    # answer keys: kept out of anything a reviewer would see, same as
    # my_labels_for_ivan_sample.json was for the original review
    # answer keys are in the SAME ORDER as the blind sample (redacted ids
    # aren't unique, so scoring matches by position, the same convention
    # parse_rater2_review_form.py used) -- context is included so the
    # scorer can confirm the order really lines up before trusting it
    with open("stronger_audit_answer_key.json", "w") as f:
        json.dump([{"id": c["id"], "context": c["context"], "gold_3way": c["gold_3way"]}
                   for c in fresh_key], f, indent=2)
    with open("strict_relabel_diagnostic_answer_key.json", "w") as f:
        json.dump([{"id": c["id"], "context": c["context"], "gold_3way": c["gold_3way"],
                    "strict_relabel": STRICT_OVERRIDES[(f"{c['pool']}_pool", c["index"])]}
                   for c in diag_key], f, indent=2)

    print(f"\nwrote stronger_audit_sample.json ({len(fresh_blind)} cases, blind)")
    print(f"wrote strict_relabel_diagnostic_sample.json ({len(diag_blind)} cases, blind)")
    print("wrote the two answer keys (NOT for the reviewer -- for scoring only)")


if __name__ == "__main__":
    main()
