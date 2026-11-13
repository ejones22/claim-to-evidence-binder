"""
Pull DC Council's official Granicus captions and turn them into a speaker-
attributed transcript -- no Whisper, no diarization model, no GPU/CPU time.

Why this exists: while prototyping speaker diarization for the NOLA project
(nocouncil-etl), the open question was always "how do you turn 'Speaker 1 /
Speaker 2' into real councilmember names." DC Council's Granicus captions
turn out to already answer that: they're produced by a live human
stenographer (CART), not auto-captioning, and the captioner writes speaker
changes inline, e.g.:

    >> COUNCILMEMBER PARKER.
    >> I WANT TO SAY IT AGAIN FOR THE RECORD...

Confirmed live against https://dc.granicus.com/TranscriptViewer.php
(view_id=3, clip_id=10801, the 7/14/26 Legislative Meeting) -- each caption
line is one `<div class="caption">` in cue order, no per-line timestamps in
this rendered view (see CAVEATS below).

Parsing heuristic (NOT 100% reliable -- validate against real transcripts
before trusting this for production attribution):
  - Every caption cue that starts with ">>" marks a new "turn" boundary.
  - A cue is treated as a SPEAKER LABEL (not spoken content) if, after
    stripping ">>", it is short and matches a title+name pattern
    (COUNCILMEMBER/CHAIRMAN/CHAIRWOMAN/SECRETARY/CLERK + a name), optionally
    cross-checked against the real roster from LIMS (see label_known()).
  - The most recent label becomes `current_speaker` for subsequent turns
    until the next label cue appears.
  - Ambiguous cases (e.g. one member addressing another by title, like
    ">> MR. CHAIRMAN.") can be misread as a label. This needs empirical
    tuning against a sample of real meetings -- start there before relying
    on this for anything customer-facing.

CAVEATS:
  - This rendered TranscriptViewer page has no visible per-line timestamps,
    so this alone gives you a searchable, speaker-attributed *document*, not
    a time-aligned transcript you can seek video to. If/when precise timing
    matters (e.g. "jump to this moment in the video"), check whether
    Granicus exposes a raw timed caption file (.vtt/.srt) elsewhere, or fall
    back to aligning this text against transcribe_whisperx.py's word-level
    output for that specific clip.
  - Not every meeting will have captions (older archives especially). Treat
    fetch_captions() returning None as "fall back to transcribe_whisperx.py"
    in the pipeline, not as an error.
"""
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BOX_PATH = os.getenv("BOX_PATH", "./data/videos/")
DATA_PATH = os.getenv("DATA_PATH", "./data/lims/")

LABEL_RE = re.compile(
    r"^(COUNCILMEMBER|CHAIRMAN|CHAIRWOMAN|MADAM CHAIR|MR\.?\s*CHAIRMAN|"
    r"SECRETARY|CLERK|GENERAL COUNSEL)\s+[A-Z][A-Z'\-]*(\s+[A-Z][A-Z'\-]*)?\.?$"
)


def dedupe_caption_text(raw_text, max_overlap=15, min_overlap=1):
    """Collapses Granicus's live-caption sliding window back into the real
    sentence stream.

    The CART captioner's display is a rolling window of recent words: it
    grows by one word at a time, then once it hits some width it shifts
    (drops the oldest word, appends the newest). Granicus's TranscriptViewer
    logs every one of those intermediate window states as its own text run
    with no boundary markers between them, so naively concatenating
    `<div class="caption">` text reproduces each sentence many times over,
    each copy one word longer or shifted from the last -- e.g. "THE LANGUAGE
    OF THIS EMERGENCY IS IDENTICAL TO THE LANGUAGE OF THIS EMERGENCY IS
    IDENTICAL TO B26-233 THE LANGUAGE OF THIS EMERGENCY IS IDENTICAL TO
    B26-233 WHICH IS IDENTICAL TO B26-233 WHICH PASSED..." for what was
    actually just "THE LANGUAGE OF THIS EMERGENCY IS IDENTICAL TO B26-233
    WHICH PASSED...". Confirmed by fetching the live TranscriptViewer page
    directly and comparing: 302/302 meetings have at least one affected
    turn, 8.9% of turns overall (view_id=3, clip_id=10152 was ~89% repeated
    text before this fix).

    Fix: walk the token stream and greedily skip any run that exactly
    repeats the tail of what's already been emitted -- that's the window
    re-displaying words it already showed, not new content. A run has to
    overlap by at least `min_overlap` words to count as a repeat (1 is
    enough in practice; raising it leaves shorter window-shifts
    uncollapsed, e.g. "LIKE WHITE OUT. OUT. OUT. THESE" instead of "LIKE
    WHITE OUT. THESE"). `max_overlap` bounds how far back to check, matched
    to the widest window actually observed (comfortably under 15 words)."""
    tokens = raw_text.split()
    output = []
    i, n = 0, len(tokens)
    while i < n:
        limit = min(max_overlap, len(output), n - i)
        best_k = 0
        for k in range(limit, min_overlap - 1, -1):
            if tokens[i:i + k] == output[-k:]:
                best_k = k
                break
        if best_k > 0:
            i += best_k
        else:
            output.append(tokens[i])
            i += 1
    return " ".join(output)


def fetch_raw_captions(captions_url):
    """Returns ordered list of caption cue strings, or None if this clip has
    no captions (Granicus renders an ~empty page rather than a 404).

    IMPORTANT: a single `<div class="caption">` is a *display line* from the
    captioning system, not a speaker turn -- it can contain more than one
    ">>" marker, and a single marker's text can be wrapped across multiple
    divs (confirmed empirically: e.g. one div ends "...I WANT TO SAY IT AGAIN
    FOR" and the next div continues "THE RECORD..." with no marker of its
    own). It can also contain many overlapping sliding-window repeats of the
    same sentence -- see dedupe_caption_text() -- collapsed here before any
    cue splitting happens, since the window-shift pattern isn't aligned to
    div boundaries. So this returns cues split on ">>" across the *whole*
    joined, deduplicated text, not one cue per div -- see split_cues()."""
    resp = requests.get(captions_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    lines = [d.get_text(" ", strip=True) for d in soup.find_all("div", class_="caption")]
    lines = [l for l in lines if l]
    if not lines:
        return None
    full_text = dedupe_caption_text(" ".join(lines))
    return split_cues(full_text)


def split_cues(full_text):
    """Split a joined caption text stream into cues at each '>>' marker
    (kept on the following segment), collapsing whitespace."""
    parts = re.split(r"(?=>>)", full_text)
    cues = [re.sub(r"\s+", " ", p).strip() for p in parts]
    return [c for c in cues if c]


def _strip_marker(cue):
    return re.sub(r"^>>\s*", "", cue).strip()


def label_known(text, known_last_names=None):
    """text: cue content already stripped of '>>'. known_last_names: optional
    set of real councilmember last names (from lims_client.members()) to
    cross-check against, cutting down false positives from generic titles
    like 'MADAM CHAIR' with no attached name."""
    if not LABEL_RE.match(text):
        return False
    if known_last_names is None:
        return True
    text_upper = text.upper()
    return any(name.upper() in text_upper for name in known_last_names)


def parse_turns(cues, known_last_names=None):
    """Returns list of {"speaker": str|None, "text": str} turns, in order.

    A label is applied ONE-SHOT to only the very next turn, then reverts to
    None (unknown) rather than persisting until the next label. Empirically
    (see module docstring), DC's captioner does not reliably re-label every
    speaker change -- long unlabeled stretches are common, and multiple
    different people can speak between labels. Persisting a label across
    those stretches produces *confident, wrong* attribution (e.g. crediting
    a quote to the last-named person when it was actually someone else
    speaking) -- for a government-accountability product that's a much worse
    failure mode than just leaving `speaker` as None and under-attributing.
    Tighten this once validated against a real sample of meetings; a
    promising next step is cross-referencing with word-level diarization
    output from transcribe_whisperx.py to detect voice changes between
    labels, rather than assuming text alone tells you when the speaker
    changed.
    """
    turns = []
    pending_label = None       # a label seen but not yet attached to a turn
    turn_speaker = None        # speaker attached to the turn being built
    current_text = []

    def flush():
        if current_text:
            turns.append({"speaker": turn_speaker, "text": " ".join(current_text).strip()})

    for cue in cues:
        is_new_cue = cue.startswith(">>")
        content = _strip_marker(cue) if is_new_cue else cue

        if is_new_cue and label_known(content, known_last_names):
            pending_label = content.rstrip(".")
            continue  # label cues aren't spoken content themselves

        if is_new_cue:
            flush()
            current_text = [content]
            turn_speaker = pending_label  # one-shot: consume, then clear
            pending_label = None
        else:
            current_text.append(content)

    flush()
    return turns


def fetch_and_parse(captions_url, known_last_names=None):
    cues = fetch_raw_captions(captions_url)
    if cues is None:
        return None
    return parse_turns(cues, known_last_names)


def _duration_to_seconds(duration_str):
    """Parses data.jsonl's "01h 20m" style duration strings (scrape_granicus.py's
    `td.listItem` text) into seconds. Returns None if unparseable."""
    if not duration_str:
        return None
    m = re.match(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", duration_str.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    hours = int(m.group(1)) if m.group(1) else 0
    minutes = int(m.group(2)) if m.group(2) else 0
    return hours * 3600 + minutes * 60


def _load_known_last_names():
    """dc_names.json is build_correction_dicts.py's output -- real current
    councilmember surnames from LIMS, used here purely to sharpen
    label_known()'s precision (see that function's docstring). Returns None
    (no cross-check) if it hasn't been generated yet, rather than failing."""
    names_path = os.path.join(DATA_PATH, "dc_names.json")
    if not os.path.exists(names_path):
        return None
    with open(names_path) as f:
        return set(json.load(f).get("last_names", []))


def build_transcripts(box_path=None):
    """Driver: for every meeting scrape_granicus.py has recorded in
    data.jsonl, fetch + parse its real captions and write one
    `{clip_id}.turns.json` file -- the missing link vectorize.py has always
    been waiting for (see that module's "no *.turns.json files found"
    message). Meetings with no captions are skipped and counted, not
    silently dropped -- they need the WhisperX fallback, out of scope here
    (not installed in this environment). Idempotent: re-running skips any
    clip_id that already has a .turns.json on disk."""
    box_path = box_path or BOX_PATH
    data_jsonl = os.path.join(box_path, "data.jsonl")
    if not os.path.exists(data_jsonl):
        print(f"{data_jsonl} not found -- run scrape_granicus.py first")
        return

    known_last_names = _load_known_last_names()
    with open(data_jsonl) as f:
        meetings = [json.loads(line) for line in f if line.strip()]

    written = skipped_exists = skipped_no_captions = failed = 0
    for row in meetings:
        clip_id = row.get("clip_id")
        captions_url = row.get("captions_url")
        if not clip_id or not captions_url:
            skipped_no_captions += 1
            continue

        out_path = os.path.join(box_path, f"{clip_id}.turns.json")
        if os.path.exists(out_path):
            skipped_exists += 1
            continue

        try:
            turns = fetch_and_parse(captions_url, known_last_names)
        except Exception as e:
            print(f"FAILED {clip_id}: {e}")
            failed += 1
            continue

        if not turns:
            print(f"{clip_id}: no captions available -- needs WhisperX fallback")
            skipped_no_captions += 1
            continue

        # Approximate proportional timestamp per turn -- same honest
        # methodology used by hand for seed_data.py's entries (Granicus
        # captions carry no real per-line timing, see module docstring),
        # now computed automatically and consistently instead of by hand.
        duration_seconds = _duration_to_seconds(row.get("duration"))
        full_text = " ".join(t["text"] for t in turns)
        total_len = len(full_text) or 1
        offset = 0
        for t in turns:
            t["timestamp_seconds"] = (
                round(offset / total_len * duration_seconds)
                if duration_seconds else None
            )
            offset += len(t["text"]) + 1  # +1 for the join-space in full_text

        meeting = {
            "clip_id": clip_id,
            "view_id": row.get("view_id"),
            "title": row.get("title"),
            "date_unix": row.get("date_unix"),
            "body": row.get("body"),
            "video": row.get("video"),
            "duration": row.get("duration"),
            "source": "captions",
            "turns": turns,
        }
        with open(out_path, "w") as f:
            json.dump(meeting, f)
        written += 1
        time.sleep(0.3)  # politeness, matching scrape_granicus.py's pacing

    print(
        f"wrote {written} turns.json files "
        f"({skipped_exists} already done, "
        f"{skipped_no_captions} skipped -- no captions, needs WhisperX fallback, "
        f"{failed} failed)"
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Debug mode: fetch+print one clip's turns without writing anything.
        turns = fetch_and_parse(sys.argv[1])
        if turns is None:
            print("no captions available for this clip")
        else:
            print(json.dumps(turns[:15], indent=2))
            print(f"... {len(turns)} turns total")
    else:
        build_transcripts()
