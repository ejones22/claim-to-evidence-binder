"""
Step 5: score every judge's run on every split and write the leaderboard
(SPEC.md section 6).

Same metric definitions as dc_council/ (see metrics.py), but computed per
split, joined by case_id, with cases a run didn't cover reported as
"missing" rather than silently dropped. The number to quote is "test";
"all" exists only to compare against the legacy all-200 numbers.

For forced-mode judges that return probabilities (decision models), it
also evaluates thresholded abstention: tau is picked on val to match the
reference judge's val coverage, then error is measured on test at that
tau -- a matched-coverage comparison, since any judge can lower its error
by refusing more.

Before scoring, it re-derives the legacy headline (qwen2.5:7b, all 200)
and checks it against dc_council/abstention_comparison.json.

Run from datapipeline/:
  python3 05_evaluate.py
Writes results/metrics.json and results/leaderboard.md.
"""
import json
import math
import os

import config
import metrics

SPLITS = ["train", "val", "test", "all"]
CI_SPLITS = {"test", "all", "stress"}  # bootstrap is slow-ish; only where we report


def load_jsonl(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def split_ids(cases, stress):
    assignments = json.load(open(config.SPLITS_PATH))["assignments"]
    ids = {s: {c["case_id"] for c in cases if assignments[c["case_id"]] == s} for s in config.SPLIT_RATIOS}
    ids["all"] = {c["case_id"] for c in cases}
    ids["stress"] = {c["case_id"] for c in stress}
    return ids


def rows_for(run, gold, ids):
    return [{**r, "gold": gold[r["case_id"]]} for r in run if r["case_id"] in ids]


def score(rows, n_expected, split, reference_rows):
    if not rows:
        return {"n": 0, "missing": n_expected}
    precision, recall = metrics.precision_recall_supported(rows)
    out = {
        "n": len(rows),
        "missing": n_expected - len(rows),
        "coverage": metrics.coverage(rows),
        "selective_error": metrics.selective_error(rows),
        "forced_error": metrics.forced_error(rows),
        "accuracy_3way": metrics.accuracy_3way(rows),
        "precision_supported": precision,
        "recall_supported": recall,
        "parse_errors": sum(1 for r in rows if r["label"] == "parse_error"),
    }
    if split in CI_SPLITS:
        out["selective_error_ci95"] = metrics.bootstrap_selective_error(
            rows, config.BOOTSTRAP_RESAMPLES, config.BOOTSTRAP_SEED)
    if reference_rows is not None:
        out["mcnemar_vs_reference"] = metrics.mcnemar_exact(rows, reference_rows)
    return out


def check_legacy_reproduction(runs, gold, ids):
    path = os.path.join(config.DC_COUNCIL_DIR, "abstention_comparison.json")
    if "legacy/qwen2.5:7b/abstain" not in runs or not os.path.exists(path):
        return
    legacy = json.load(open(path))
    a = rows_for(runs["legacy/qwen2.5:7b/abstain"], gold, ids["all"])
    f = rows_for(runs["legacy/qwen2.5:7b/forced"], gold, ids["all"])
    checks = [
        ("abstain coverage", metrics.coverage(a), legacy["abstaining"]["coverage"]),
        ("abstain error", metrics.selective_error(a), legacy["abstaining"]["error_rate"]),
        ("forced error", metrics.forced_error(f), legacy["forced"]["error_rate"]),
    ]
    print("Reproducing dc_council/abstention_comparison.json (qwen2.5:7b, all 200):")
    for label, ours, theirs in checks:
        status = "OK" if math.isclose(ours, theirs, abs_tol=1e-9) else "MISMATCH"
        print(f"  {label:18} pipeline={ours:.4f}  legacy={theirs:.4f}  {status}")
    print()


def thresholded(run, gold, ids, reference_val_coverage):
    """Forced judge + confidence threshold, tau tuned on val only."""
    val = rows_for(run, gold, ids["val"])
    test = rows_for(run, gold, ids["test"])
    if not val or not test or reference_val_coverage is None:
        return None
    tau = metrics.tau_for_coverage(val, reference_val_coverage)
    test_at_tau = metrics.apply_threshold(test, tau)
    return {
        "target_val_coverage": reference_val_coverage,
        "tau": tau,
        "val_coverage_at_tau": metrics.coverage(metrics.apply_threshold(val, tau)),
        "test_coverage_at_tau": metrics.coverage(test_at_tau),
        "test_selective_error_at_tau": metrics.selective_error(test_at_tau),
        "test_selective_error_at_tau_ci95": metrics.bootstrap_selective_error(
            test_at_tau, config.BOOTSTRAP_RESAMPLES, config.BOOTSTRAP_SEED),
        "aurc_val": metrics.aurc(val),
        "aurc_test": metrics.aurc(test),
    }


# --- leaderboard formatting ---

def pct(x):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1%}"


def ci(m):
    lo_hi = m.get("selective_error_ci95")
    return "" if not lo_hi or any(math.isnan(v) for v in lo_hi) else f" [{lo_hi[0]:.0%}, {lo_hi[1]:.0%}]"


def split_table(results, split):
    entries = [(name, r["splits"][split]) for name, r in results.items() if r["splits"][split]["n"]]
    entries.sort(key=lambda e: (math.isnan(e[1]["selective_error"]), e[1]["selective_error"]))
    lines = [
        "| judge | n (missing) | coverage | selective error [95% CI] | forced error | "
        "P(sup) | R(sup) | parse err | McNemar p vs ref (ref-wins/judge-wins) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, m in entries:
        mc = m.get("mcnemar_vs_reference")
        # metrics.mcnemar_exact(judge, ref) counts n10 = judge right & ref wrong;
        # show it as ref-wins/judge-wins so the column reads left to right
        if not mc or mc["p_value"] is None:
            p = "–"
        else:
            p_txt = "<0.001" if mc["p_value"] < 0.001 else f"{mc['p_value']:.3f}"
            p = f"{p_txt} ({mc['n01']}/{mc['n10']})"
        lines.append(
            f"| {name} | {m['n']} ({m['missing']}) | {pct(m['coverage'])} | "
            f"{pct(m['selective_error'])}{ci(m)} | {pct(m['forced_error'])} | "
            f"{pct(m['precision_supported'])} | {pct(m['recall_supported'])} | "
            f"{m['parse_errors']} | {p} |")
    return "\n".join(lines)


def write_leaderboard(results, split_sizes):
    parts = [
        "# Judge leaderboard",
        "",
        "Generated by `05_evaluate.py` -- do not edit by hand. Definitions: SPEC.md section 6.",
        f"Reference judge: `{config.REFERENCE_JUDGE}`. Split sizes: "
        + ", ".join(f"{s}={n}" for s, n in split_sizes.items()) + ".",
        "",
        "- **coverage**: share of cases the judge committed to (didn't answer unverifiable)",
        "- **selective error**: wrong ÷ committed. The headline metric -- always read it next to coverage.",
        "- **forced error**: wrong ÷ all, counting gold-unverifiable as wrong for any committed answer",
        "- **missing**: split cases this run has no result for (partial runs are not imputed)",
        "",
        "## Test (held out -- the number to report)",
        "",
        split_table(results, "test"),
        "",
        "## Validation (used for tuning thresholds / choosing models)",
        "",
        split_table(results, "val"),
        "",
        "## All 200 (legacy comparability only -- includes train/val, not a held-out estimate)",
        "",
        split_table(results, "all"),
    ]
    if any(r["splits"]["stress"]["n"] for r in results.values()):
        parts += [
            "",
            "## Stress: same-category hard negatives (gold = contradicted by construction)",
            "",
            "Selective error here is the false-accept rate among committed answers.",
            "",
            split_table(results, "stress"),
        ]
    th = [(name, r["thresholded"]) for name, r in results.items() if r.get("thresholded")]
    if th:
        parts += [
            "",
            "## Thresholded abstention (forced judge + confidence threshold, tau tuned on val)",
            "",
            "tau is chosen on val to match the reference judge's val coverage; test numbers use that tau.",
            "",
            "| judge | tau | val coverage | test coverage | test selective error [95% CI] | AURC val | AURC test |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, t in sorted(th, key=lambda e: e[1]["test_selective_error_at_tau"]):
            lo, hi = t["test_selective_error_at_tau_ci95"]
            parts.append(
                f"| {name} | {t['tau']:.3f} | {pct(t['val_coverage_at_tau'])} | "
                f"{pct(t['test_coverage_at_tau'])} | {pct(t['test_selective_error_at_tau'])} "
                f"[{lo:.0%}, {hi:.0%}] | {t['aurc_val']:.3f} | {t['aurc_test']:.3f} |")
    with open(config.LEADERBOARD_PATH, "w") as f:
        f.write("\n".join(parts) + "\n")


def main():
    cases = load_jsonl(config.BENCHMARK_PATH)
    stress = load_jsonl(config.STRESS_PATH)
    gold = {c["case_id"]: c["gold_3way"] for c in cases + stress}
    ids = split_ids(cases, stress)

    runs = {name: load_jsonl(config.run_path(name)) for name in config.JUDGES}
    runs = {name: rows for name, rows in runs.items() if rows}
    known = {os.path.basename(config.run_path(n)) for n in config.JUDGES}
    for fn in sorted(os.listdir(config.RUNS_DIR)):
        if fn not in known:
            print(f"warning: {fn} isn't in config.JUDGES, skipped")

    check_legacy_reproduction(runs, gold, ids)

    reference = runs.get(config.REFERENCE_JUDGE)
    ref_val = rows_for(reference, gold, ids["val"]) if reference else []
    reference_val_coverage = metrics.coverage(ref_val) if ref_val else None

    results = {}
    for name, run in runs.items():
        judge = config.JUDGES[name]
        entry = {"backend": judge["backend"], "model": judge["model"], "mode": judge["mode"], "splits": {}}
        for split in SPLITS + ["stress"]:
            rows = rows_for(run, gold, ids[split])
            ref_rows = None
            if reference and name != config.REFERENCE_JUDGE:
                ref_rows = rows_for(reference, gold, ids[split])
            entry["splits"][split] = score(rows, len(ids[split]), split, ref_rows)
        has_probs = run and all(r.get("probabilities") for r in run)
        if judge["mode"] == "forced" and has_probs:
            entry["thresholded"] = thresholded(run, gold, ids, reference_val_coverage)
        results[name] = entry

    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    with open(config.METRICS_PATH, "w") as f:
        json.dump({"reference_judge": config.REFERENCE_JUDGE, "judges": results}, f, indent=2)
    split_sizes = {s: len(ids[s]) for s in SPLITS + ["stress"]}
    write_leaderboard(results, split_sizes)

    print(f"{'judge':36} {'split':6} {'n':>4} {'miss':>4} {'coverage':>9} {'sel.err':>8} {'forced':>8}")
    for name, entry in results.items():
        for split in ["val", "test", "all"]:
            m = entry["splits"][split]
            if m["n"]:
                print(f"{name:36} {split:6} {m['n']:>4} {m['missing']:>4} {pct(m['coverage']):>9} "
                      f"{pct(m['selective_error']):>8} {pct(m['forced_error']):>8}")
    print(f"\nwrote {os.path.relpath(config.METRICS_PATH)} and {os.path.relpath(config.LEADERBOARD_PATH)}")


if __name__ == "__main__":
    main()
