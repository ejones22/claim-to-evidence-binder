"""
Baseline A: does a plain LLM judge, given the same context and candidate
title as the deterministic word-overlap matcher, recover the recall that
matcher loses on paraphrased/synonym/domain-specific matches -- without
giving up its 94.6% precision?

Deliberately blind: this script has no access to benchmark_gold_labels.py
and makes its judgment from the context + title alone, the same inputs
score_citations.py's topic_overlap() sees. Uses qwen2.5:7b via Ollama --
same model this project's summarize.py already uses, for a documented,
reproducible, free-to-rerun baseline.

Run from dc-council/dc_etl/:
  python3 llm_judge_baseline.py
Writes llm_judge_results.json.
"""
import json
import re
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

PROMPT_TMPL = """You are checking whether a snippet of spoken meeting transcript \
actually describes the legislation it names, or just mentions its number.

TRANSCRIPT SNIPPET:
"{context}"

CANDIDATE BILL/RESOLUTION TITLE:
"{title}"

Does the transcript snippet's description of what this bill/resolution is about \
match the candidate title? Answer with exactly one word:
SUPPORTED -- the snippet describes content consistent with this title (even if \
it uses different words, paraphrases, or needs some background knowledge to see).
CONTRADICTED -- the snippet clearly describes something else, not this title.
UNVERIFIABLE -- the snippet gives no real description to check (e.g. it's just \
a procedural vote, a name read aloud, or background about something else).

Answer:"""


def classify(context, title):
    prompt = PROMPT_TMPL.format(context=context, title=title)
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0},
    })
    resp.raise_for_status()
    text = resp.json()["response"].strip().upper()
    m = re.search(r"\b(SUPPORTED|CONTRADICTED|UNVERIFIABLE)\b", text)
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

    print(f"{len(cases)} cases to judge with {MODEL}")
    results = []
    for i, c in enumerate(cases):
        label = classify(c["context"], c["title"])
        results.append({**c, "llm_label": label})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(cases)}")

    with open("llm_judge_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("done, wrote llm_judge_results.json")


if __name__ == "__main__":
    main()
