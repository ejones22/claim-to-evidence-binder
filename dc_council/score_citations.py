"""
The Day-2 "prove it generalizes" step: the same claim-to-evidence idea as
score_claims.py (dc-council/earnings_etl/), pointed at a different domain
and a different kind of claim. An earnings call claims a dollar figure
that should match a filed number; a council meeting cites a bill or
resolution number that should (a) actually exist in the official record
and (b) be discussed consistently with what that record says it's about.

Two levels, reported separately since they answer different questions:
  - EXISTS: the cited B##-#### / PR##-#### number is a real LIMS record.
  - TOPIC MATCH: the sentence citing it shares real vocabulary with the
    record's official title, i.e. the speaker is describing the right bill,
    not just reading out a number that happens to resolve.

Run from dc-council/dc_etl/:
  python3 score_citations.py
Writes citations_scored.jsonl (one row per citation found) + a summary.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LIMS_PATH = os.path.join(HERE, "data", "lims", "bulk_legislation.json")
VIDEOS_DIR = os.path.join(HERE, "data", "videos")

CITATION_RE = re.compile(
    r"\b(BILL|RESOLUTION|PR|B)\.?\s*(\d{1,3})[\s\-]+(\d{1,4})\b", re.IGNORECASE
)
TYPE_TO_PREFIX = {"BILL": "B", "B": "B", "RESOLUTION": "PR", "PR": "PR"}

STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "for", "in", "on", "act",
    "amendment", "clarification", "temporary", "emergency", "permanent",
    "declaration", "resolution", "approval", "congressional", "review",
    "district", "government", "2025", "2026", "2027", "this",
}


def load_lookup():
    raw = json.load(open(LIMS_PATH))
    lookup = {}
    for items in raw.values():
        for item in items:
            num = item.get("legislationNumber")
            if num:
                lookup[num.upper()] = item
    return lookup


def normalize(type_word, period, number):
    prefix = TYPE_TO_PREFIX.get(type_word.upper())
    if not prefix:
        return None
    return f"{prefix}{period}-{int(number):04d}"


def significant_words(text):
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def topic_overlap(sentence, title):
    s_words = significant_words(sentence)
    t_words = significant_words(title)
    if not t_words:
        return 0.0
    return len(s_words & t_words) / len(t_words)


def main():
    lookup = load_lookup()
    print(f"{len(lookup)} legislation records loaded")

    rows = []
    meeting_files = sorted(glob.glob(os.path.join(VIDEOS_DIR, "*.turns.json")))
    for path in meeting_files:
        clip_id = os.path.basename(path).split(".")[0]
        with open(path) as f:
            meeting = json.load(f)
        for turn in meeting.get("turns", []):
            text = turn["text"]
            for m in CITATION_RE.finditer(text):
                # "BILL 20 6-599" is a real caption artifact for "BILL
                # 26-599" (confirmed against LIMS: B26-0599 exists, B20-0006
                # does not, and this exact garble pattern repeats across
                # meetings) -- if a hyphen+digit immediately trails the
                # match, the regex almost certainly split one number into
                # two, so the match is unreliable and is skipped rather
                # than minted as a confident but wrong citation.
                tail = text[m.end():m.end() + 2]
                if re.match(r"-\d", tail):
                    continue
                cite_id = normalize(m.group(1), m.group(2), m.group(3))
                if not cite_id:
                    continue
                record = lookup.get(cite_id)
                # look at a window around the citation for the topic check,
                # not just the one sentence, since the description often
                # trails the number ("Bill 26-770, the Restoration of...")
                lo, hi = max(0, m.start() - 20), min(len(text), m.end() + 160)
                context = text[lo:hi]
                row = {
                    "clip_id": clip_id,
                    "view_id": meeting.get("view_id"),
                    "meeting_title": meeting.get("title"),
                    "start_sec": turn.get("timestamp_seconds"),
                    "speaker": turn.get("speaker"),
                    "cited_as": m.group(0),
                    "normalized": cite_id,
                    "exists": record is not None,
                }
                if record:
                    row["official_title"] = record["title"]
                    row["context"] = context
                    row["topic_overlap"] = round(topic_overlap(context, record["title"]), 2)
                    row["topic_match"] = row["topic_overlap"] >= 0.3
                rows.append(row)

    with open(os.path.join(HERE, "citations_scored.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n = len(rows)
    n_exists = sum(1 for r in rows if r["exists"])
    n_topic = sum(1 for r in rows if r.get("topic_match"))
    print(f"\n{n} citations found across {len(meeting_files)} meetings")
    print(f"{n_exists}/{n} ({n_exists/n:.0%}) resolve to a real LIMS record")
    print(f"{n_topic}/{n_exists} ({n_topic/max(n_exists,1):.0%} of those that exist) "
          f"are discussed with vocabulary matching the official title")

    not_found = sorted({r["normalized"] for r in rows if not r["exists"]})
    print(f"\n{len(not_found)} distinct cited numbers never resolved, e.g.: {not_found[:10]}")


if __name__ == "__main__":
    main()
