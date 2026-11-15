"""
Shared settings for the judge-evaluation pipeline (see SPEC.md): where
files live, the split seed/ratios, and the JUDGES registry -- the one
place a new model gets added.

Adding a judge = adding one entry to JUDGES. Keys are the judge's name
(also its results filename, with "/" -> "__"); values say which backend
to call, which model, and which task mode:
  mode "abstain" -> 3-way: supported / contradicted / unverifiable
  mode "forced"  -> 2-way: supported / contradicted
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DC_COUNCIL_DIR = os.path.join(REPO, "dc_council")

# API keys live in the repo-root .env (git-ignored). Real environment
# variables win over the file. The file names the Adaption key
# "Adaption_key"; backends.py reads the documented ADAPTION_API_KEY.
ENV_PATH = os.path.join(REPO, ".env")
if os.path.exists(ENV_PATH):
    for line in open(ENV_PATH):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
if "Adaption_key" in os.environ:
    os.environ.setdefault("ADAPTION_API_KEY", os.environ["Adaption_key"])

# dc_council/ is the source of truth for the benchmark, gold labels and
# prompts -- import it rather than copy it, so the two can't drift apart
sys.path.insert(0, DC_COUNCIL_DIR)

DATA_DIR = os.path.join(HERE, "data")
RESULTS_DIR = os.path.join(HERE, "results")
RUNS_DIR = os.path.join(RESULTS_DIR, "runs")

BENCHMARK_SAMPLE_PATH = os.path.join(DC_COUNCIL_DIR, "benchmark_sample.json")
CITATIONS_SCORED_PATH = os.path.join(DC_COUNCIL_DIR, "citations_scored.jsonl")

BENCHMARK_PATH = os.path.join(DATA_DIR, "benchmark.jsonl")
STRESS_PATH = os.path.join(DATA_DIR, "stress_hard_negatives.jsonl")
SPLITS_PATH = os.path.join(DATA_DIR, "splits.json")
METRICS_PATH = os.path.join(RESULTS_DIR, "metrics.json")
LEADERBOARD_PATH = os.path.join(RESULTS_DIR, "leaderboard.md")

# pool name in benchmark_sample.json -> short pool name used in case_ids
POOLS = {
    "supported": "supported",
    "weak": "weak",
    "no_context": "no_context",
    "synthetic_contradicted": "synthetic_contradicted",
}

SPLIT_SEED = 2026
SPLIT_RATIOS = {"train": 0.2, "val": 0.2, "test": 0.6}

STRESS_SEED = 2026
STRESS_N = 100  # same-category hard negatives to build (0 = skip)

LABELS_ABSTAIN = ["supported", "contradicted", "unverifiable"]
LABELS_FORCED = ["supported", "contradicted"]

# the judge every other judge is compared against (McNemar, matched
# coverage for thresholded abstention) -- the legacy headline setup
REFERENCE_JUDGE = "legacy/qwen2.5:7b/abstain"

BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 0

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
ADAPTION_URL = "https://api.prod.adaptionlabs.ai/api/v1/responses"

JUDGES = {
    # --- legacy runs, imported from dc_council/ by 03_import_legacy_runs.py
    # (not re-run: the qwen models aren't installed on this machine) ---
    "legacy/qwen2.5:7b/abstain": {"backend": "legacy", "model": "qwen2.5:7b", "mode": "abstain",
                                  "file": "llm_judge_results.json"},
    "legacy/qwen2.5:7b/forced": {"backend": "legacy", "model": "qwen2.5:7b", "mode": "forced",
                                 "file": "llm_forced_results.json"},
    "legacy/qwen2.5:3b/abstain": {"backend": "legacy", "model": "qwen2.5:3b", "mode": "abstain",
                                  "file": "llm_judge_results_qwen2.5-3b.json"},
    "legacy/qwen2.5:3b/forced": {"backend": "legacy", "model": "qwen2.5:3b", "mode": "forced",
                                 "file": "llm_forced_results_qwen2.5-3b.json"},
    "legacy/qwen3.5:9b/abstain": {"backend": "legacy", "model": "qwen3.5:9b", "mode": "abstain",
                                  "file": "llm_judge_results_qwen3.5-9b.json"},
    "legacy/qwen3.5:9b/forced": {"backend": "legacy", "model": "qwen3.5:9b", "mode": "forced",
                                 "file": "llm_forced_results_qwen3.5-9b.json"},
    # hosted judges run from dc_council/ (jev_judge.py via the jevmodel.org
    # reseller, claude_batch_judge.py via Anthropic's Message Batches API),
    # imported the same way as the legacy runs
    # the Jev run predates per-case usage logging; its exact total (from the
    # run's own output: 99,028 tokens for cases 0-184 + 8,108 for 185-199)
    # is spread evenly over its cases for cost reporting
    "jev/jev-1.13.0/abstain": {"backend": "legacy", "model": "jev-1.13.0", "mode": "abstain",
                               "file": "jev_judge_results.json",
                               "run_total_usage": {"input_tokens": 107136, "output_tokens": 0, "cases": 200}},
    # the Claude runs have per-case usage in their results files, so their
    # cost comes from tokens x PRICES (batch prices), not a run average
    "anthropic/claude-haiku-5-5/abstain": {"backend": "legacy", "model": "claude-haiku-5-5", "mode": "abstain",
                                           "file": "claude_haiku_judge_results.json"},
    "anthropic/claude-sonnet-5-5/abstain": {"backend": "legacy", "model": "claude-sonnet-5-5", "mode": "abstain",
                                            "file": "claude_sonnet_judge_results.json"},

    # --- local Ollama, generative (same call as the legacy scripts) ---
    "ollama/qwen2.5:7b/abstain": {"backend": "ollama", "model": "qwen2.5:7b", "mode": "abstain"},
    "ollama/qwen2.5:7b/forced": {"backend": "ollama", "model": "qwen2.5:7b", "mode": "forced"},
    "ollama/mistral:7b/abstain": {"backend": "ollama", "model": "mistral:7b", "mode": "abstain"},

    # --- Adaption Labs hosted models (hackathon credits) ---
    # reasoning off: with it on, qwen3.5-397b spent >4096 tokens (44s,
    # ~$0.014) on one label and still returned no answer. Platform model
    # IDs are used; the stacks set up in the dashboard (stack:qwen3-5-397b-1,
    # stack:glm-5-2-1) resolve to the same models.
    "adaption/qwen3.5-397b/abstain": {"backend": "adaption", "model": "qwen3.5-397b", "mode": "abstain",
                                      "reasoning": {"effort": "none"}},
    "adaption/qwen3.5-397b/forced": {"backend": "adaption", "model": "qwen3.5-397b", "mode": "forced",
                                     "reasoning": {"effort": "none"}},
    "adaption/deepseek-v4-flash/abstain": {"backend": "adaption", "model": "deepseek-v4-flash", "mode": "abstain",
                                           "reasoning": {"effort": "none"}},
    "adaption/deepseek-v4-flash/forced": {"backend": "adaption", "model": "deepseek-v4-flash", "mode": "forced",
                                          "reasoning": {"effort": "none"}},
    "adaption/glm-5.2/abstain": {"backend": "adaption", "model": "glm-5.2", "mode": "abstain",
                                 "reasoning": {"effort": "none"}},
    "adaption/glm-5.2/forced": {"backend": "adaption", "model": "glm-5.2", "mode": "forced",
                                "reasoning": {"effort": "none"}},

    # --- Ollama decision models (/v1/systemone, needs a recent Ollama) ---
    # forced-mode runs return P(supported)/P(contradicted), which is what
    # makes thresholded abstention (SPEC.md 4.5) possible
    # d3:9b is a 10GB download / ~10GB RAM -- too big for a 14GB laptop
    # with no GPU; d3:4b and pplx-decider-flash (5.6GB each) are the
    # laptop-sized options
    # pplx-decider-flash only ships MLX builds (Apple silicon): on this
    # Linux laptop `ollama pull` fails with "requires MLX support". The
    # q8_0 tags below are regular builds that run on a Linux CPU.
    "decision/d3:4b-q8_0/abstain": {"backend": "ollama_decision", "model": "d3:4b-q8_0", "mode": "abstain"},
    "decision/d3:4b-q8_0/forced": {"backend": "ollama_decision", "model": "d3:4b-q8_0", "mode": "forced"},
    "decision/d3:2b-q8_0/abstain": {"backend": "ollama_decision", "model": "d3:2b-q8_0", "mode": "abstain"},
    "decision/d3:2b-q8_0/forced": {"backend": "ollama_decision", "model": "d3:2b-q8_0", "mode": "forced"},
    "decision/d3:4b/abstain": {"backend": "ollama_decision", "model": "d3:4b", "mode": "abstain"},
    "decision/d3:4b/forced": {"backend": "ollama_decision", "model": "d3:4b", "mode": "forced"},
    "decision/pplx-decider-flash/abstain": {"backend": "ollama_decision", "model": "pplx-decider-flash",
                                            "mode": "abstain"},
    "decision/d3:9b/abstain": {"backend": "ollama_decision", "model": "d3:9b", "mode": "abstain"},
    "decision/d3:9b/forced": {"backend": "ollama_decision", "model": "d3:9b", "mode": "forced"},
    "decision/nimble/abstain": {"backend": "ollama_decision", "model": "nimble", "mode": "abstain"},
    "decision/nimble/forced": {"backend": "ollama_decision", "model": "nimble", "mode": "forced"},
    "decision/pplx-decider/abstain": {"backend": "ollama_decision", "model": "pplx-decider", "mode": "abstain"},
    "decision/pplx-decider/forced": {"backend": "ollama_decision", "model": "pplx-decider", "mode": "forced"},
    "decision/pplx-decider-flash/forced": {"backend": "ollama_decision", "model": "pplx-decider-flash",
                                           "mode": "forced"},
    "decision/tev1:4b/forced": {"backend": "ollama_decision", "model": "tev1:4b", "mode": "forced"},
}


# USD per 1M tokens, for cost per task in 05_evaluate.py. A row's own
# billed cost (Adaption returns usage.cost) wins over this table. Local
# models are $0: hardware and electricity aren't counted.
# Keyed by judge "model". {"local": True} marks a free local model;
# otherwise "input" / "output" are USD per 1M tokens.
PRICES = {
    "claude-haiku-5-5": {"input": 0.05, "output": 0.25},  # Message Batches (50% of $0.10/$0.50)
    "claude-sonnet-5-5": {"input": 1.00, "output": 5.00},  # Message Batches (50% of $2/$10)
    "jev-1.13.0": {"input": 0.66, "output": 0.0},  # jevmodel.org token pack; output free
    "qwen2.5:7b": {"local": True},
    "qwen2.5:3b": {"local": True},
    "qwen3.5:9b": {"local": True},
}
# backends that run on the user's machine: a model with no PRICES entry on
# one of these is costed at $0 instead of "unknown"
LOCAL_BACKENDS = {"ollama", "ollama_decision"}


def run_path(judge_name):
    return os.path.join(RUNS_DIR, judge_name.replace("/", "__") + ".jsonl")
