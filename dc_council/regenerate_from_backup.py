"""
One-off: regenerates turns.json for clip_ids whose entry no longer exists in
the current data.jsonl (it was overwritten by a later, narrower scrape run)
but whose metadata survives in data/videos/pre_dedup_backup/ -- backed up
right before deleting the duplication-corrupted originals. Reuses that
metadata (view_id, title, date_unix, body, video, duration) and re-fetches
+ re-parses captions fresh from Granicus with the dedupe_caption_text() fix.

Run from dc-council/dc_etl/:
  python3 regenerate_from_backup.py
"""
import json
import os
import time

from fetch_captions import fetch_and_parse, _duration_to_seconds, _load_known_last_names

HERE = os.path.dirname(os.path.abspath(__file__))
BOX_PATH = os.path.join(HERE, "data", "videos")
BACKUP_PATH = os.path.join(BOX_PATH, "pre_dedup_backup")


def main():
    with open("/tmp/affected_clips.json") as f:
        affected = json.load(f)
    missing = [c for c in affected if not os.path.exists(os.path.join(BOX_PATH, f"{c}.turns.json"))]
    print(f"{len(missing)} clips to regenerate from backup metadata")

    known_last_names = _load_known_last_names()
    written, failed = 0, 0
    for clip_id in missing:
        backup_path = os.path.join(BACKUP_PATH, f"{clip_id}.turns.json")
        with open(backup_path) as f:
            old = json.load(f)

        view_id = old.get("view_id")
        captions_url = f"https://dc.granicus.com/TranscriptViewer.php?view_id={view_id}&clip_id={clip_id}"
        try:
            turns = fetch_and_parse(captions_url, known_last_names)
        except Exception as e:
            print(f"FAILED {clip_id}: {e}")
            failed += 1
            continue
        if not turns:
            print(f"{clip_id}: no captions available on re-fetch")
            failed += 1
            continue

        duration_seconds = _duration_to_seconds(old.get("duration"))
        full_text = " ".join(t["text"] for t in turns)
        total_len = len(full_text) or 1
        offset = 0
        for t in turns:
            t["timestamp_seconds"] = (
                round(offset / total_len * duration_seconds) if duration_seconds else None
            )
            offset += len(t["text"]) + 1

        meeting = {
            "clip_id": clip_id,
            "view_id": view_id,
            "title": old.get("title"),
            "date_unix": old.get("date_unix"),
            "body": old.get("body"),
            "video": old.get("video"),
            "duration": old.get("duration"),
            "source": "captions",
            "turns": turns,
        }
        out_path = os.path.join(BOX_PATH, f"{clip_id}.turns.json")
        with open(out_path, "w") as f:
            json.dump(meeting, f)
        written += 1
        print(f"wrote {clip_id}.turns.json ({len(turns)} turns)")
        time.sleep(0.3)

    print(f"\ndone: wrote {written}, failed {failed}, of {len(missing)}")


if __name__ == "__main__":
    main()
