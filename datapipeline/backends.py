"""
One function per way of asking a model "does this snippet describe this
title?" (SPEC.md section 4). Each takes a judge config + (context, title)
and returns the same dict shape, so 04_run_judge.py doesn't care which
backend it's talking to:

  {"label": "supported" | "contradicted" | "unverifiable" | "parse_error",
   "probabilities": {label: p, ...} or None,
   "raw": <model text, or the decision model's answer JSON>,
   "usage": {...} or None}

Generative backends (ollama, adaption) use the dc_council prompts
verbatim and the same first-match regex parser, so a new model sees the
exact text the legacy models saw. The decision backend asks the same
question in the model's native typed-question schema.

Errors are never swallowed: 429/5xx/connection errors are retried a few
times with backoff, anything else (or running out of retries) raises.
"""
import hashlib
import json
import os
import re
import subprocess
import time

import requests

import config
from llm_judge_baseline import PROMPT_TMPL as ABSTAIN_PROMPT
from llm_forced_baseline import PROMPT_TMPL as FORCED_PROMPT

PROMPTS = {"abstain": ABSTAIN_PROMPT, "forced": FORCED_PROMPT}
ALLOWED = {"abstain": config.LABELS_ABSTAIN, "forced": config.LABELS_FORCED}

# The decision-model question, built from the legacy prompts' own wording.
# Kept as literal strings (rather than parsed out of the template) so
# they're easy to read; the asserts below guarantee they're verbatim.
DECISION_PREAMBLE = ("You are checking whether a snippet of spoken meeting transcript "
                     "actually describes the legislation it names, or just mentions its number.")
DECISION_INSTRUCTIONS = ("Does the transcript snippet's description of what this "
                         "bill/resolution is about match the candidate title?")
DECISION_CRITERIA = {
    "abstain": {
        "supported": "the snippet describes content consistent with this title (even if "
                     "it uses different words, paraphrases, or needs some background knowledge to see).",
        "contradicted": "the snippet clearly describes something else, not this title.",
        "unverifiable": "the snippet gives no real description to check (e.g. it's just "
                        "a procedural vote, a name read aloud, or background about something else).",
    },
    "forced": {
        "supported": "the snippet's content is more consistent with this title than not.",
        "contradicted": "the snippet's content is less consistent with this title than not.",
    },
}
for _mode, _criteria in DECISION_CRITERIA.items():
    assert DECISION_PREAMBLE in PROMPTS[_mode] and DECISION_INSTRUCTIONS in PROMPTS[_mode]
    for _label, _text in _criteria.items():
        assert f"{_label.upper()} -- {_text}" in PROMPTS[_mode], (_mode, _label)

GENERATION_SETTINGS = ("think", "reasoning", "max_output_tokens")

# Local models stay in RAM for 5 minutes after the last request by
# default -- with a 5.6GB model on a 14GB laptop that's enough to take the
# machine down. Each request asks for a short keep-alive (so a killed run
# still frees the model within a minute), and release() unloads it
# explicitly when a run ends.
KEEP_ALIVE = "1m"
LOCAL_BACKENDS = {"ollama", "ollama_decision"}

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
# Adaption's per-user limit answers 429 "retry after 60 seconds" after
# ~20 fast calls; a rate limit isn't a failure, so it gets its own,
# longer allowance and waits as long as the server asks
MAX_RATE_LIMIT_WAITS = 20
DEFAULT_RATE_LIMIT_WAIT_S = 60


def prompt_sha(judge):
    """Hash of everything about the prompt that could change a judgment --
    used to refuse mixing two prompt versions in one results file."""
    if judge["backend"] == "ollama_decision":
        payload = json.dumps(decision_question(judge["mode"]), sort_keys=True)
    else:
        payload = PROMPTS[judge["mode"]]
    # generation settings change judgments too; only hashed when set, so
    # judges without them keep the plain-prompt hash
    settings = {k: judge[k] for k in GENERATION_SETTINGS if k in judge}
    if settings:
        payload += json.dumps(settings, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def parse_label(text, mode):
    """The legacy parser: first allowed label word in the upper-cased text."""
    pattern = r"\b(" + "|".join(l.upper() for l in ALLOWED[mode]) + r")\b"
    m = re.search(pattern, text.strip().upper())
    return m.group(1).lower() if m else "parse_error"


def post_with_retry(url, body, headers=None, timeout=300):
    attempt = rate_limit_waits = 0
    while True:
        attempt += 1
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)
        except requests.ConnectionError:
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429 and rate_limit_waits < MAX_RATE_LIMIT_WAITS:
            rate_limit_waits += 1
            attempt -= 1  # waiting out a rate limit doesn't use up an error retry
            retry_after = resp.headers.get("Retry-After", "")
            wait = int(retry_after) if retry_after.isdigit() else DEFAULT_RATE_LIMIT_WAIT_S
            print(f"    rate limited, waiting {wait}s ({rate_limit_waits}/{MAX_RATE_LIMIT_WAITS})")
            time.sleep(wait)
            continue
        if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
            continue
        if not resp.ok:
            raise RuntimeError(f"{url} -> HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()


def call_ollama(judge, context, title):
    prompt = PROMPTS[judge["mode"]].format(context=context, title=title)
    body = {"model": judge["model"], "prompt": prompt, "stream": False,
            "options": {"temperature": 0}, "keep_alive": KEEP_ALIVE}
    # only sent when the judge asks for it -- the qwen2.5 baselines never
    # sent it, qwen3.5:9b needed it (see dc_council/run_second_model.py)
    if "think" in judge:
        body["think"] = judge["think"]
    out = post_with_retry(f"{config.OLLAMA_URL}/api/generate", body)
    text = out["response"]
    usage = {"input_tokens": out.get("prompt_eval_count"), "output_tokens": out.get("eval_count")}
    return {"label": parse_label(text, judge["mode"]), "probabilities": None,
            "raw": text, "usage": usage}


def call_adaption(judge, context, title):
    key = os.environ.get("ADAPTION_API_KEY")
    if not key:
        raise RuntimeError("ADAPTION_API_KEY is not set")
    prompt = PROMPTS[judge["mode"]].format(context=context, title=title)
    body = {"model": judge["model"], "input": prompt, "temperature": 0,
            "max_output_tokens": judge.get("max_output_tokens", 256), "store": False}
    # reasoning models (qwen3.5-397b) otherwise spend the whole token budget
    # thinking and return no answer text; {"effort": "none"} is the hosted
    # equivalent of the think:false the legacy qwen3.5:9b run used
    if "reasoning" in judge:
        body["reasoning"] = judge["reasoning"]
    out = post_with_retry(config.ADAPTION_URL, body,
                          headers={"Authorization": f"Bearer {key}"})
    text = out.get("output_text") or ""
    if out.get("status") != "completed":
        # keep the row (the parser may still find a label) but make the
        # truncation visible in raw instead of hiding it
        text = f"[status={out.get('status')} {out.get('incomplete_details')}] {text}"
    return {"label": parse_label(text, judge["mode"]), "probabilities": None,
            "raw": text, "usage": out.get("usage")}


def decision_question(mode):
    return {
        "type": "choice",
        "instructions": f"{DECISION_PREAMBLE} {DECISION_INSTRUCTIONS}",
        "criteria": DECISION_CRITERIA[mode],
    }


def decision_state(context, title):
    # same two blocks, same headings, as the generative prompt
    return (f'TRANSCRIPT SNIPPET:\n"{context}"\n\n'
            f'CANDIDATE BILL/RESOLUTION TITLE:\n"{title}"')


def call_ollama_decision(judge, context, title):
    body = {"model": judge["model"], "state": decision_state(context, title),
            "questions": {"verdict": decision_question(judge["mode"])}}
    headers = None
    if judge["model"].endswith(":cloud"):
        key = os.environ.get("OLLAMA_API_KEY")
        if not key:
            raise RuntimeError("OLLAMA_API_KEY is not set (needed for :cloud decision models)")
        headers = {"Authorization": f"Bearer {key}"}
        url = "https://ollama.com/v1/systemone"
    else:
        url = f"{config.OLLAMA_URL}/v1/systemone"
        body["keep_alive"] = KEEP_ALIVE
    out = post_with_retry(url, body, headers=headers)
    answer = out["answers"]["verdict"]
    label = answer.get("choice")
    if label not in ALLOWED[judge["mode"]]:
        label = "parse_error"
    return {"label": label, "probabilities": answer.get("probabilities"),
            "raw": json.dumps(answer), "usage": out.get("usage")}


def release(judge):
    """Unload a local model from RAM now, instead of waiting out keep_alive.
    `ollama stop` works for both generative and decision models."""
    if judge["backend"] not in LOCAL_BACKENDS or judge["model"].endswith(":cloud"):
        return
    host = config.OLLAMA_URL.replace("http://", "").replace("https://", "")
    result = subprocess.run(["ollama", "stop", judge["model"]], env={**os.environ, "OLLAMA_HOST": host},
                            capture_output=True, text=True)
    status = "unloaded" if result.returncode == 0 else f"unload failed: {result.stderr.strip()}"
    print(f"{judge['model']}: {status}")


BACKENDS = {
    "ollama": call_ollama,
    "adaption": call_adaption,
    "ollama_decision": call_ollama_decision,
}
