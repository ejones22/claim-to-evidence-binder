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
| `benchmark_gold_labels.py`, `compute_benchmark_metrics.py` | New |
| `llm_judge_baseline.py`, `llm_forced_baseline.py`, `compare_abstention.py` | New |
| `regenerate_from_backup.py` | New (one-off migration script, kept for provenance) |
| `*.json`, `*.jsonl` | New (this sprint's generated results) |

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
python3 make_figures.py
```

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
