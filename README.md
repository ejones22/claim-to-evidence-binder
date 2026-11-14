# Claim-to-Evidence Binder

Does a spoken claim in a public meeting actually bind to the official record, or does
letting an automated verifier abstain on weak evidence make a real difference to how
often it's wrong? Built over the AI x Epistemics Research Sprint (Nov 13-15, 2026).

**Primary result (`dc_council/`):** across 302 real DC Council meetings, we score
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
| `reconcile_root_causes.py` | New (final root-cause breakdown of unresolved citations) |
| `error_taxonomy.json` | New (qualitative breakdown of the abstaining judge's remaining mistakes) |
| `rater2_review_form.txt`, `parse_rater2_review_form.py`, `score_rater2_review.py` | New (independent inter-rater review materials, parser and scorer) |
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
