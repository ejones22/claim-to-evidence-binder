"""
Robustness check: does the abstention-value finding hold with a third,
larger/different model? qwen3.5:9b was unusable at first -- it's a
"thinking" model that defaults to ~26-54s/call, which would make 400
calls (200 cases x 2 prompts) take 3+ hours. Ollama's native "think":
false request field suppresses that reasoning pass entirely (confirmed:
same model, same prompt, 26s -> 0.86s), which is what makes this run
feasible at all.

Run from dc-council/dc_etl/:
  python3 run_second_model.py
"""
import json

from llm_judge_baseline import PROMPT_TMPL as ABSTAIN_PROMPT, OLLAMA_URL
from llm_forced_baseline import PROMPT_TMPL as FORCED_PROMPT
import re
import requests

MODEL = "qwen3.5:9b"


def classify(prompt_tmpl, context, title, allowed):
    prompt = prompt_tmpl.format(context=context, title=title)
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False, "think": False,
        "options": {"temperature": 0},
    })
    resp.raise_for_status()
    text = resp.json()["response"].strip().upper()
    pattern = r"\b(" + "|".join(allowed) + r")\b"
    m = re.search(pattern, text)
    return m.group(1).lower() if m else "parse_error"


def main():
    d = json.load(open("benchmark_sample.json"))
    cases = []
    for r in d["supported"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "supported_pool"})
    for r in d["weak"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "weak_pool"})
    for r in d["no_context"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "no_context_pool"})
    for r in d["synthetic_contradicted"]:
        cases.append({"context": r["context"], "title": r["swapped_title"], "pool": "synthetic_contradicted"})

    print(f"{len(cases)} cases x 2 prompts with {MODEL}")
    abstain_results, forced_results = [], []
    for i, c in enumerate(cases):
        a_label = classify(ABSTAIN_PROMPT, c["context"], c["title"],
                            ["SUPPORTED", "CONTRADICTED", "UNVERIFIABLE"])
        f_label = classify(FORCED_PROMPT, c["context"], c["title"],
                            ["SUPPORTED", "CONTRADICTED"])
        abstain_results.append({**c, "llm_label": a_label})
        forced_results.append({**c, "llm_label": f_label})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(cases)}")

    with open("llm_judge_results_qwen3.5-9b.json", "w") as f:
        json.dump(abstain_results, f, indent=2)
    with open("llm_forced_results_qwen3.5-9b.json", "w") as f:
        json.dump(forced_results, f, indent=2)
    print("done")


if __name__ == "__main__":
    main()
