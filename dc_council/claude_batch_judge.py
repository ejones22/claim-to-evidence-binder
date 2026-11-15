"""
Baseline D: the same 3-way judgment as llm_judge_baseline.py, made by
Claude Haiku 5.5 (default) or Claude Sonnet 5.5 (--model sonnet) through
Anthropic's Message Batches API (asynchronous, half price). Uses the exact same prompt (imported from
llm_judge_baseline.py) and the same 200 benchmark cases in the same order,
so compare_abstention's attach_gold() lines up.

Needs a `Claude=` key in ../.env.

Run from dc_council/:
  python3 claude_batch_judge.py --submit    # sends one batch, saves its id
  python3 claude_batch_judge.py --collect   # waits for it to end, writes results
  python3 claude_batch_judge.py --submit --model sonnet   # same, Sonnet 5.5
Writes claude_batch_id.txt and claude_haiku_judge_results.json (Sonnet:
claude_sonnet_batch_id.txt, claude_sonnet_judge_results.json), same shape
as llm_judge_results.json.
"""
import json
import os
import re
import sys
import time

import anthropic

from jev_judge import build_cases
from llm_judge_baseline import PROMPT_TMPL

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, "..", ".env")
# --model name -> (model id, batch id file, results file); haiku is the default
MODELS = {
    "haiku": ("claude-haiku-5-5", "claude_batch_id.txt", "claude_haiku_judge_results.json"),
    "sonnet": ("claude-sonnet-5-5", "claude_sonnet_batch_id.txt", "claude_sonnet_judge_results.json"),
}
choice = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "haiku"
MODEL, _batch_file, RESULTS_FILE = MODELS[choice]
BATCH_ID_PATH = os.path.join(HERE, _batch_file)


def load_key():
    """Read the Anthropic API key from ../.env (a `Claude=...` line); exit if missing."""
    with open(ENV_PATH) as f:
        for line in f:
            name, _, value = line.strip().partition("=")
            if name == "Claude":
                return value.strip().strip('"').strip("'")
    raise SystemExit("no Claude= key in ../.env")


def submit(client, cases):
    """
    Send all cases as one batch and save its id to BATCH_ID_PATH for
    --collect. custom_id is the case's position ("case-000"...), which is
    how collect() maps results back to cases.
    """
    requests = [{
        "custom_id": f"case-{i:03d}",
        "params": {
            "model": MODEL,
            "max_tokens": 2000,  # room for adaptive thinking before the one-word answer
            "output_config": {"effort": "low"},
            "messages": [{"role": "user", "content": PROMPT_TMPL.format(
                context=c["context"], title=c["title"])}],
        },
    } for i, c in enumerate(cases)]
    batch = client.messages.batches.create(requests=requests)
    with open(BATCH_ID_PATH, "w") as f:
        f.write(batch.id)
    print(f"submitted {len(requests)} requests as batch {batch.id} ({batch.processing_status})")


def parse_label(message):
    """
    Pull the label out of a reply: the first SUPPORTED / CONTRADICTED /
    UNVERIFIABLE word in its text block (thinking blocks are skipped).
    Returns "refusal" if the model refused, "parse_error" if no label found.
    """
    if message.stop_reason == "refusal":
        return "refusal"
    text = next((b.text for b in message.content if b.type == "text"), "").upper()
    m = re.search(r"\b(SUPPORTED|CONTRADICTED|UNVERIFIABLE)\b", text)
    return m.group(1).lower() if m else "parse_error"


def collect(client, cases):
    """
    Poll (every 30s) until the saved batch has ended, then write
    RESULTS_FILE in the same shape as llm_judge_results.json plus per-case
    token usage. Cases without a successful result get a non-label such as
    "batch_errored" or "missing", counted as unusable in the printout.
    """
    batch_id = open(BATCH_ID_PATH).read().strip()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        print(f"  {batch.processing_status}: {batch.request_counts.processing} still processing")
        time.sleep(30)
    counts = batch.request_counts
    print(f"batch ended: succeeded={counts.succeeded} errored={counts.errored} "
          f"expired={counts.expired} canceled={counts.canceled}")

    # results arrive in any order -- key by custom_id, never by position
    labels, usage, in_tok, out_tok = {}, {}, 0, 0
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            msg = result.result.message
            labels[result.custom_id] = parse_label(msg)
            usage[result.custom_id] = {"input_tokens": msg.usage.input_tokens,
                                       "output_tokens": msg.usage.output_tokens}
            in_tok += msg.usage.input_tokens
            out_tok += msg.usage.output_tokens
        else:
            labels[result.custom_id] = f"batch_{result.result.type}"

    # per-case usage is kept so datapipeline/ can report cost per task
    results = [{**c, "llm_label": labels.get(f"case-{i:03d}", "missing"),
                "usage": usage.get(f"case-{i:03d}")}
               for i, c in enumerate(cases)]
    with open(os.path.join(HERE, RESULTS_FILE), "w") as f:
        json.dump(results, f, indent=2)
    bad = sum(1 for r in results if r["llm_label"] not in ("supported", "contradicted", "unverifiable"))
    print(f"wrote {RESULTS_FILE} ({bad} unusable labels)")
    print(f"tokens: input={in_tok} output={out_tok}")


def main():
    """Dispatch --submit or --collect; the model comes from --model at import time."""
    client = anthropic.Anthropic(api_key=load_key())
    cases = build_cases()
    if "--submit" in sys.argv:
        submit(client, cases)
    elif "--collect" in sys.argv:
        collect(client, cases)
    else:
        raise SystemExit("use --submit or --collect")


if __name__ == "__main__":
    main()
