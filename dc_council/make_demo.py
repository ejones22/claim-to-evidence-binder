"""
Builds the Day-3 demo view (demo.html): one self-contained page showing
the headline abstention result across all three models, the worked
examples, the percent of citations bound per meeting, and the open
limitations.

Every number and every quoted transcript snippet is read from the
committed result files at build time -- nothing is typed in by hand.
The abstention numbers reuse compare_abstention.py's own gold-label
attachment and scoring functions, so the page can't drift from what that
script reports. Demo examples are picked by their benchmark index (see
EXAMPLES below) and pulled verbatim from benchmark_sample.json, with the
model labels looked up from the results files.

No raw data needed (data/ isn't in the repo) -- only the committed
*.json / *.jsonl results.

Run from dc_council/:
  python3 make_demo.py
Writes demo.html next to this script.
"""
import collections
import json
import os

from compare_abstention import attach_gold, score_abstaining, score_forced

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "demo.html")

# model name -> (abstaining results, forced results)
MODELS = [
    ("qwen2.5:3b", "llm_judge_results_qwen2.5-3b.json", "llm_forced_results_qwen2.5-3b.json"),
    ("qwen2.5:7b", "llm_judge_results.json", "llm_forced_results.json"),
    ("qwen3.5:9b", "llm_judge_results_qwen3.5-9b.json", "llm_forced_results_qwen3.5-9b.json"),
]

POOL_TO_SAMPLE_KEY = {
    "supported_pool": "supported",
    "weak_pool": "weak",
    "no_context_pool": "no_context",
}

# (pool, index into that pool, kind, heading, why it's shown, expected labels)
# The "why" text describes the labels, so the expected (gold, judge, forced)
# triple is asserted at build time -- if a rerun changes them, the build
# fails instead of shipping a caption that no longer matches the data.
EXAMPLES = [
    ("supported_pool", 0, "bound", "Clean bind",
     "The speaker reads the bill number and its title. The number resolves to a "
     "real record and the words match it. Every check agrees.",
     ("supported", "supported", "supported")),
    ("supported_pool", 30, "caught", "Word overlap fooled, LLM judge caught it",
     "Shared boilerplate (“real property tax”, “commission”) pushed the "
     "word-overlap score to 0.5, so the matcher accepted it. The person named is "
     "different from the one in the record.",
     ("contradicted", "contradicted", "contradicted")),
    ("no_context_pool", 9, "abstain", "Why abstention helps",
     "A procedural vote. Nothing in the text says what the bill is about. Forced to "
     "answer, the model calls it contradicted. Allowed to abstain, it says it can't tell, "
     "which matches the gold label.",
     ("unverifiable", "unverifiable", "contradicted")),
    ("no_context_pool", 18, "flagged", "Flagged: the record says something else",
     "The number resolves to a real bill, but the speaker describes a different "
     "one. The gold label marks this as a genuine mismatch, not a parsing error. "
     "Flagged for a person to look at; it is not a claim that anyone misspoke on purpose.",
     ("contradicted", "contradicted", "contradicted")),
    ("no_context_pool", 43, "miss", "Where abstention still fails",
     "Just a vote, with no description at all. The abstaining judge should have said "
     "“can't tell” but called it contradicted. This is one of 3 errors of this kind "
     "in error_taxonomy.json.",
     ("unverifiable", "contradicted", "contradicted")),
]

ROOT_CAUSE_LABELS = {
    "plausible_old_period": "Earlier council period, not in our LIMS snapshot",
    "period_20_anomaly": "“Period 20” numbers (caption error)",
    "garbled_digits_period_correct": "Garbled digits, right period",
    "impossible_period": "Impossible number (e.g. B76-0040)",
    "truncated_midword": "Caption cut off mid-number",
}

# the three examples the Day-3 spec asks for; the rest render below the chart
LEAD_KINDS = {"bound", "caught", "abstain"}


def load(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)


def model_rows():
    rows = []
    for name, judge_file, forced_file in MODELS:
        abstaining = attach_gold(load(judge_file))
        forced = attach_gold(load(forced_file))
        a_cov, a_err, a_n, a_errs = score_abstaining(abstaining)
        f_cov, f_err, f_n, f_errs = score_forced(forced)
        # forced, restricted to the cases the abstaining run chose to answer
        # (same comparison as significance_test.py / compare_second_model.py)
        covered_idx = [i for i, r in enumerate(abstaining) if r["llm_label"] != "unverifiable"]
        same_errs = sum(1 for i in covered_idx if forced[i]["llm_label"] != forced[i]["gold"])
        rows.append({
            "model": name,
            "n_cases": len(abstaining),
            "coverage": a_cov,
            "abstain_err": a_err, "abstain_errs": a_errs, "abstain_n": a_n,
            "forced_err": f_err, "forced_errs": f_errs, "forced_n": f_n,
            "forced_same_err": same_errs / len(covered_idx), "forced_same_errs": same_errs,
        })
    return rows


def examples():
    sample = load("benchmark_sample.json")
    judge = attach_gold(load("llm_judge_results.json"))
    forced = attach_gold(load("llm_forced_results.json"))
    by_pool = collections.defaultdict(list)
    for j, f in zip(judge, forced):
        by_pool[j["pool"]].append((j, f))

    # the demo must never show labels for a case in the blind inter-rater
    # sample (ivan_blind_sample.json) -- that would unblind the second labeler
    blind_key = lambda r: (r["official_title"].strip(), r["context"].strip()[:60])
    blind = {blind_key(b) for b in load("ivan_blind_sample.json")}

    out = []
    for pool, i, kind, heading, why, expected in EXAMPLES:
        s = sample[POOL_TO_SAMPLE_KEY[pool]][i]
        j, f = by_pool[pool][i]
        # results rows carry no id, only (context, title) -- make sure the
        # positional lookup really landed on the same case
        assert j["title"] == s["official_title"], (pool, i)
        # checked before anything label-related, so a failure here can't
        # print the labels of a blind case
        assert blind_key(s) not in blind, f"{pool}#{i} is in the blind inter-rater sample"
        actual = (j["gold"], j["llm_label"], f["llm_label"])
        assert actual == expected, (pool, i, actual, expected)
        out.append({
            "kind": kind, "lead": kind in LEAD_KINDS, "heading": heading, "why": why,
            "ref": f"{pool}#{i}",
            "cited_as": s["cited_as"], "normalized": s["normalized"],
            "meeting": s["meeting_title"], "clip_id": s["clip_id"], "view_id": s["view_id"],
            "start_sec": s["start_sec"],
            "context": s["context"].strip(), "title": s["official_title"],
            "overlap": s["topic_overlap"],
            "matcher": "match" if s["topic_overlap"] >= 0.3 else "no match",
            "gold": j["gold"], "judge": j["llm_label"], "forced": f["llm_label"],
        })
    return out


def meetings():
    with open(os.path.join(HERE, "citations_scored.jsonl")) as f:
        cites = [json.loads(line) for line in f if line.strip()]
    per = collections.OrderedDict()
    for c in cites:
        m = per.setdefault(c["clip_id"], {
            "clip_id": c["clip_id"], "view_id": c["view_id"],
            "title": c["meeting_title"], "cites": [],
        })
        if not c["exists"]:
            status = "none"
        elif c.get("topic_match"):
            status = "match"
        else:
            status = "review"
        m["cites"].append({
            "cited_as": c["cited_as"], "normalized": c["normalized"],
            "start_sec": c.get("start_sec"), "status": status, "title": c.get("official_title"),
            "overlap": c.get("topic_overlap"), "context": (c.get("context") or "").strip(),
        })
    out = list(per.values())
    for m in out:
        counts = collections.Counter(c["status"] for c in m["cites"])
        m["n"] = len(m["cites"])
        m["match"], m["review"], m["none"] = counts["match"], counts["review"], counts["none"]
    totals = collections.Counter(c["status"] for m in out for c in m["cites"])
    # fetch_captions.py estimates turn times proportionally (Granicus captions
    # have no per-line timing); 0/None means no estimate for that citation
    no_time = sum(1 for c in cites if not c.get("start_sec"))
    return out, {"n": len(cites), "meetings": len(out), "no_timestamp": no_time, **totals}


def main():
    root = load("root_cause_final.json")
    resolutions = load("root_cause_resolutions.json")
    data = {
        "models": model_rows(),
        "significance": load("significance_results.json"),
        "examples": examples(),
        "matcher": load("benchmark_metrics.json"),
        "hard_neg": load("hard_negative_findings.json"),
        "taxonomy": load("error_taxonomy.json"),
        "n_blind": len(load("ivan_blind_sample.json")),
        "n_hard_neg_llm": len(load("hard_negative_llm_results.json")),
        "root_cause": {
            "n_distinct": root["n_distinct"], "n_occurrences": root["n_occurrences"],
            "by_category": [
                {"key": k, "label": ROOT_CAUSE_LABELS.get(k, k), "n": n}
                for k, n in sorted(root["by_category"].items(), key=lambda kv: -kv[1])
            ],
            "period_20_resolved": len(resolutions["period_20_anomaly_resolved"]),
            "garbled_resolved": len(resolutions["garbled_digits_resolved"]),
        },
    }
    # the "Where abstention still fails" caption says "one of 3 errors"
    assert data["taxonomy"]["categories"]["C_overconfident_on_empty_content"]["n"] == 3
    data["meetings"], data["totals"] = meetings()

    with open(os.path.join(HERE, "demo_template.html")) as f:
        template = f.read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(OUT_PATH, "w") as f:
        f.write(template.replace("__DEMO_DATA__", payload))

    t = data["totals"]
    print(f"Wrote {OUT_PATH}")
    print(f"  {t['n']} citations across {t['meetings']} meetings: "
          f"{t['match']} word-matched, {t['review']} need review, {t['none']} not in LIMS")
    for m in data["models"]:
        print(f"  {m['model']:11} n={m['n_cases']:3}  forced {m['forced_err']:.1%}  "
              f"abstaining {m['abstain_err']:.1%} at {m['coverage']:.1%} coverage  "
              f"forced-on-same-cases {m['forced_same_err']:.1%}")


if __name__ == "__main__":
    main()
