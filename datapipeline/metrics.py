"""
Pure metric functions for 05_evaluate.py (SPEC.md section 6) -- no file
I/O, so each one can be read (and checked) on its own.

Every function takes "rows": dicts with at least
  {"label": model output, "gold": gold_3way, ...}
where gold_3way already maps the one "uncertain" gold case to
"unverifiable" (same mapping as dc_council/significance_test.py).

Definitions match dc_council/ so legacy numbers reproduce:
  coverage / selective_error  -> compare_abstention.score_abstaining
  forced_error                -> compare_abstention.score_forced
  precision/recall_supported  -> compute_benchmark_metrics
"""
import math
import random


def is_covered(row):
    return row["label"] != "unverifiable"


def is_wrong(row):
    return row["label"] != row["gold"]


def coverage(rows):
    return sum(1 for r in rows if is_covered(r)) / len(rows) if rows else float("nan")


def selective_error(rows):
    """Errors among the answers the judge was willing to commit to.
    parse_error counts as covered and wrong (the legacy behaviour)."""
    covered = [r for r in rows if is_covered(r)]
    if not covered:
        return float("nan")
    return sum(1 for r in covered if is_wrong(r)) / len(covered)


def forced_error(rows):
    """Errors among all answers. For a 2-way judge, a gold-unverifiable
    case is always wrong -- it claimed a confidence the evidence didn't
    support, which is exactly what abstention exists to prevent."""
    return sum(1 for r in rows if is_wrong(r)) / len(rows) if rows else float("nan")


def accuracy_3way(rows):
    return 1 - forced_error(rows)


def precision_recall_supported(rows):
    tp = sum(1 for r in rows if r["gold"] == "supported" and r["label"] == "supported")
    fp = sum(1 for r in rows if r["gold"] != "supported" and r["label"] == "supported")
    fn = sum(1 for r in rows if r["gold"] == "supported" and r["label"] != "supported")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    return precision, recall


def bootstrap_selective_error(rows, n_resamples, seed):
    """95% CI on selective error, resampling cases (not just covered ones)
    -- same procedure as dc_council/significance_test.bootstrap_error_rate."""
    rng = random.Random(seed)
    n = len(rows)
    rates = []
    for _ in range(n_resamples):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        covered = [r for r in sample if is_covered(r)]
        if covered:
            rates.append(sum(1 for r in covered if is_wrong(r)) / len(covered))
    if not rates:
        return [float("nan"), float("nan")]
    rates.sort()
    return [rates[int(0.025 * len(rates))], rates[int(0.975 * len(rates))]]


def mcnemar_exact(rows_a, rows_b):
    """Exact McNemar's test on cases BOTH judges cover, paired by case_id.
    Same as scipy.stats.binomtest(min(n10, n01), n10 + n01, 0.5) two-sided,
    written out with math.comb so there's no scipy dependency."""
    b_by_id = {r["case_id"]: r for r in rows_b}
    n10 = n01 = 0  # a right & b wrong / a wrong & b right
    for a in rows_a:
        b = b_by_id.get(a["case_id"])
        if b is None or not is_covered(a) or not is_covered(b):
            continue
        a_right, b_right = not is_wrong(a), not is_wrong(b)
        if a_right and not b_right:
            n10 += 1
        elif b_right and not a_right:
            n01 += 1
    n = n10 + n01
    if n == 0:
        return {"n10": 0, "n01": 0, "p_value": None}
    k = min(n10, n01)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"n10": n10, "n01": n01, "p_value": min(1.0, 2 * tail)}


# --- thresholded abstention, for judges that return probabilities ---

def max_prob(row):
    return max(row["probabilities"].values())


def apply_threshold(rows, tau):
    """Turn a forced judge into an abstaining one: keep the answer only
    when the model's top probability is at least tau."""
    return [{**r, "label": r["label"] if max_prob(r) >= tau else "unverifiable"} for r in rows]


def risk_coverage_curve(rows):
    """Answer the most confident case first, then the next, ...; after k
    answers, coverage = k/n and risk = errors so far / k."""
    ordered = sorted(rows, key=max_prob, reverse=True)
    curve, errors = [], 0
    for k, r in enumerate(ordered, start=1):
        errors += is_wrong(r)
        curve.append((k / len(ordered), errors / k))
    return curve


def aurc(rows):
    """Area under the risk-coverage curve (mean risk over all coverage
    levels). Lower is better; 0 means every committed answer is right."""
    curve = risk_coverage_curve(rows)
    return sum(risk for _, risk in curve) / len(curve) if curve else float("nan")


def tau_for_coverage(rows, target_coverage):
    """Smallest-error threshold that still answers at least target_coverage
    of the cases: the max-prob of the ceil(target * n)-th most confident case."""
    probs = sorted((max_prob(r) for r in rows), reverse=True)
    k = max(1, math.ceil(target_coverage * len(probs)))
    return probs[min(k, len(probs)) - 1]
