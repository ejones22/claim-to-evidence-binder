"""
The actual claim-to-evidence binder: scans each transcript sentence for a
spoken financial claim ("record revenue of $6.3 billion"), matches it to
the right SEC-filed figure for that exact quarter (ground_truth/*.json),
and scores whether the claim is bound (within rounding of the filing),
off, or a flat mismatch. This is the Track 2 deliverable -- "what fraction
of a real domain's content can be automatically bound to checkable
evidence today" -- made concrete for earnings calls.

Only scores concepts with a scale word (million/billion/thousand) nearby,
except EPS, which is spoken as a bare decimal -- this is a precision-over-
recall choice: miss some claims rather than silently match the wrong
number, same principle as the DC Council pipeline's "no unverified AI
summary" rule.

Run from dc-council/earnings_etl/:
  python3 score_claims.py
Writes one scored/{event_id}.json per transcript that had ground truth,
plus a printed summary across all of them.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
GT_DIR = os.path.join(HERE, "ground_truth")
OUT_DIR = os.path.join(HERE, "scored")

SCALE = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6, "m": 1e6,
         "thousand": 1e3, "k": 1e3}

CONCEPT_KEYWORDS = {
    "revenue": re.compile(r"\brevenues?\b", re.IGNORECASE),
    "net_income": re.compile(r"\bnet (income|loss|profit)\b", re.IGNORECASE),
    "eps_diluted": re.compile(r"\b(diluted (earnings|eps)|earnings per share|\beps\b)", re.IGNORECASE),
    # "non-operating income" is a different GAAP line (other income/expense,
    # below the operating line) -- without the lookbehind this substring-
    # matches as if it were operating income itself.
    "operating_income": re.compile(r"(?<!non-)(?<!non )\boperating (income|profit|loss)\b", re.IGNORECASE),
    "total_assets": re.compile(r"\btotal assets\b", re.IGNORECASE),
}

# "net loss of $13.9 million" is spoken as a positive number but means a
# negative figure -- without this, that phrasing reads as a flat mismatch
# against a filed value of -13.9 million, when the two actually agree.
LOSS_RE = re.compile(r"\bloss\b", re.IGNORECASE)
GAIN_RE = re.compile(r"\b(income|profit)\b", re.IGNORECASE)

# Ground truth is always the single filed GAAP figure for the exact quarter.
# A sentence about guidance, a non-GAAP/adjusted measure, or a different
# period (nine months, full year) isn't wrong when it doesn't match that
# figure -- it's not a claim about that figure at all, so it's excluded
# before scoring rather than counted as a mismatch.
OUT_OF_SCOPE_RE = re.compile(
    r"\b(guidance|outlook|forecast|we expect|we now expect|continue to expect|"
    r"raising our|revising|range of \$|"
    r"adjusted|non-gaap|pro forma|excluding|one-time|one.off|"
    r"nine.months?|year-to-date|full.year|full-year|fiscal year|"
    r"the year ended|twelve months|annualized)\b",
    re.IGNORECASE,
)

# EPS is dollars-per-share -- a window match north of this is never really
# a per-share figure, just the nearest unrelated dollar amount (often the
# net-income total itself) caught by a bare "EPS"/"earnings per share"
# mention with no actual per-share number nearby.
EPS_PLAUSIBLE_MAX = 50

# "Core hardware revenue", "Carrier services revenue", "Same-center revenue"
# are a SEGMENT's figure, not the consolidated total our ground truth holds
# -- rather than list every segment name a company might invent (which
# never generalizes past this sample), require the word immediately before
# the concept phrase to be one of the small, generic set of words that
# actually mean "the whole company", and treat anything else as a scoped
# claim we can't verify against a single consolidated number.
GENERIC_PRECEDING = {
    "total", "net", "consolidated", "overall", "record", "our", "quarterly",
    "company", "companys", "company's", "group", "groups",
    "gaap", "quarter", "quarters", "quarter's", "year", "years", "period",
    "the", "a", "an", "q1", "q2", "q3", "q4",
    # a reporting VERB directly before the concept noun ("posted revenue of
    # $X") makes revenue its object, not a segment-scoping adjective --
    # these are ordinary English reporting verbs, not specific to any one
    # company's segment names, so they don't trade away generality.
    "reported", "posted", "generated", "delivered", "drove", "grew",
    "increased", "decreased", "declined", "recorded", "booked",
    "recognized", "totaled", "closed", "finished", "ended", "saw",
    "achieved", "produced", "brought", "contributed",
    # likewise a preposition/conjunction right before the noun ("resulted
    # IN net income of $X", "$2 million OF operating income") -- the real
    # qualifier, if any, sits further back and was already caught by one
    # of the checks above or is too far away to resolve cheaply.
    "in", "at", "of", "to", "for", "with", "as", "and", "from",
    "was", "is", "are", "were",
}
# "third-quarter revenue" / "this quarter's revenue" name the CURRENT
# period, same as "quarter" alone -- but "prior-year" or "year-ago" must
# NOT be swept in here, since that number belongs to a different period
# entirely and comparing it to this quarter's filing would be wrong.
CURRENT_PERIOD_RE = re.compile(r"^(this|current|third|first|second|fourth|q[1-4])[-]?quarter'?s?$", re.IGNORECASE)

PRECEDING_WORD_RE = re.compile(r"([A-Za-z][A-Za-z'\-]*)\s*$")


def has_segment_qualifier(sentence, phrase_start):
    m = PRECEDING_WORD_RE.search(sentence[:phrase_start])
    if not m:
        return False  # start of sentence/clause -- nothing scoping it
    word = m.group(1).lower()
    if word in GENERIC_PRECEDING or CURRENT_PERIOD_RE.match(word):
        return False
    return True

# "increased BY $40 million" and "a $6 million increase" are the SIZE OF A
# CHANGE, not the quarter's actual total -- only "increased TO $X" or a bare
# "$X" gives the level we have ground truth for. Checked around each
# candidate number individually (not the whole sentence), since one sentence
# routinely carries both a real total and a change description.
DELTA_WORD = r"(increase(d)?|decrease(d)?|decline(d)?|growth|improvement|improved|change(d)?|grew|fell|rose|drop(ped)?|widened|narrowed)"
DELTA_BEFORE_RE = re.compile(DELTA_WORD + r"\s+(by|of)\s*$", re.IGNORECASE)
DELTA_AFTER_RE = re.compile(r"^\s*(million|billion|thousand|mm)?\s*" + DELTA_WORD + r"\b", re.IGNORECASE)

DOLLAR_RE = re.compile(
    r"\(?\s*\$\s*(-?[\d][\d,]*(?:\.\d+)?)\s*\)?\s*"
    r"(billion|bn|million|mm|thousand|k)?\b",
    re.IGNORECASE,
)

WINDOW = 90  # chars on either side of the concept keyword to search for a number

# "...increased materially to $49.9 million, ... compared to a net loss of
# $8.4 million ... in the third quarter of 2025" -- a wider window can now
# reach the PRIOR-PERIOD number on the far side of a comparison clause.
# A number introduced by "compared to/with", "versus" etc. belongs to
# that other period, not the one the keyword itself is about.
COMPARISON_RE = re.compile(r"\b(compared (to|with)|versus|vs\.?|from)\b", re.IGNORECASE)


def parse_amount(match_text, group1, group2):
    val = float(group1.replace(",", ""))
    if "(" in match_text:
        val = -abs(val)
    if group2:
        val *= SCALE.get(group2.lower(), 1)
    return val


def find_claim(sentence, concept):
    if OUT_OF_SCOPE_RE.search(sentence):
        return None
    kw_re = CONCEPT_KEYWORDS[concept]
    # a sentence can mention the concept word more than once (an
    # introductory "Now turning to revenue," before the actual figure) --
    # try every occurrence, not just the first, and use the first one that
    # both isn't segment-scoped and has a usable number nearby.
    for kw_match in kw_re.finditer(sentence):
        if concept in ("revenue", "net_income", "operating_income") and \
                has_segment_qualifier(sentence, kw_match.start()):
            continue
        lo = max(0, kw_match.start() - WINDOW)
        hi = min(len(sentence), kw_match.end() + WINDOW)
        window = sentence[lo:hi]
        kw_lo, kw_hi = kw_match.start() - lo, kw_match.end() - lo
        best, best_dist = None, None
        for m in DOLLAR_RE.finditer(window):
            if concept != "eps_diluted" and not m.group(2):
                continue  # no scale word -- too ambiguous to trust for a $-figure claim
            if DELTA_BEFORE_RE.search(window[:m.start()]) or DELTA_AFTER_RE.search(window[m.end():]):
                continue  # this number is the SIZE OF A CHANGE, not a level
            between = window[kw_hi:m.start()] if m.start() >= kw_hi else window[m.end():kw_lo]
            if COMPARISON_RE.search(between):
                continue  # this number belongs to the OTHER side of a comparison
            dist = abs(m.start() - kw_lo)
            if best is None or dist < best_dist:
                best, best_dist = m, dist
        if best is None:
            continue
        value = parse_amount(best.group(0), best.group(1), best.group(2))
        if concept == "eps_diluted" and abs(value) > EPS_PLAUSIBLE_MAX:
            continue
        if concept in ("net_income", "operating_income"):
            # a spoken "loss" is never written with a minus sign -- the word
            # itself carries the sign that a filed XBRL value makes explicit
            if LOSS_RE.search(kw_match.group(0)) or LOSS_RE.search(sentence[kw_match.end():kw_match.end() + 20]):
                value = -abs(value)
            elif GAIN_RE.search(kw_match.group(0)):
                value = abs(value)
        return value
    return None


def verdict_for(claimed, truth, concept):
    denom = max(abs(truth), 1e-9)
    rel_err = abs(claimed - truth) / denom
    abs_err = abs(claimed - truth)
    # a speaker rounds to the nearest unit they bothered to say -- "$0.2
    # million" for a true -239,163 is correct speech, not a 16% miss, so a
    # small absolute gap is also "bound" even when the relative gap looks
    # large next to a small truth value. $50k ~= half of the finest commonly
    # spoken rounding (nearest $0.1 million); $0.02 ~= half a spoken cent.
    abs_floor = 0.02 if concept == "eps_diluted" else 50_000
    if rel_err <= 0.03 or abs_err <= abs_floor:
        return "bound", rel_err
    if rel_err <= 0.10:
        return "close_but_off", rel_err
    return "mismatch", rel_err


def score_transcript(transcript, ground_truth):
    claims = []
    for turn in transcript["turns"]:
        for sent in turn["sentences"]:
            text = sent["text"]
            for concept in CONCEPT_KEYWORDS:
                if concept not in ground_truth["figures"]:
                    continue
                claimed = find_claim(text, concept)
                if claimed is None:
                    continue
                truth = ground_truth["figures"][concept]["value"]
                verdict, rel_err = verdict_for(claimed, truth, concept)
                claims.append({
                    "speaker": turn["speaker"],
                    "start_sec": sent["start_sec"],
                    "sentence": text,
                    "concept": concept,
                    "claimed_value": claimed,
                    "filed_value": truth,
                    "relative_error": round(rel_err, 4),
                    "verdict": verdict,
                    "filing": {
                        "form": ground_truth["figures"][concept]["form"],
                        "filed": ground_truth["figures"][concept]["filed"],
                        "filing_index_url": ground_truth["figures"][concept]["filing_index_url"],
                    },
                })
    return claims


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    totals = {"bound": 0, "close_but_off": 0, "mismatch": 0}
    n_transcripts_with_claims = 0
    mismatches = []

    for gt_path in sorted(glob.glob(os.path.join(GT_DIR, "*.json"))):
        event_id = os.path.splitext(os.path.basename(gt_path))[0]
        with open(gt_path) as f:
            ground_truth = json.load(f)
        with open(os.path.join(DATA_DIR, f"{event_id}.json")) as f:
            transcript = json.load(f)

        claims = score_transcript(transcript, ground_truth)
        if not claims:
            continue
        n_transcripts_with_claims += 1
        for c in claims:
            totals[c["verdict"]] += 1
            if c["verdict"] == "mismatch":
                mismatches.append({"event_id": event_id, "ticker": ground_truth["ticker"], **c})

        out = {
            "event_id": event_id,
            "ticker": ground_truth["ticker"],
            "company": ground_truth["company"],
            "quarter_label": ground_truth["quarter_label"],
            "n_claims": len(claims),
            "n_bound": sum(1 for c in claims if c["verdict"] == "bound"),
            "claims": claims,
        }
        with open(os.path.join(OUT_DIR, f"{event_id}.json"), "w") as f:
            json.dump(out, f, indent=2)
        print(f"{event_id}  {ground_truth['ticker']:<6}  {len(claims)} claims found, "
              f"{out['n_bound']} bound")

    n_claims_total = sum(totals.values())
    print(f"\n{n_transcripts_with_claims} transcripts had at least one scoreable claim")
    print(f"{n_claims_total} claims scored total: "
          f"{totals['bound']} bound, {totals['close_but_off']} close_but_off, "
          f"{totals['mismatch']} mismatch")
    if n_claims_total:
        print(f"bindable fraction: {totals['bound'] / n_claims_total:.0%}")

    if mismatches:
        print(f"\n{len(mismatches)} flat mismatches (claim vs. filed figure disagree by >10%):")
        for m in mismatches:
            fmt = (lambda v: f"{v:,.2f}") if m["concept"] == "eps_diluted" else (lambda v: f"{v:,.0f}")
            print(f"  {m['ticker']} {m['event_id']} [{m['concept']}]: \"{m['sentence'][:90]}\" "
                  f"-- claimed {fmt(m['claimed_value'])}, filed {fmt(m['filed_value'])}")


if __name__ == "__main__":
    main()
