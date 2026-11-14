"""
Gold labels assigned by independently reading each sampled case's context
and official title (benchmark_sample.json) -- not by trusting the
automated topic_overlap score. This is deliberately a SEPARATE read, not a
re-run of score_citations.py's own logic, so it can actually catch that
logic's mistakes rather than just confirming them.

supported pool (35): now individually read and verified in full (not just
spot-checked). First pass: 12/35 read directly. Second pass: the LLM
baseline's 9 disagreements on the remaining 23 prompted checking those.
Third pass: the final 17 never individually read were checked too, once
the first two passes had established this pool wasn't as reliable as
"overlap >= 0.3" alone would suggest. Of all 35: 34 are genuine matches
(including several only verified by catching a benign CART-caption
variant -- "Bernbach"/"Birenbach", "Blakesley"/"Blakeslee" -- or a stray
one-year date slip while reading a title verbatim). Index 30 is the one
real error: the deterministic matcher's 0.5 overlap came entirely from
generic institutional words ("real property tax", "confirmation
resolution"), while the actual person named ("Cliftine Jones") doesn't
match the record's ("May Chan") -- a false positive the first spot-check
missed, caught only because a second, independent method (the LLM)
disagreed and got checked by hand. Index 27 is a genuine edge case, not a
clean error either way: the speaker says the bill is "now entitled" a
different name than LIMS has on file, consistent with a mid-session
rename our LIMS snapshot predates -- kept as "supported" (same bill) but
flagged.

no_context and weak pools: labeled in full (55 cases) -- this is where the
automated system's fixed 0.3 threshold and exact-token overlap metric
turn out to materially disagree with a careful read.

not_found pool (20): root-caused by period plausibility + context, not
re-labeled for topic (there's no record to check a topic against).
"""

# index -> gold label, for d['weak'] (25 cases)
WEAK_GOLD = {
    0: "supported", 1: "unverifiable", 2: "supported", 3: "unverifiable",
    4: "supported", 5: "supported", 6: "unverifiable", 7: "supported",
    8: "supported", 9: "supported", 10: "supported", 11: "supported",
    12: "supported", 13: "supported", 14: "supported", 15: "supported",
    16: "supported", 17: "supported", 18: "supported", 19: "supported",
    20: "supported", 21: "supported", 22: "supported", 23: "supported",
    24: "contradicted",  # PR26-0004 resolved -- real citation was almost
                         # certainly PR26-0477 ("PR 26-4 77"), a digit-split
                         # the existing tail-check guard doesn't catch
                         # (space-separated, not hyphen-separated)
    # cases 25-39 added in the benchmark expansion
    25: "supported", 26: "supported", 27: "supported", 28: "contradicted",
    29: "supported", 30: "supported", 31: "unverifiable", 32: "unverifiable",
    33: "supported", 34: "supported", 35: "supported", 36: "supported",
    37: "supported", 38: "unverifiable", 39: "supported",
}

# index -> gold label, for d['no_context'] (30 cases)
NO_CONTEXT_GOLD = {
    0: "unverifiable", 1: "uncertain", 2: "unverifiable", 3: "unverifiable",
    4: "contradicted",   # "BILL 26-22 FOUR" -> real number is B26-0224,
                         # spoken-word digit continuation ("FOUR") not
                         # caught by the numeric-only regex
    5: "unverifiable", 6: "contradicted",  # "PR 26-5 HUNDRED 99" -> PR26-0599
    7: "supported",      # "DIOCESE" vs "Archdiocese" -- exact-token miss
    8: "contradicted",   # "BILL 26-58 90" -> B26-0589 or B26-5890-shaped split
    9: "unverifiable", 10: "unverifiable", 11: "unverifiable",
    12: "supported",     # "displaced homeowners" vs "Homeownership" -- stem miss
    13: "unverifiable", 14: "unverifiable",
    15: "supported",     # "Accountability Act" phrase visible, truncated window
    16: "unverifiable", 17: "unverifiable",
    18: "contradicted",  # genuine real-world mismatch -- speaker calls B26-0679
                         # the "Soccer Stadium Redevelopment Act"; LIMS has it as
                         # the water/sewer billing bill. Not a parsing artifact.
    19: "unverifiable",
    20: "contradicted",  # speaker explicitly titles B26-0006 "RFK Campus Small
                         # Area Plan Amendment Act"; LIMS title is unrelated
    21: "unverifiable", 22: "unverifiable", 23: "unverifiable",
    24: "supported",     # "Finnegan" -- a real tax-apportionment term matching
                         # "Combined Reporting Amendment Act"; needs domain
                         # knowledge a word-overlap metric can't have
    25: "supported",     # "assessments"/"appeal cycle" vs "Assessment and Appeals"
    26: "unverifiable", 27: "supported", 28: "unverifiable", 29: "unverifiable",
    # cases 30-54 added in the benchmark expansion
    30: "unverifiable", 31: "unverifiable", 32: "unverifiable",
    33: "contradicted",  # "BILL 26-3 98" -> real number almost certainly
                         # B26-0398; same digit-split pattern, resolved to
                         # the wrong record (B26-0003)
    34: "unverifiable",
    35: "unverifiable",
    36: "contradicted",  # genuine natural contradiction, not a parsing bug:
                         # content clearly describes "Harmony Park" (the
                         # same park as B26-0331, confirmed elsewhere), but
                         # resolves to a real, different, valid record (a
                         # contract approval) under B26-0231
    37: "unverifiable",  # window-boundary issue: this citation's own title
                         # precedes what the fixed-width window captured;
                         # the text shown is the adjacent bills' names
    38: "unverifiable",
    39: "unverifiable",
    40: "supported",     # "BSA" -- the standard abbreviation for "Budget
                         # Support Act," a domain-knowledge acronym match
    41: "unverifiable", 42: "unverifiable", 43: "unverifiable",
    44: "supported",     # "Bottle Bill" -- the common nickname for
                         # container-deposit/recycling-refund legislation
    45: "unverifiable", 46: "unverifiable", 47: "unverifiable",
    48: "supported",     # content (ballot access process, Board of
                         # Elections, petition evaluation) matches the real
                         # subject even without sharing the title's exact words
    49: "unverifiable",
    50: "contradicted",  # "BILL 26-22 FOR..." ("FOR" = "FOUR" spoken) --
                         # the same B26-0224/B26-0022 digit-split bug,
                         # recurring independently; corroborates it as a
                         # real, repeatable pattern rather than a one-off
    51: "unverifiable", 52: "unverifiable", 53: "unverifiable",
    54: "supported",     # same bill (B26-0403) confirmed elsewhere with a
                         # clear match; this mention alone is generic but
                         # consistent, not contradictory
}

# index -> gold label, for d['supported'] (now 55 cases after the
# benchmark expansion); only entries that differ from the pool's default
# "supported" assumption are listed. All 55 are now individually read.
SUPPORTED_POOL_OVERRIDES = {
    30: "contradicted",  # Cliftine Jones named in the transcript; the
                         # record this resolved to confirms May Chan --
                         # a different person. High overlap came entirely
                         # from generic institutional words.
    51: "unverifiable",  # confirms the institution (Board of Trustees of
                         # UDC) but never names the person (Marc Battle) --
                         # same boilerplate-overlap failure mode as index
                         # 30, just caught this time before being trusted.
}

NOT_FOUND_ROOT_CAUSE = {
    0: "unidentified_garble",       # B20-0659 -- real bill (B26-0659, FY27
                                     # budget act) doesn't match the "utility
                                     # bills" content spoken, so even that
                                     # guess is wrong; true source unclear
    1: "genuine_old_period",        # B24-0760
    2: "unidentified_garble",       # PR20-2641, likely PR26-04xx (EMS medical
                                     # director confirmation), not confirmed
    3: "genuine_old_period",        # B15-0032
    4: "truncated_midword",         # B26-0000, caption cut off mid-number
    5: "impossible_period",         # PR36-0639
    6: "impossible_period",         # B226-0595
    7: "genuine_old_period",        # B22-0950
    8: "genuine_old_period",        # B21-0777
    9: "impossible_period",         # B26-6659 -- bill numbers don't reach 6659
    10: "unidentified_garble",      # B20-0661
    11: "unidentified_garble",      # PR20-0654
    12: "unidentified_garble",      # B20-0066
    13: "impossible_period",        # B265-0030
    14: "impossible_period",        # B76-0040
    15: "unidentified_garble",      # B20-0062
    16: "impossible_period",        # B26-2271 -- too large for period 26
    17: "genuine_old_period",       # B24-0641
    18: "impossible_period",        # B36-0360
    19: "genuine_old_period",       # B25-0106
}
