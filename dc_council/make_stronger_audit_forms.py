"""
Builds the two blank review forms for the stronger independent audit
(build_stronger_audit_sample.py): one for the fresh 60-case random sample,
one for the 20-case strict-relabel diagnostic. Same two-field schema on
both, so answers are comparable, but scored and reported separately --
the diagnostic is a targeted check of one person's relabeling pass, not a
random-sample agreement estimate.

Run from dc_council/:
  python3 make_stronger_audit_forms.py
Writes stronger_audit_form.txt, strict_relabel_diagnostic_form.txt.
"""
import json

INSTRUCTIONS = """INDEPENDENT LABEL REVIEW -- {title}
======================================================================

For each case: read the CONTEXT (what was actually said in the meeting)
and the OFFICIAL TITLE (the real legislative record it's being checked
against). Answer two separate questions, then give one overall label.

FIELD 1 -- TOPIC MATCH: is the transcript clearly talking about this same
  specific bill/resolution (not a different one, not something else
  entirely)?
    Write: YES / NO / CANT_TELL

FIELD 2 -- CONTENT CONFIRMED: setting the bill number aside, does the
  transcript actually describe what THIS measure does or says -- not just
  name it, read it off a list with others, or make a generic remark that
  would apply equally to a different, similar bill?
    Write: YES / NO / CANT_TELL

OVERALL LABEL -- given your two answers above:
  SUPPORTED     if FIELD 1 = YES and FIELD 2 = YES
  CONTRADICTED  if FIELD 1 = NO
  UNVERIFIABLE  if FIELD 1 = YES but FIELD 2 = NO, or if FIELD 1 = CANT_TELL
  (if your own judgment disagrees with this mapping for some case, go with
  your own judgment on OVERALL LABEL and leave FIELD 1 / FIELD 2 as you
  answered them -- the mapping is a guide, not a rule)

Don't overthink it -- go with your first honest read. Send this file back
with the blanks filled in.

----------------------------------------------------------------------
"""


def write_form(sample_path, out_path, title):
    cases = json.load(open(sample_path))
    with open(out_path, "w") as f:
        f.write(INSTRUCTIONS.format(title=title))
        for n, c in enumerate(cases, start=1):
            f.write(f"CASE {n} (id: {c['id']})\n")
            f.write(f"CONTEXT: {c['context']}\n")
            f.write(f"OFFICIAL TITLE: {c['official_title']}\n")
            f.write("FIELD 1 (TOPIC MATCH): \n")
            f.write("FIELD 2 (CONTENT CONFIRMED): \n")
            f.write("OVERALL LABEL: \n")
            f.write("\n" + "-" * 70 + "\n")
    print(f"wrote {out_path} ({len(cases)} cases)")


if __name__ == "__main__":
    write_form("stronger_audit_sample.json", "stronger_audit_form.txt",
               "FRESH RANDOM SAMPLE (60 cases)")
    write_form("strict_relabel_diagnostic_sample.json", "strict_relabel_diagnostic_form.txt",
               "STRICT-RELABEL DIAGNOSTIC (20 cases) -- checking one person's relabeling pass")
