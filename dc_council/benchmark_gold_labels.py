"""
Gold labels assigned by independently reading each sampled case's context
and official title (benchmark_sample.json) -- not by trusting the
automated topic_overlap score. This is deliberately a SEPARATE read, not a
re-run of score_citations.py's own logic, so it can actually catch that
logic's mistakes rather than just confirming them.

supported pool (35): spot-checked 12/35 directly; the LLM baseline's 9
disagreements on the remaining 23 prompted checking those too. 8 were the
LLM being wrong (overly literal about a one-year date slip, or missing an
exact-phrase match buried among witness names) -- real matches, kept as
"supported". Index 30 was genuinely wrong: the deterministic matcher's
0.5 overlap came entirely from generic institutional words ("real property
tax", "confirmation resolution"), while the actual person named
("Cliftine Jones") doesn't match the record's ("May Chan") -- a real false
positive this benchmark's own spot-check missed, caught only because a
second, independent method (the LLM) disagreed and got checked by hand.
Index 27 is a genuine edge case, not a clean error either way: the speaker
says the bill is "now entitled" a different name than LIMS has on file,
consistent with a mid-session rename our LIMS snapshot predates -- kept as
"supported" (same bill) but flagged.

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
}

# index -> gold label, for d['supported'] (35 cases); only entries that
# differ from the pool's default "supported" assumption are listed
SUPPORTED_POOL_OVERRIDES = {
    30: "contradicted",  # Cliftine Jones named in the transcript; the
                         # record this resolved to confirms May Chan --
                         # a different person. High overlap came entirely
                         # from generic institutional words.
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
