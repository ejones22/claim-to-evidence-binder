"""
The real comparison the project needs, not just "does an LLM beat a
regex": does letting the verifier ABSTAIN actually buy a lower error rate,
or is three-way judgment (llm_judge_baseline.py) just as error-prone as a
naive judge that's forced to always commit to an answer?

Same model, same prompt inputs, same 120 cases as llm_judge_baseline.py --
the only difference is this one has no UNVERIFIABLE option. If forcing a
commitment doesn't hurt accuracy, abstention isn't earning its keep; if it
does, that's the headline number for "coverage vs. reliability."

Run from dc-council/dc_etl/:
  python3 llm_forced_baseline.py
Writes llm_forced_results.json.
"""
import json
import re

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
match the candidate title? You must pick one, even if you are not fully certain \
-- give your best judgment. Answer with exactly one word:
SUPPORTED -- the snippet's content is more consistent with this title than not.
CONTRADICTED -- the snippet's content is less consistent with this title than not.

Answer:"""


def classify(context, title):
    prompt = PROMPT_TMPL.format(context=context, title=title)
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0},
    })
    resp.raise_for_status()
    text = resp.json()["response"].strip().upper()
    m = re.search(r"\b(SUPPORTED|CONTRADICTED)\b", text)
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

    print(f"{len(cases)} cases to judge with {MODEL} (forced, no abstain)")
    results = []
    for i, c in enumerate(cases):
        label = classify(c["context"], c["title"])
        results.append({**c, "llm_label": label})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(cases)}")

    with open("llm_forced_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("done, wrote llm_forced_results.json")


if __name__ == "__main__":
    main()
