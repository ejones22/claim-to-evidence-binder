"""
Computes agreement between the second rater's independent labels and the original
gold labels for the same 30 blind-sampled cases -- real human-to-human
inter-rater reliability, not just one person's read (even if that one
person double-checked against an LLM's disagreements, which is what
the benchmark relied on before this).

Usage: generate rater1_labels.json and rater2_labels.json from the
filled-in rater2_review_form.txt, then score:
  python3 parse_rater2_review_form.py
  python3 score_rater2_review.py
"""
import json


def cohens_kappa(labels_a, labels_b, categories):
    n = len(labels_a)
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    pe = sum(
        (labels_a.count(c) / n) * (labels_b.count(c) / n) for c in categories
    )
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


def main():
    rater1 = json.load(open("rater1_labels.json"))
    try:
        rater2 = json.load(open("rater2_labels.json"))
    except FileNotFoundError:
        print("rater2_labels.json not found yet -- run parse_rater2_review_form.py first.")
        print('Format: {"<id>": "supported"|"contradicted"|"unverifiable", ...}')
        return

    ids = list(rater1.keys())
    missing = [i for i in ids if i not in rater2]
    if missing:
        print(f"Missing {len(missing)} labels from the second rater's file: {missing}")
        return

    a = [rater1[i] for i in ids]
    b = [rater2[i].lower().strip() for i in ids]

    agree = sum(1 for x, y in zip(a, b) if x == y)
    print(f"Raw agreement: {agree}/{len(ids)} = {agree/len(ids):.1%}")
    print(f"Cohen's kappa: {cohens_kappa(a, b, ['supported', 'contradicted', 'unverifiable']):.2f}")

    print("\nDisagreements:")
    for i in ids:
        if rater1[i] != rater2[i].lower().strip():
            print(f"  {i}: rater1={rater1[i]}  rater2={rater2[i]}")


if __name__ == "__main__":
    main()
