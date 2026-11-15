"""
Baseline C: the same 3-way judgment as llm_judge_baseline.py, made by
TypeSafe AI's Jev (a hosted "System One" decision model that returns
calibrated-by-claim probabilities instead of generated text) rather than
a local Ollama LLM.

Same inputs as the Ollama judge -- context snippet + candidate title, no
topic_overlap score -- so the two are directly comparable. Jev has no
abstain mode of its own; "unverifiable" is just one of the three options,
and the full probability map is kept so thresholds on P(supported) can be
chosen later by cross-validation instead of by hand.

Needs a `Jev=` key in ../.env. The key is from jevmodel.org, an
independent reseller (not operated by TypeSafe AI) that forwards requests
to TypeSafe; the official api.typesafe.ai endpoint rejects it.

Run from dc_council/:
  python3 jev_judge.py           # all 200 benchmark cases
  python3 jev_judge.py --one     # single test call, nothing written
  python3 jev_judge.py --resume  # continue a partial jev_judge_results.json
Writes jev_judge_results.json (same shape as llm_judge_results.json, plus
jev_probabilities / jev_confidence).
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, "..", ".env")
JEV_URL = "https://jevmodel.org/v1/systemone"
MODEL = "jev-1.13.0"  # pinned rather than jev-latest, for reproducibility

INSTRUCTIONS = (
    "The state is a snippet of spoken meeting transcript and the official title "
    "of the bill/resolution it names. Does the snippet's description of what this "
    "bill/resolution is about match the title, or does it just mention its number?"
)
CRITERIA = {
    "supported": "The snippet describes content consistent with this title, even if "
                 "it uses different words, paraphrases, or needs some background "
                 "knowledge to see.",
    "contradicted": "The snippet clearly describes something else, not this title.",
    "unverifiable": "The snippet gives no real description to check (e.g. it's just a "
                    "procedural vote, a name read aloud, or background about something else).",
}


def load_key():
    """Read the Jev API key from ../.env (a `Jev=...` line); exit if missing."""
    with open(ENV_PATH) as f:
        for line in f:
            name, _, value = line.strip().partition("=")
            if name == "Jev":
                return value.strip().strip('"').strip("'")
    raise SystemExit("no Jev= key in ../.env")


def classify(session, context, title):
    """
    Ask Jev one question: does this snippet match this title? Returns
    (answer, usage), where answer holds the chosen label plus its
    probability map and confidence. Retries up to 4 times with
    exponential backoff on 429/5xx; other HTTP errors are raised.
    """
    body = {
        "model": MODEL,
        "state": {"transcript_snippet": context, "candidate_title": title},
        "questions": {"binding": {"type": "choice", "instructions": INSTRUCTIONS,
                                  "criteria": CRITERIA}},
    }
    for attempt in range(4):
        resp = session.post(JEV_URL, json=body, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        data = resp.json()
        answer = data["answers"]["binding"]
        return answer, data.get("usage", {})
    resp.raise_for_status()


def build_cases():
    """
    Flatten benchmark_sample.json into the 200 judge cases: a list of
    {context, title, pool}. Contradicted cases use the swapped title.
    Also imported by claude_batch_judge.py, so all judges see the same cases.
    """
    # identical case order to llm_judge_baseline.py, so compare_abstention's
    # attach_gold() lines up
    d = json.load(open(os.path.join(HERE, "benchmark_sample.json")))
    cases = []
    for r in d["supported"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "supported_pool"})
    for r in d["weak"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "weak_pool"})
    for r in d["no_context"]:
        cases.append({"context": r["context"], "title": r["official_title"], "pool": "no_context_pool"})
    for r in d["synthetic_contradicted"]:
        cases.append({"context": r["context"], "title": r["swapped_title"], "pool": "synthetic_contradicted"})
    return cases


def main():
    """
    Judge every case sequentially (or one test call with --one, or continue
    a partial run with --resume) and write jev_judge_results.json plus
    latency / input-token totals. Per-call usage is stored in each result.
    """
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {load_key()}"
    cases = build_cases()

    if "--one" in sys.argv:
        t0 = time.time()
        answer, usage = classify(session, cases[0]["context"], cases[0]["title"])
        print(f"{time.time() - t0:.2f}s  {json.dumps(answer)}  usage={usage}")
        return

    results, latencies, tokens = [], [], 0
    out_path = os.path.join(HERE, "jev_judge_results.json")
    # --resume: keep an earlier partial run (e.g. one cut off by running out
    # of tokens) and only judge the cases after it
    if "--resume" in sys.argv and os.path.exists(out_path):
        results = json.load(open(out_path))
    print(f"{len(cases) - len(results)} cases to judge with {MODEL}")
    for i, c in enumerate(cases):
        if i < len(results):
            continue
        t0 = time.time()
        try:
            answer, usage = classify(session, c["context"], c["title"])
        except requests.HTTPError as e:
            # e.g. token allowance used up -- keep what we have rather than
            # losing the whole run
            print(f"  stopped at case {i}: {e.response.status_code} {e.response.text[:200]}")
            break
        latencies.append(time.time() - t0)
        tokens += usage.get("input_tokens", 0)
        results.append({**c, "llm_label": answer["choice"],
                        "jev_probabilities": answer.get("probabilities"),
                        "jev_confidence": answer.get("confidence"),
                        "usage": usage})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(cases)}")

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    latencies.sort()
    print(f"done, wrote jev_judge_results.json")
    print(f"latency p50={latencies[len(latencies) // 2]:.2f}s  "
          f"p95={latencies[int(len(latencies) * 0.95)]:.2f}s  input_tokens={tokens}")


if __name__ == "__main__":
    main()
