# Claim-to-Evidence Binder

Does a spoken claim in a public meeting actually bind to the official record, or does
letting an automated verifier abstain on weak evidence make a real difference to how
often it's wrong? Built over the AI x Epistemics Research Sprint (Nov 13-15, 2026).

**Headline finding: the "best judge" on an LLM-judge leaderboard can be an artifact of
a hidden gold-label bias, not a property of the models.** We built the citation-binding
benchmark below, scored 7 judges on it (three local, two Claude models, a hosted
decision model, and a third-party API), and got a clean leaderboard where Claude
Sonnet 5.5 and a 397B hosted model narrowly beat Claude Haiku 5.5. Then an independent
second rater blind-labeled a held-out sample and found the *gold labels themselves* were
biased toward "supported" -- never the reverse. Applying that now-explicit standard to
the rest of the benchmark by hand and re-scoring every judge's already-collected output
(no re-running, no new API calls) **inverts the ranking**: Claude Haiku 5.5 goes from
third to clearly first, at roughly 1/20th the cost of the models that had "beaten" it.
Every judge gets worse under the corrected labels -- the ranking changes because they
get worse by different amounts. See Figure 3 and "Inter-rater check" below. We think
this generalizes: an LLM-judge benchmark's leaderboard is only as trustworthy as its
gold labels, and that's checkable with a small blind re-rating, not just assumed.

**Testbed (`dc_council/`):** across 302 real DC Council meetings, we score
whether a spoken bill/resolution citation (a) resolves to a real legislative record
and (b) is actually discussed consistently with what that record says. On a
200-case hand-reviewed benchmark, an LLM judge allowed to abstain on weak evidence
cuts its error rate roughly in half to two-thirds compared to the same model forced
to always answer -- at the cost of giving up confident judgment on a third to 40% of
cases, depending on the model. Tested across three models (qwen2.5:3b, qwen2.5:7b,
qwen3.5:9b): **the benefit tracks model capability, not size alone** -- the smallest
model barely uses the abstain option at all (96.7% coverage, no real error
improvement), while both larger models use it meaningfully. A paired significance
test (McNemar's, n=120 covered cases) shows the honest, more precise version of this
finding: most of the headline gap is the model correctly routing away from its
hardest cases (a real, useful behavior), not sharper reasoning on the cases it does
judge either way (p=0.125, not significant on the cases both systems judge in common).

**Stress-testing the evaluation itself:** the original validity check used random
title swaps as negative examples, which mostly produce wildly off-topic pairings --
an easy target. Rebuilt as same-category swaps (wrong confirmation resolution, not
just a random unrelated bill) to test the realistic failure mode: the deterministic
matcher's false-accept rate nearly quintuples (2.2% -> 10.8%), confirmed by hand to
be a genuine weakness (shared category boilerplate language inflates the score even
when the named person/property is wrong). The LLM judge holds up under the same
harder test (2% false-accept), and that one miss is a confirmed dataset artifact
(adjacent citations read in sequence bleeding into the fixed-width context window),
not a reasoning failure -- the same artifact independently explains the only other
LLM miss found anywhere in the project.

**Root-cause rigor:** of 39 distinct citations that never resolved to a LIMS record,
most are now individually explained rather than left as an aggregate percentage --
38% are genuine references to a council period our data snapshot doesn't cover, 18%
trace to a specific, narrow mechanism (one batch of bills shows the same leading-
digit substitution, consistent with one stenographer's typing habit), and most of
a previously-unexplained "period 20" anomaly (8 of 10 cases) was resolved by cross-
referencing transcript content directly against LIMS.

**Inter-rater check:** a second person independently labeled a blind 30-case
sample (`rater2_review_form.txt`, with the sampling-pool ids redacted so the pool
couldn't hint at the answer). Agreement with the original gold labels: 21/30 (70%),
Cohen's kappa 0.46 (moderate). All 9 disagreements go the same way: the original
labeling said "supported" and the second reviewer said "unverifiable" (8) or
"contradicted" (1), so the original gold labels are more generous toward
"supported" than an independent reader. Kappa is 0.44 (20/29) if the one case with
an original "uncertain" label is excluded instead of being treated as "unverifiable".
One disagreement (`weak_pool#27`) isn't just a borderline call: the transcript names
the wrong street ("25th Street" vs. the official title's "35th Street" for B26-0772),
confirmed against LIMS and a related record (PR26-0805) on the same squares. The
citation itself resolves correctly -- this is the same leading-digit caption
substitution documented below in "Root-cause rigor", here corrupting a content
detail rather than the citation number. See `error_taxonomy.json` category G.

**Sensitivity bound on the "supported" bias** (`sensitivity_strict_supported.py`):
rater2's standard -- the transcript must actually confirm a measure's specific
content, not just name it alongside siblings -- was applied by hand to the rest
of the "supported" pools the 30-case sample was drawn from (95 cases total: 53
supported_pool + 32 weak_pool + 10 no_context_pool overrides). 11 more cases fail
it, on top of the 9 the independent review already found, moving 20/95 (21%) of
"supported" gold labels to unverifiable/contradicted. Re-scoring the headline
abstention result under this stricter gold: the abstaining qwen2.5:7b judge's
error rate on its 120 covered answers rises from 13.3% to 21.7% (same cases, same
coverage -- 10 of them were "supported" calls that no longer are), and the forced
judge's rises from 41.5% to 46.0%. **The core finding survives**: abstaining still
cuts error to less than half of forced (21.7% vs. 46.0%, vs. 13.3% vs. 41.5%
originally) -- the absolute error levels this report should be read with are
closer to the stricter numbers, but the comparative claim (abstention helps, by
roughly half) is not an artifact of the labeling bias. This bound was applied by
one person, not independently reviewed itself -- treat it as a bound, not a
replacement gold standard.

**Stronger independent audit (complete, two reviewers):** `build_stronger_audit_sample.py`
addresses two gaps in the above: the original rater2 review excluded originally-
contradicted cases entirely and was a single 30-case sample, and the strict
relabeling just above was one person's pass, never independently checked. It draws
TWO separate blind samples -- `stronger_audit_form.txt` (60 fresh natural cases:
all 11 remaining natural "contradicted" cases, plus a stratified sample of
supported/unverifiable ones, none previously reviewed) and
`strict_relabel_diagnostic_form.txt` (the 20 cases the strict relabeling touched,
as a separate targeted check, never pooled with the random-sample agreement rate).
Both use a two-field schema per case -- FIELD 1: does the transcript address this
same measure at all; FIELD 2: does it actually confirm this measure's specific
content, as opposed to just naming it -- plus an overall 3-way label. Two
reviewers (blind, independent, no access to each other's answers or the keys)
completed both samples; `score_stronger_audit.py` scores each against the answer
key and, given both filled forms, the two reviewers against each other.

Diagnostic sample (20 cases, checks whether the one-person strict relabeling
holds up): reviewer 1 agreed with the relabeling on 18/20 (90%), reviewer 2 on
17/20 (85%); the two reviewers agreed with each other on 17/20 (85%). Both
reviewers, independently, missed the same case (`weak_27`, the 25th/35th Street
mismatch) -- it needs outside geographic knowledge to catch, which is itself a
data point for why a deterministic record check, not a careful human skim, has
to be the first line of defense.

Fresh sample (60 cases, the real agreement estimate): reviewer 1 agreed with the
original gold on 34/60 (56.7%, kappa=0.38); reviewer 2 on 40/60 (66.7%,
kappa=0.50). The number that matters most -- genuine two-person independent
agreement -- is **41/60 (68.3%, kappa=0.45)**, moderate on the standard scale:
a real but unsurprising ceiling for a task this subjective, not a red flag.
More importantly, both reviewers' disagreements with the original gold point the
same direction: 16 of reviewer 2's 20 disagreements (80%) and the large majority
of reviewer 1's call "unverifiable" or "contradicted" where the original gold
says "supported," essentially never the reverse. That makes four independent
checks now -- the original rater2 review (9/30), the strict relabeling pass,
and these two fresh reviewers -- all finding the same one-directional bias in
the original "supported" label, at increasing scale. That convergence, more
than any single number, is why we treat the ranking-inversion finding above as
real rather than an artifact of one reviewer's idiosyncrasy.

**Secondary exploration (`earnings_calls_exploratory/`):** an earlier, smaller pass
at the same idea applied to a different domain -- checking numeric claims on
corporate earnings calls against SEC XBRL filings. Kept for context, not part of
the submitted results.

## What's new this sprint vs. preexisting

This project builds on an existing DC Council transcript pipeline (Granicus caption
scraping + a basic speaker-attribution parser) that predates this sprint. Everything
in `dc_council/` below is new work from this weekend, with one exception called out:

| File | Status |
|---|---|
| `fetch_captions.py` | **Modified.** The file (caption scraping/parsing) predates the sprint; `dedupe_caption_text()` is new. See "The caption bug" below. |
| `score_citations.py` | New |
| `validate_citation_binding.py` | New |
| `hard_negative_check.py` | New (stress test: same-category negatives, not just random swaps) |
| `benchmark_gold_labels.py`, `compute_benchmark_metrics.py` | New |
| `llm_judge_baseline.py`, `llm_forced_baseline.py`, `compare_abstention.py` | New |
| `significance_test.py` | New (McNemar's exact test + bootstrap CIs) |
| `run_second_model.py`, `compare_second_model.py` | New (third-model robustness check) |
| `jev_judge.py`, `compare_jev.py` | New (hosted decision-model judge, TypeSafe AI's Jev, as a comparison to the local LLM judges) |
| `claude_batch_judge.py` | New (Claude Haiku 5.5 / Sonnet 5.5 judges via Anthropic's Message Batches API, same prompt as the Ollama judge) |
| `reconcile_root_causes.py` | New (final root-cause breakdown of unresolved citations) |
| `error_taxonomy.json` | New (qualitative breakdown of the abstaining judge's remaining mistakes) |
| `rater2_review_form.txt`, `parse_rater2_review_form.py`, `score_rater2_review.py` | New (independent inter-rater review materials, parser and scorer) |
| `sensitivity_strict_supported.py` | New (sensitivity bound: re-scores the headline result after relabeling "supported" cases that fail rater2's stricter standard) |
| `build_stronger_audit_sample.py`, `make_stronger_audit_forms.py`, `score_stronger_audit.py` | New (stronger independent audit: fresh 60-case sample + 20-case relabeling diagnostic, two-field schema) |
| `sensitivity_all_judges.py` | New (applies the same correction to every judge's already-collected outputs, all 200 cases) |
| `datapipeline/05b_sensitivity_strict_gold.py` | New (same correction, restricted to the held-out test split) |
| `datapipeline/05c_shared_cases_comparison.py` | New (coverage-matched comparison: every judge on exactly the same answered cases) |
| `regenerate_from_backup.py` | New (one-off migration script, kept for provenance) |
| `*.json`, `*.jsonl`, `*.png` | New (this sprint's generated results and figures) |

`earnings_calls_exploratory/` is entirely new this sprint, built and then set aside
in favor of the DC Council direction.

Not included in this repo: the raw pulled data (302 meetings' caption transcripts,
~130MB; the LIMS legislation snapshot, ~7MB; 92 companies' SEC XBRL filings,
~140MB). All of it is regeneratable from the fetch scripts against public sources
(Granicus, SEC EDGAR, DC Council's LIMS). `citations_scored.jsonl` and the
benchmark/results files *are* included -- they're the actual evidence behind the
reported numbers, just not the multi-hundred-MB raw pulls behind those.

## The caption bug

Granicus's live CART captioning page displays a rolling word window that grows and
shifts as the stenographer types -- and its TranscriptViewer page logs every one of
those intermediate window states, not just the final line. Naively joining them (the
preexisting scraper's behavior) reproduces every sentence many times over, each copy
shifted or one word longer than the last. `dedupe_caption_text()` in
`fetch_captions.py` fixes this with a greedy overlap-skip reconstruction. Verified
against the live Granicus pages directly (not just our own stored data): fixed 78 of
302 meetings, corpus-wide word-level duplication dropped from an 87.8% average (in
the affected meetings) to a 0.9% clean baseline.

## Comparison: a hosted decision model (Jev)

`jev_judge.py` runs the same 200-case benchmark through Jev 1.13.0 (TypeSafe AI's
hosted "System One" decision model, which returns label probabilities rather than
generated text), with the same inputs (context + title) and the same three label
definitions as the Ollama judge prompt. Accessed via the jevmodel.org reseller
endpoint, an independent service not operated by TypeSafe AI.

| Judge (same 200 cases) | Answered | Errors | Error rate on answered |
|---|---|---|---|
| Jev 1.13.0 | 131 (66%) | 17 | 13.0% |
| qwen2.5:7b | 120 (60%) | 16 | 13.3% |
| qwen3.5:9b | 148 (74%) | 23 | 15.5% |
| Claude Haiku 5.5 | 129 (64%) | 10 | 7.8% |
| Claude Sonnet 5.5 | 139 (70%) | 9 | 6.5% |

Jev roughly ties qwen2.5:7b on error rate while answering 11 more cases, at
~0.5-0.8s/call median versus ~3s/call for local qwen3.5:9b. Its main failure is
the same over-caution the LLM judges show: 29 of 95 gold-supported cases called
"unverifiable", mostly near-verbatim title reads.

Its probabilities are **not** calibrated: answers given 0.8-0.9 confidence are
right 62% of the time, and 0.9-1.0 answers are right 84%. They do rank well --
requiring P(chosen) >= 0.6 cuts error to 10.9% at 60% coverage, the same
coverage as qwen2.5:7b -- but that threshold was picked on the same 200 cases it
was scored on, so it is optimistic until cross-validated. Used as the middle-band
judge behind the deterministic matcher (matcher accepts topic_overlap >= 0.6),
Jev does worse than the local models (11.5% vs 8.8% for qwen2.5:7b), because its
abstentions are concentrated in the high-overlap band the matcher already handles.

Each judge was run once; the Jev prompt wording was not tuned.

**Claude Haiku 5.5** (`claude_batch_judge.py`, Message Batches API, effort `low`,
the exact Ollama judge prompt) is the most accurate judge tested: 7.8% error at
64% coverage, about 40% fewer errors than Jev or qwen2.5:7b at similar coverage,
and only 2 real matches called "contradicted". Behind the deterministic matcher it
reaches 6.6% error (136 answered). It shares the same over-caution as every other
judge here (28 of 95 gold-supported cases called "unverifiable"), which points at
the shared prompt rather than any one model. The 200-case batch cost roughly half
a cent (~84k input / ~11k output tokens at batch pricing) and finished in about a
minute. Haiku's sampling can't be pinned to temperature 0, so reruns may differ
slightly.

**Claude Sonnet 5.5** (`claude_batch_judge.py --model sonnet`, same prompt and
settings) answers more cases than Haiku with fewer errors: 6.5% error at 70%
coverage on all 200, 5.6% behind the deterministic matcher, and the highest 3-way
agreement with gold of any judge (84.5%). On the held-out test split
(`datapipeline/results/leaderboard.md`) it is 8.4% vs Haiku's 8.9% -- within
noise -- at about 20x the cost ($0.13 for the 200-case batch vs Haiku's $0.007;
$0.00107 vs $0.00006 per correct answer on test).

**This Sonnet-over-Haiku edge doesn't survive the "supported"-label sensitivity
check above, and neither does Adaption's qwen3.5-397b leading the test-split
leaderboard.** `sensitivity_all_judges.py` (all 200) and
`datapipeline/05b_sensitivity_strict_gold.py` (held-out test split) rescore every
hosted and local judge's *already-collected* outputs -- no re-run, no new API
calls -- against the stricter gold. Every judge's error rate rises (the bias
affects all of them, since they were scored against the same labels), but not
by the same amount, and the ranking changes:

| judge (test split) | original error | strict error |
|---|---|---|
| Claude Haiku 5.5 | 8.9% | **13.9%** |
| Adaption qwen3.5-397b | 8.2% | 16.5% |
| Claude Sonnet 5.5 | 8.4% | 18.1% |
| Jev 1.13.0 | 12.3% | 21.0% |
| legacy qwen2.5:7b | 13.0% | 23.2% |

(plotted as `figure3_ranking_inversion.png`, `make_figures.py`)

**Claude Haiku 5.5 moves from third to clearly first** once the correction is
applied, on both the full-200 and held-out-test views -- it absorbs the
relabeling better than every other judge tested, at roughly 1/20th Sonnet's cost
and well under Adaption's. Read as: the original leaderboard's ranking of the
*best* judges (Sonnet/qwen3.5-397b/Haiku, all within ~1 point of each other) was
partly an artifact of which judge happened to call the mislabeled "supported"
cases "unverifiable" more often -- Haiku did that more than Sonnet did, which
originally looked like over-caution and under the corrected standard looks like
being right. The result that abstention beats forced-answer, and that capability
beats raw size, both still hold; which specific hosted judge is "best" does not,
without this correction.

**A coverage-matched comparison goes further: among the capable judges, there may be
no real quality difference at all.** `05c_shared_cases_comparison.py` restricts every
judge to the 48 test-split cases ALL seven judges actually committed to (removing
coverage differences from the comparison entirely, not just relabeling). On exactly
those 48 cases, Jev, Adaption's qwen3.5-397b, Claude Haiku 5.5, and Claude Sonnet 5.5
are tied -- 2.1% error under the original gold, 8.3% under the strict gold, and
Haiku vs. Sonnet make identical calls on every single one (0 discordant pairs,
McNemar's undefined). The two local models are clearly worse on this same shared set
(12.5%/16.7%). So there's a genuine capability cliff between local and hosted-tier
models, but no detectable difference *among* the hosted-tier judges -- the entire
apparent ranking between them, in both the original and corrected leaderboards, comes
from which additional, harder cases each one chooses to answer, not from judging
those cases better or worse. This is the same shape as the project's headline finding
(abstention helps mostly via routing, not sharper reasoning, p=0.125) recurring one
level up: selection effects, not judgment quality, appear to dominate this kind of
evaluation at every level examined so far.

## Reproducing the results

```
cd dc_council
python3 score_citations.py              # needs data/lims/bulk_legislation.json + data/videos/*.turns.json
python3 validate_citation_binding.py     # synthetic title-swap validity check + risk-coverage curve
python3 llm_judge_baseline.py            # needs Ollama running locally with qwen2.5:7b
python3 llm_forced_baseline.py
python3 compute_benchmark_metrics.py
python3 compare_abstention.py            # the headline abstention-vs-forced result
python3 significance_test.py             # McNemar's exact test + bootstrap CIs
python3 run_second_model.py              # robustness check against a different model
python3 compare_second_model.py
python3 jev_judge.py                     # needs a jevmodel.org key as Jev= in ../.env (~110k tokens)
python3 claude_batch_judge.py --submit   # needs a Claude= key in ../.env
python3 claude_batch_judge.py --collect  # waits for the batch, writes claude_haiku_judge_results.json
python3 claude_batch_judge.py --submit --model sonnet    # same for Sonnet 5.5
python3 claude_batch_judge.py --collect --model sonnet   # writes claude_sonnet_judge_results.json
python3 compare_jev.py                   # Jev vs the Ollama judges and Haiku, calibration, router
python3 reconcile_root_causes.py         # final root-cause breakdown of unresolved citations
python3 hard_negative_check.py           # stress test: same-category negatives vs. random ones
python3 make_figures.py
```

To score the independent inter-rater review from the filled-in form:
```
python3 parse_rater2_review_form.py        # rater2_review_form.txt -> rater2_labels.json + rater1_labels.json
python3 score_rater2_review.py             # raw agreement, Cohen's kappa, list of disagreements
```
The form's ids are redacted and repeat, so the parser matches answers to cases by
order (CASE n -> entry n in `rater2_blind_sample.json`) and checks each case's context
text to confirm the match. It maps the one "uncertain" gold label (`no_context_1`)
to "unverifiable", as `significance_test.py` does.

`run_second_model.py` is set to `qwen3.5:9b`, a "thinking" model that defaults to
~26-54s/call; it passes Ollama's native `"think": false` request field to suppress
that reasoning pass, which is what makes 400 calls in one run practical (~3s/call
instead). Without that flag the same run would take 3+ hours.

## Limitations and Dual-Use / Ethical Considerations

See the full report for the required Limitations and Dual-Use / Ethical
Considerations appendix. In short: this measures whether a citation exists and is
discussed consistently with its official record -- it does not and cannot verify
that the underlying claim is factually true, and no output from this system should
be read as fact-checking in that sense.
