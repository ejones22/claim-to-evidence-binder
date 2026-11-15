# Judge Evaluation Pipeline: Spec

Status: draft, written before the code. Owner: the claim-to-evidence team.
Scope: `datapipeline/`. Nothing in `dc_council/` is modified; this pipeline
reads its outputs and imports its prompts.

---

## 1. Why this exists

`dc_council/` answers one question well: on 200 hand-labeled cases, does
letting an LLM judge abstain lower its error rate? It does that with one
script per model (`llm_judge_baseline.py`, `run_second_model.py`, ...),
results keyed by *position in a list*, and every metric computed on all
200 cases.

That's fine for a single finding. It gets in the way of the next one:
**which judge is best?** We want to compare many more judges (bigger
hosted models on Adaption credits, and Ollama's new "decision" models),
and that needs three things the current scripts don't have:

1. **A held-out test set.** Today there's no train/val/test split. Every
   reported number is computed on the same 200 cases that were used to
   write the prompts, pick the 0.3 overlap threshold, and adjudicate the
   gold labels. As soon as we *tune* anything (an abstention threshold,
   a few-shot example, a choice of model), we need cases we didn't tune on.
2. **One judge interface.** Adding a model should mean adding one entry
   to a registry, not copying a script.
3. **Stable case IDs.** Results are currently matched to gold labels by
   their order within each pool. Reordering or a partial run silently
   misaligns them. Every case gets an ID, and every result row carries it.

## 2. Answer to "do we support train/val/test today?"

**No.** Concretely:

| Thing | Today |
|---|---|
| Benchmark | 200 cases in `benchmark_sample.json`: 55 `supported`, 40 `weak`, 55 `no_context` pool, 50 `synthetic_contradicted` |
| Gold labels | `benchmark_gold_labels.py`, as dicts keyed by pool index |
| Gold distribution | 95 supported, 61 contradicted, 43 unverifiable, 1 uncertain |
| Splits | none; every metric uses all 200 (or the first 120 for the qwen2.5:3b run) |
| Training | none; all judges are zero-shot, so the lack of a split hasn't biased a *trained* model, but it has biased the prompt and threshold choices |

Two known contamination issues, which the split can't undo and the report
should state:

- **Prompt/threshold development** looked at these cases. Numbers on the
  full 200 are optimistic for the legacy qwen2.5:7b setup in particular.
- **Gold adjudication used qwen2.5:7b's disagreements** to decide which
  cases to re-read (see the `benchmark_gold_labels.py` docstring). Cases
  where qwen2.5:7b *agreed* with a wrong first-pass label were less likely
  to be caught. That biases the benchmark toward qwen2.5:7b looking right.
  Other judges may be penalised for being right where the gold is wrong.
  Mitigation: the independent second-rater review (`ivan_review_form.txt`).

## 3. Data

### 3.1 Case record (`data/benchmark.jsonl`)

One JSON object per line. Built by `01_build_dataset.py` from
`dc_council/benchmark_sample.json` plus `dc_council/benchmark_gold_labels.py`.

| Field | Meaning |
|---|---|
| `case_id` | `"{pool}-{index:03d}"`, e.g. `weak-024`. The index is the case's position in its pool in `benchmark_sample.json`, so it lines up with the gold-label dicts. |
| `pool` | `supported`, `weak`, `no_context`, `synthetic_contradicted` |
| `clip_id` | meeting ID; the split's grouping key |
| `normalized` | cited bill/resolution number, e.g. `B26-0596` |
| `context` | transcript window (same text the legacy judges saw) |
| `title` | the title shown to the judge: `official_title`, or `swapped_title` for synthetic cases |
| `gold` | label exactly as in `benchmark_gold_labels.py` (`supported` / `contradicted` / `unverifiable` / `uncertain`) |
| `gold_3way` | `gold` with `uncertain` mapped to `unverifiable`, the same mapping `significance_test.py` applies |
| `is_synthetic` | true for `synthetic_contradicted` (gold by construction, not by reading) |

Not included: the `not_found` pool (35 cases). Those never resolved to a
record, so there's no title to judge against.

### 3.2 Stress set (`data/stress_hard_negatives.jsonl`)

Same-category title swaps, built the way `hard_negative_check.py` builds
them (a confirmation resolution swapped for a different confirmation
resolution, and so on). Gold is `contradicted` by construction. Rebuilt
deterministically from `citations_scored.jsonl`: sorted titles and a
seeded RNG. The original script picks from a Python `set`, whose order
changes between runs, so its exact 50 cases can't be reproduced. This set
is reported separately and never mixed into train/val/test, because its
contexts come from the same meetings as the benchmark.

Known label noise, found by reading qwen3.5-397b's false accepts: some
swapped titles are a bill the context window *also* names, because the
same hearing or agenda covers both (`stress-081`, where "Eric's ID
Amendment Act" appears verbatim in the window) or the next citation is
read out right after (`stress-039`). Accepting those isn't a reasoning
error. It's the adjacent-citation window artifact the top-level README
already documents. So stress false-accept rates are an upper bound.

### 3.3 Splits (`data/splits.json`)

```json
{"seed": 2026, "ratios": {"train": 0.2, "val": 0.2, "test": 0.6},
 "assignments": {"weak-024": "test", ...}, "summary": {...}}
```

- **Grouped by meeting (`clip_id`).** Cases from the same meeting share
  speakers, agenda and often overlapping context windows, and 4 synthetic
  cases reuse a real case's exact context. A meeting-level split stops
  that from leaking across splits. 200 cases across 83 meetings, at most
  12 per meeting, so grouping is feasible.
- **Stratified by `gold_3way`.** The algorithm visits meetings in a seeded
  random order and puts each one in whichever split brings per-label
  counts closest to the target. Ratios come out approximate, not exact;
  the summary prints the real counts.
- **Ratios are 20/20/60.** There's no gradient training, so `train` is
  small: it's only a pool of few-shot examples. `val` is for choosing
  thresholds and models. `test` (about 120 cases) is the number we report,
  and it's about the size of the original 120-case benchmark.
- **Rules.** Never tune on `test`. Report `all` (200) only for
  comparison with the legacy numbers, and label it as such.

## 4. Judges

### 4.1 What a judge is

A judge maps `(context, title)` to a label. Each judge is one entry in
`JUDGES` in `config.py`:

```python
"adaption/qwen3.5-397b/abstain": {
    "backend": "adaption", "model": "qwen3.5-397b", "mode": "abstain",
},
```

- **mode `abstain`** is the 3-way task: supported / contradicted / unverifiable.
- **mode `forced`** is the 2-way task: supported / contradicted.

Prompts aren't redefined. Generative backends import `PROMPT_TMPL`
verbatim from `dc_council/llm_judge_baseline.py` (abstain) and
`dc_council/llm_forced_baseline.py` (forced), so a new model sees exactly
the text the legacy models saw. Decision models get the same task in their
native schema (§4.4).

### 4.2 Backend `ollama`: legacy local generation

`POST localhost:11434/api/generate`, `temperature: 0`, `think: false`.
The response is parsed with the legacy regex (first matching label word,
upper-cased). This is how the baselines are reproduced.

### 4.3 Backend `adaption`: bigger hosted models

Adaption Labs Responses API, paid for with hackathon credits.

- `POST https://api.prod.adaptionlabs.ai/api/v1/responses`
- `Authorization: Bearer $ADAPTION_API_KEY`
- body: `{"model", "input": <prompt>, "temperature": 0, "max_output_tokens", "store": false}`
- answer text: top-level `output_text`

Candidate models (from the Adaption models page, Nov 2026): `qwen3.5-397b`,
`glm-5.2`, `deepseek-v4-flash`, `glm-53-flash`, `gemma-4-31b-it`,
`gemma-4-26b-a4b-it`, `qwen3.8-27b`. The registry starts with three:
`qwen3.5-397b` (largest member of the family we already tested),
`deepseek-v4-flash` (cheapest), and `glm-5.2` (a different family).

What the first real calls showed (Nov 14):

- **Reasoning is off** (`"reasoning": {"effort": "none"}`). With it on,
  qwen3.5-397b spent all 256, and then all 4,096, output tokens on hidden
  reasoning for one label (44s, about $0.014) and returned no answer text.
  With it off: one word, about 1.4s and about $0.00015 per call. That's
  the hosted equivalent of the `think: false` the legacy qwen3.5:9b run
  used, so the comparison is like for like. A reasoning-on judge would be
  its own, separately named entry with a large token budget.
- **Rate limit.** About 20 fast calls trigger a per-user 429 that says
  "retry after 60 seconds". The client waits it out; that isn't counted
  as an error retry.
- **Stack IDs.** The dashboard stacks (`stack:qwen3-5-397b-1`,
  `stack:glm-5-2-1`) resolve to the same models as the platform IDs. The
  registry uses the platform IDs so anyone with a key can reproduce runs.
- **glm-5.2** returned a gateway 504 after 60s on every call, through
  both IDs and even on a trivial prompt: an outage on the provider side.
  Retried 2026-11-14: still 504 after 61s with reasoning on or off, by both
  IDs, and with `stream: true` (no first token inside the gateway's 60s),
  while a qwen3.5-397b control call answered in 1.5s. Not run.

Risk: big models tend to answer in a sentence ("The snippet is SUPPORTED
because… not CONTRADICTED"), and the legacy first-match regex can pick
the wrong word. We keep the legacy parser for comparability, store the
raw text for every call, and the evaluation reports the `parse_error`
count. If verbose output turns out to be a problem, the fix is a separate,
named judge with a stricter parser, not a silent change to the existing one.

### 4.4 Backend `ollama_decision`: decision models

These models don't generate text. They take a `state` plus typed questions
and return a probability for each option in one forward pass, via Ollama's
`POST /v1/systemone`:

```json
{"model": "d3:9b",
 "state": "TRANSCRIPT SNIPPET:\n...\n\nCANDIDATE BILL/RESOLUTION TITLE:\n...",
 "questions": {"verdict": {
    "type": "choice",
    "instructions": "Does the transcript snippet's description ... match the candidate title?",
    "criteria": {"supported": "...", "contradicted": "...", "unverifiable": "..."}}}}
```

Response: `answers.verdict.choice`, `answers.verdict.probabilities`
(one per option), and `answers.verdict.confidence`. The criterion texts
are the definitions from the legacy prompts, word for word. `forced` mode
drops the `unverifiable` option.

Candidate models (from ollama.com/search?c=decision, Nov 2026): `d3`
(2b/4b/9b/27b), `nimble` (9b), `pplx-decider` (27b, fine-tuned from
Qwen3.8-27B), `pplx-decider-flash` (4b), `tev1` (4b), `clef` (27b, cloud only).

**Prerequisite:** local Ollama is 0.11.5, which has no `/v1/systemone`.
It needs an upgrade, and each model has to be pulled. `clef:cloud` runs on
ollama.com with an `OLLAMA_API_KEY` instead.

### 4.5 Why decision models change the abstention question

A generative judge abstains only when it *says* "UNVERIFIABLE". A decision
model in `forced` mode returns P(supported) and P(contradicted). That gives
a second way to abstain: **answer only when max(p) ≥ τ**. Sweeping τ gives
a full risk–coverage curve, and τ is a hyperparameter, which is exactly
what the `val` split is for. The evaluation compares the two ways:

- **prompted abstention:** the `abstain` mode, where the model picks `unverifiable`
- **thresholded abstention:** the `forced` mode plus a τ chosen on `val`

τ is chosen on `val` to match the reference judge's `val` coverage, which
by default is legacy qwen2.5:7b abstain. Then error is compared on `test`
at that τ. Matched coverage keeps the comparison fair: any judge can push
its error down by refusing more.

### 4.6 Legacy runs

`03_import_legacy_runs.py` converts the existing
`dc_council/llm_{judge,forced}_results*.json` into the pipeline's run
format, so the three tested models are baselines without re-running them
(the qwen models aren't installed on this machine). Rows are matched to
cases by `(pool, context, title)`, not by position, and the import fails
if any match is missing or ambiguous. The qwen2.5:3b files cover only 120
cases; its metrics are computed on that subset and marked as partial.

## 5. Runs

`04_run_judge.py --judge NAME [--split test] [--limit N]` writes
`results/runs/<judge name with / → __>.jsonl`, one row per case:

```json
{"case_id": "weak-024", "judge": "...", "backend": "...", "model": "...", "mode": "abstain",
 "label": "supported", "probabilities": {"supported": 0.91, ...} | null,
 "raw": "<model text or answer JSON>", "prompt_sha": "ab12...", "latency_s": 0.84,
 "usage": {...} | null, "timestamp": "2026-11-14T17:02:11Z"}
```

- **Resumable.** Cases already in the file are skipped, so a crashed or
  interrupted run picks up where it stopped.
- **Fail loudly.** HTTP errors are retried 3 times with backoff on 429/5xx;
  after that the run stops with the error. It never writes a placeholder
  label or skips a case without saying so. A missing API key is an error
  before the first call.
- **Prompt drift check.** Each row stores a hash of the prompt template
  and criteria. If the file holds rows with a different hash, the run
  refuses to append until you pass `--overwrite`, so results from two
  prompt versions never mix in one file.
- **`label` values.** Only `supported`, `contradicted`, `unverifiable`, or
  `parse_error`. Nothing else is written.

## 6. Evaluation (`05_evaluate.py`)

For every run file × split (`train`, `val`, `test`, `all`, and `stress`
for runs that cover it), using `gold_3way`:

| Metric | Definition | Matches legacy |
|---|---|---|
| `n` | cases in the split that have a result row | - |
| `missing` | cases in the split with no result row (reported, never imputed) | - |
| `coverage` | share of answered cases whose label isn't `unverifiable` | `compare_abstention.score_abstaining` |
| `selective_error` | wrong answers ÷ covered answers (`parse_error` counts as covered and wrong) | same |
| `forced_error` | wrong answers ÷ all answers; unverifiable gold counts as wrong for a 2-way judge | `compare_abstention.score_forced` |
| `accuracy_3way` | label == gold_3way, over all answered cases | - |
| `precision_sup`, `recall_sup` | positive class = `supported`, everything else negative | `compute_benchmark_metrics` |
| `parse_errors` | count | - |
| `selective_error_ci95` | bootstrap, 10,000 resamples, seed 0 | `significance_test.bootstrap_error_rate` |
| `mcnemar_p` vs reference | exact binomial on discordant pairs, over cases both judges cover | `significance_test` |
| `cost_usd` | summed cost of every answered case in the split (see below) | - |
| `cost_per_1k_cases` | `cost_usd` ÷ `n` × 1,000 | - |
| `cost_per_correct_answer` | `cost_usd` ÷ covered answers that match gold (the cost of each committed, correct answer) | - |
| `cost_basis` | where the per-call costs came from: `billed`, `tokens`, `run_average`, `local`, or several joined by `+` | - |

Cost of one call, first rule that applies:

1. **`billed`**: the row's `usage.cost`, when the provider reports it (Adaption).
2. **`local`**: $0 for models marked `local` in `config.PRICES` and for the
   `ollama` / `ollama_decision` backends. Hardware and electricity aren't counted.
3. **`tokens`**: the row's `usage.input_tokens` / `output_tokens` × the model's
   USD-per-1M-token prices in `config.PRICES` (e.g. Claude Haiku 5.5 at batch prices).
4. **`run_average`**: for runs logged before per-call usage existed, the judge's
   `run_total_usage` in `config.JUDGES` × prices, spread evenly over its cases.
   Marked † on the leaderboard (currently only the Jev run).

If any call in a split has no cost by these rules, all four cost fields are
`None` (shown as –), never a partial sum.

For `forced`-mode runs where every row has probabilities (decision
models), also:

- **`aurc`**: area under the risk–coverage curve, where answers are sorted
  by max probability (lower is better)
- **`tau`**: chosen on `val` to match the reference judge's `val` coverage
- **`test_selective_error_at_tau`** and **`test_coverage_at_tau`**

Outputs:

- `results/metrics.json` (everything)
- `results/leaderboard.md` (one table per split, sorted by selective error
  on test, with coverage beside it and $ / 1k cases and $ / correct answer
  at the end of each row)

The McNemar test runs without scipy: `binomtest` on discordant pairs is a
two-sided sum of `math.comb` terms. That's one less dependency, and the
code shows exactly what's computed.

## 7. Layout and style

```
datapipeline/
  SPEC.md                    this document
  README.md                  how to run, in 10 lines
  config.py                  paths, seeds, split ratios, JUDGES registry
  backends.py                ollama / adaption / ollama_decision clients
  metrics.py                 pure metric functions (no I/O)
  01_build_dataset.py        benchmark.jsonl + stress_hard_negatives.jsonl
  02_make_splits.py          splits.json
  03_import_legacy_runs.py   dc_council results -> results/runs/
  04_run_judge.py            run one judge over a split
  05_evaluate.py             metrics.json + leaderboard.md
  data/                      generated (small, committed)
  results/                   generated (small, committed)
```

Style follows `dc_council/`: each script starts with a docstring that says
*why* it exists and how to run it, has constants at the top and small
functions, ends in `main()` behind `if __name__ == "__main__"`, uses plain
JSON in and out, and prints a human-readable summary. The only third-party
dependency is `requests`.

## 8. Out of scope (for now)

- Fine-tuning. With about 40 train cases there's nothing to fine-tune on.
  `train` exists so few-shot prompting can be added later as new judges
  without touching `val` or `test`.
- Re-labeling gold. The pipeline reads `benchmark_gold_labels.py` as the
  source of truth; corrections go there.
- Changing anything in `dc_council/`.

## 9. Acceptance checks

1. `01`: 200 benchmark cases, label counts 95/61/43/1 (matching §2).
2. `02`: every case assigned once, no `clip_id` in more than one split,
   and the printed per-split label counts are close to 20/20/60.
3. `03`: every legacy row maps to exactly one case. Re-scoring legacy
   qwen2.5:7b on `all` reproduces `dc_council/abstention_comparison.json`
   (coverage and error rates).
4. `04`: a real run with `--limit 3` against an available backend writes
   3 rows, and running it again writes 0 new rows.
5. `05`: produces the leaderboard without errors, `missing` is reported
   for partial runs.
