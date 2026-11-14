# datapipeline: judge evaluation

Compares citation judges (local Ollama, Adaption-hosted large models,
Ollama decision models) on the dc_council benchmark with a meeting-grouped
train/val/test split. Design and metric definitions: [SPEC.md](SPEC.md).

```
python3 01_build_dataset.py        # data/benchmark.jsonl, data/stress_hard_negatives.jsonl
python3 02_make_splits.py          # data/splits.json (train 41 / val 40 / test 119, grouped by meeting)
python3 03_import_legacy_runs.py   # dc_council's qwen runs -> results/runs/
python3 04_run_judge.py --list     # see runnable judges
python3 04_run_judge.py --judge adaption/deepseek-v4-flash/abstain   # needs ADAPTION_API_KEY
python3 04_run_judge.py --judge decision/d3:9b/forced                # needs Ollama with /v1/systemone + `ollama pull d3:9b`
python3 05_evaluate.py             # results/metrics.json, results/leaderboard.md
```

Steps 01-03 and 05 are deterministic and quick. Step 04 is resumable: rerun it after a crash and it continues.
Only dependency: `requests`. Quote **test**-split numbers, never tune on test.
