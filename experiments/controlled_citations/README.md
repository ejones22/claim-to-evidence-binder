# Controlled citation support experiment

This experiment asks whether a verifier accepts a correctly identified measure when the available description concerns only procedure or a neighboring measure, and whether requiring an exact evidence span plus attribution reduces false support while retaining genuine support. It is separate from the existing natural benchmark and its reported results.

**Status: setup complete; all human labels and model results are pending. No inference calls have been made by this setup.** The authoring assistant selected sources and wrote constructed contexts; these must not be presented as authentic transcript quotations or independent human annotations.

## What is included

- 30 distinct legislative measures anchored to natural cases at commit `31f4afe58c2d3a18b22fc07339860fb9127f697e`. `sources.json` preserves the original snippet, official-title field, identifier, meeting ID, source-case ID, and pinned repository link.
- 90 constructed examples: substantive target description, procedural mention, and description explicitly attached to a neighboring measure. The target identifier and candidate title remain constant within each source triplet.
- 15 related donor pairs. Each pair supplies the other's neighboring description. Three fixed pairs (6 sources, 18 cases) are development; 12 pairs (24 sources, 72 cases) are test. Paired sources never cross splits. Related categories range from named appointments to utility, housing, and healthcare policy; they are not uniformly difficult.
- Independent Emma/Vivianne TXT and CSV packets, 90 cases each, with different deterministic shuffled orders and opaque review IDs. Each reviewer completes ONE file format.
- The existing baseline prompt copied verbatim from `dc_council/llm_judge_baseline.py`, plus a frozen intervention using the same label definitions and requiring quoted evidence and target attribution.
- An offline review/scoring tool, paired bootstrap analysis, an optional local Ollama runner, and a provider-neutral request export.

## Review first

Distribute only `review/REVIEW_INSTRUCTIONS.md` and that person's TXT or CSV form. Reviewers should not inspect this README's design details, sources, mappings, scripts, prompts, or each other's answers before saving their responses. Public repository access makes blinding procedural, not guaranteed; the forms themselves reveal neither variants nor expected answers. Similar triplets may remain recognizable. Team members may recognize source legislation from prior work; disclose that limitation.

Review both topic mention and substantive content, and supply an explicit independent overall label. There are no prefilled answers and no automatic field-to-label conversion. Do not assume the construction intent is correct. Preserve ambiguous judgments. The scripts do not generate or substitute human labels.

From the repository root, with Python 3.10+ (standard library only):

```bash
python experiments/controlled_citations/build.py --check
python -m unittest discover -s experiments/controlled_citations/tests -v

# Save completed forms under a local directory; CSV and TXT are both accepted.
python experiments/controlled_citations/experiment.py review \
  --emma experiments/controlled_citations/local/emma_completed.txt \
  --vivianne experiments/controlled_citations/local/vivianne_completed.txt \
  --output experiments/controlled_citations/local/review_lock.json
```

The review command requires all 90 cases from both reviewers, checks unchanged input text and unique IDs, reports agreement separately by split, and saves original judgments plus disagreements. It never replaces either review with a consensus decision. The primary reference uses only agreement cases and reports its excluded count; each reviewer's full labels are also scored separately. Agreement is not adjudicated truth. If you adjudicate, preserve the original reviews and extend the protocol explicitly before inference; do not silently edit the lock.

## Freeze and run

Prompts, example bytes, and reviewer orders are hashed in `manifest.json`. Test jobs require the frozen review lock. Development and test remain separate in all output. This is a newly constructed diagnostic from an already explored corpus, not a prospective natural holdout. Choose the model before evaluating test outputs, and use the same model, endpoint, and settings for both conditions.

The Ollama runner uses temperature 0, thinking disabled, and a 1,024-token output limit for both conditions. It sends no credentials and defaults to localhost. Confirm the chosen model supports these options. Do not silently change parameters for one condition.

```bash
# Optional development run: 18 cases x 2 conditions = 36 requests.
python experiments/controlled_citations/experiment.py run \
  --model qwen2.5:7b --split development \
  --review-lock experiments/controlled_citations/local/review_lock.json \
  --output experiments/controlled_citations/local/development_predictions.jsonl

# Frozen test: 72 cases x 2 conditions = 144 requests.
python experiments/controlled_citations/experiment.py run \
  --model qwen2.5:7b --split test \
  --review-lock experiments/controlled_citations/local/review_lock.json \
  --output experiments/controlled_citations/local/test_predictions.jsonl

python experiments/controlled_citations/experiment.py analyze \
  --review-lock experiments/controlled_citations/local/review_lock.json \
  --predictions experiments/controlled_citations/local/test_predictions.jsonl \
  --output experiments/controlled_citations/local/test_analysis.json
```

To export jobs without inference, replace `run` with `prepare` and give a new output path. A hosted-provider adapter can consume the resulting `prompt` field; retain every job metadata field (except optionally the prompt), append `status: "ok"`, `backend`, `endpoint`, and the unmodified text `raw_response`. Record provider settings honestly and implement a separately versioned adapter if the provider cannot reproduce the specified settings. API errors must have `status: "error"`; they cannot be represented as abstention. No adapter for a hosted provider is included.

The runner appends one response at a time, supports resuming an interrupted successful prefix, and stops on request errors. Preserve failed runs and use a separately named rerun; never choose the better of repeated runs. Parsing errors are reported by the analysis and block headline scores. Exact quoted spans are checked, but a bad span does not silently change the model's label. Output filenames under `local/` are ignored to avoid publishing unfinished reviews or accidental test inspection.

## Prespecified analysis

Primary outcomes are false support among reviewer-reference non-supported cases and support retention among reference-supported cases. Report both, with counts and denominators; abstaining on everything is not success. Report outcomes by constructed variant, coverage, selective error, three-way agreement, and exact-span validity. The tool computes all three references: reviewer agreement, Emma, and Vivianne. Treat differences across them as sensitivity, not opportunities to select favorable results.

Differences are intervention minus baseline. A decrease in false support is favorable; a decrease in support retention is a cost. Paired percentile intervals use 20,000 resamples of donor pairs, keeping both sources, all variants, and both conditions together. There are only 12 test clusters. Empty denominators produce null metrics, never zero, and undefined bootstrap draws are counted. No case-independent significance test is applied to the 72 correlated cases. Preselect any substantive success threshold before inspecting model results; the script does not declare an experiment a success from a p-value.

## Interpretation and scope

The neighboring variant explicitly marks a switch to a different measure. It tests failure to bind descriptions to the correct measure; it does not test detection of every possible direct contradiction. Its intended label is not used as scoring gold. Synthetic affirmative descriptions are concise paraphrases grounded in titles and existing snippets, not verified summaries of full legislation. Human review can reject them.

The intervention changes both instructions and output format. Any improvement belongs to that combined intervention; do not attribute it uniquely to span extraction. Model output quoting is only a provenance check, not an entailment guarantee. Context length and syntax differ across variants. Donor-pair resampling addresses shared construction but not every dependency from repeated meetings or subject matter. Findings cannot estimate the prevalence of failure in natural civic discourse or establish superiority across models. A second model can replicate the frozen experiment, with its own complete analysis.

Keep this experiment out of the main paper's results until reviews and inference are complete. Report null or adverse outcomes as well as improvements. Before public release, publish the original human reviews, protocol/version, model settings, raw outputs, and the exact analysis command.

## Changing the protocol

`build.py --check` is read-only; `build.py` regenerates blank forms and frozen assets, so do not run it over completed review files. Those files should always live under `local/`. If development motivates a prompt or dataset revision, copy this experiment to a new version, preserve the original, rebuild its manifest, record the change before test access, and collect fresh reviews for changed examples. Never alter the current frozen artifacts to accommodate observed test results.
