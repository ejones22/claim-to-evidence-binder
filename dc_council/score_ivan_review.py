"""
Computes agreement between Ivan's independent labels and the original
gold labels for the same 30 blind-sampled cases -- real human-to-human
inter-rater reliability, not just one person's read (even if that one
person double-checked against an LLM's disagreements, which is what
the benchmark relied on before this).

Usage: fill in ivans_labels.json as {"<id>": "supported"|"contradicted"|
"unverifiable", ...} for all 30 ids in ivan_blind_sample.json, then:
  python3 score_ivan_review.py
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
    mine = json.load(open("my_labels_for_ivan_sample.json"))
    try:
        ivans = json.load(open("ivans_labels.json"))
    except FileNotFoundError:
        print("ivans_labels.json not found yet -- fill it in once Ivan sends his answers.")
        print('Format: {"<id>": "supported"|"contradicted"|"unverifiable", ...}')
        return

    ids = list(mine.keys())
    missing = [i for i in ids if i not in ivans]
    if missing:
        print(f"Missing {len(missing)} labels from Ivan's file: {missing}")
        return

    a = [mine[i] for i in ids]
    b = [ivans[i].lower().strip() for i in ids]

    agree = sum(1 for x, y in zip(a, b) if x == y)
    print(f"Raw agreement: {agree}/{len(ids)} = {agree/len(ids):.1%}")
    print(f"Cohen's kappa: {cohens_kappa(a, b, ['supported', 'contradicted', 'unverifiable']):.2f}")

    print("\nDisagreements:")
    for i in ids:
        if mine[i] != ivans[i].lower().strip():
            print(f"  {i}: mine={mine[i]}  ivan={ivans[i]}")


if __name__ == "__main__":
    main()
