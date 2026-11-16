"""
Scores a filled-in stronger_audit_form.txt / strict_relabel_diagnostic_form.txt
against its answer key, for one or two independent reviewers. Reports the
two samples SEPARATELY (never pooled) per the critique that prompted this:
the fresh 60-case sample gives a real agreement/kappa estimate; the 20-case
diagnostic only checks whether sensitivity_strict_supported.py's one-person
relabeling pass holds up, and also reports the FIELD 1 / FIELD 2 breakdown
("which kinds of apparent citation success conceal insufficient support?").

Usage, after a filled-in form comes back as <name>_filled.txt:
  python3 score_stronger_audit.py stronger_audit_form_filled.txt stronger_audit_answer_key.json
  python3 score_stronger_audit.py strict_relabel_diagnostic_form_filled.txt strict_relabel_diagnostic_answer_key.json
With two reviewers' filled forms for the same sample, pass both paths and
the key as a third argument to also get inter-rater agreement between them.
"""
import json
import re
import sys

CASE_RE = re.compile(
    r"CASE \d+ \(id: (?P<id>\S+)\)\n"
    r"CONTEXT: (?P<context>.*?)\n"
    r"OFFICIAL TITLE: (?P<title>.*?)\n"
    r"FIELD 1 \(TOPIC MATCH\): *(?P<f1>\S*)\n"
    r"FIELD 2 \(CONTENT CONFIRMED\): *(?P<f2>\S*)\n"
    r"OVERALL LABEL: *(?P<overall>\S*)",
    re.DOTALL,
)


def parse_form(path):
    text = open(path).read()
    out = []
    for m in CASE_RE.finditer(text):
        out.append({"id": m["id"], "context": m["context"], "f1": m["f1"].upper(),
                    "f2": m["f2"].upper(), "overall": m["overall"].upper()})
    return out


def cohens_kappa(a, b, categories):
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in categories)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: score_stronger_audit.py <filled_form.txt> <answer_key.json> [second_filled_form.txt]")
    form_path, key_path = sys.argv[1], sys.argv[2]
    second_path = sys.argv[3] if len(sys.argv) > 3 else None

    # the form's ids are redacted and repeat (not unique), so -- like
    # parse_rater2_review_form.py -- cases are matched to the answer key
    # by ORDER, with each one's context checked to confirm the order
    # really lines up before trusting the pairing
    answers = parse_form(form_path)
    key = json.load(open(key_path))
    if len(answers) != len(key):
        raise SystemExit(f"form has {len(answers)} cases, answer key has {len(key)} -- can't match by order")
    for n, (a, g) in enumerate(zip(answers, key), start=1):
        a_snip, g_snip = a["context"][:40].strip(), g["context"][:40].strip()
        if a_snip != g_snip:
            raise SystemExit(f"CASE {n}: context mismatch between form and answer key "
                              f"({a_snip!r} vs {g_snip!r}) -- order doesn't line up, stopping")
    paired = list(zip(answers, key))
    gold = [g["gold_3way"] for _, g in paired]
    overall = [a["overall"].lower() for a, _ in paired]

    agree = sum(1 for o, g in zip(overall, gold) if o == g)
    print(f"n = {len(paired)}")
    print(f"Raw agreement with gold: {agree}/{len(paired)} = {agree/len(paired):.1%}")
    print(f"Cohen's kappa: {cohens_kappa(overall, gold, ['supported', 'contradicted', 'unverifiable']):.2f}")

    print("\nField 1 (topic match) / Field 2 (content confirmed) breakdown:")
    combo = {}
    for a, g in paired:
        key_combo = (a["f1"], a["f2"])
        combo.setdefault(key_combo, []).append(g["gold_3way"])
    for (f1, f2), golds in sorted(combo.items()):
        from collections import Counter
        print(f"  F1={f1:<10} F2={f2:<10} n={len(golds):<3} gold breakdown={dict(Counter(golds))}")

    topic_yes_content_no = [a for a, _ in paired if a["f1"] == "YES" and a["f2"] in ("NO", "CANT_TELL")]
    print(f"\n'Topic matches but content not confirmed' (the exact pattern behind the "
          f"supported-label bias): {len(topic_yes_content_no)}/{len(paired)} = "
          f"{len(topic_yes_content_no)/len(paired):.1%} of this sample")

    print("\nDisagreements with gold (real case id from the answer key, not the form's redacted id):")
    for a, g in paired:
        if a["overall"].lower() != g["gold_3way"]:
            print(f"  {g['id']}: reviewer={a['overall']} (F1={a['f1']} F2={a['f2']})  gold={g['gold_3way']}")

    if second_path:
        second = parse_form(second_path)
        if len(second) != len(key):
            raise SystemExit(f"second form has {len(second)} cases, answer key has {len(key)} -- can't match by order")
        for n, (b, g) in enumerate(zip(second, key), start=1):
            if b["context"][:40].strip() != g["context"][:40].strip():
                raise SystemExit(f"second form, CASE {n}: context mismatch -- order doesn't line up, stopping")
        a1 = [x["overall"].lower() for x, _ in paired]
        a2 = [b["overall"].lower() for b in second]
        agree2 = sum(1 for x, y in zip(a1, a2) if x == y)
        print(f"\nInter-rater agreement between the two reviewers: "
              f"{agree2}/{len(a1)} = {agree2/len(a1):.1%}  "
              f"kappa={cohens_kappa(a1, a2, ['supported', 'contradicted', 'unverifiable']):.2f}")


if __name__ == "__main__":
    main()
