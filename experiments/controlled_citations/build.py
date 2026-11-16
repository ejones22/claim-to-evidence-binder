"""Deterministically construct a frozen, explicitly synthetic diagnostic and review packets."""
import ast
import csv
import hashlib
import io
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_COMMIT = "31f4afe58c2d3a18b22fc07339860fb9127f697e"
VARIANTS = ("substantive", "procedural", "adjacent_measure")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()


def artifacts():
    benchmark_path = ROOT / "datapipeline/data/benchmark.jsonl"
    benchmark = {c["case_id"]: c for c in map(json.loads, benchmark_path.read_text().splitlines())}
    specs = json.loads((HERE / "source_specs.json").read_text())
    sources, cases = [], []
    for group, split, aid, adesc, bid, bdesc in specs:
        for cid, description, donor_id, donor_description in [(aid, adesc, bid, bdesc), (bid, bdesc, aid, adesc)]:
            c, donor = benchmark[cid], benchmark[donor_id]
            assert not c["is_synthetic"] and c["normalized"] != donor["normalized"]
            source_id = f"S{len(sources)+1:02d}"
            source = dict(source_id=source_id, source_case_id=cid, pair_id=group, split=split,
                          identifier=c["normalized"], title=c["title"], original_context=c["context"],
                          clip_id=c["clip_id"], donor_case_id=donor_id,
                          constructed_description=description,
                          source_url=f"https://github.com/ejones22/claim-to-evidence-binder/blob/{SOURCE_COMMIT}/datapipeline/data/benchmark.jsonl")
            sources.append(source)
            prefix = f"The committee has {c['normalized']} before it."
            contexts = {
                "substantive": f"{prefix} This measure {description}. Members may now discuss this item.",
                "procedural": f"{prefix} Members may now discuss this item. All those in favor, say aye. The vote is recorded.",
                "adjacent_measure": f"{prefix} We next turn to {donor['normalized']}. This measure {donor_description}. Members may now discuss this item.",
            }
            for variant in VARIANTS:
                case_id = "C" + digest(f"v1/{source_id}/{variant}".encode())[:12]
                cases.append(dict(case_id=case_id, source_id=source_id, pair_id=group, split=split,
                                  variant=variant, title=c["title"], context=contexts[variant],
                                  is_constructed=True, review_status="pending"))
    assert len(sources) == 30 and len({s['identifier'] for s in sources}) == 30
    assert len(cases) == 90 and len({c['case_id'] for c in cases}) == 90
    files = {"sources.json": json_bytes(sources), "cases.jsonl": ("\n".join(json.dumps(c, ensure_ascii=False) for c in cases)+"\n").encode()}
    # Extract the existing baseline literal without importing network-capable code.
    tree = ast.parse((ROOT / "dc_council/llm_judge_baseline.py").read_text())
    baseline = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROMPT_TMPL" for t in n.targets))
    files["prompts/baseline.txt"] = baseline.encode()
    review_map = {}
    for reviewer, seed in [("emma", 2026111501), ("vivianne", 2026111502)]:
        shuffled = list(cases)
        random.Random(seed).shuffle(shuffled)
        mapping = {}
        buf = io.StringIO(newline="")
        columns = ["review_id", "context", "title", "topic_match", "content_support", "label", "notes"]
        writer = csv.DictWriter(buf, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        lines = ["INDEPENDENT REVIEW", "Read REVIEW_INSTRUCTIONS.md before starting. Complete either this TXT file OR the CSV, not both.", "Do not inspect sources, case metadata, scripts, or another reviewer's answers until your form is locked.", ""]
        for i, c in enumerate(shuffled, 1):
            rid = f"R{i:03d}"
            mapping[rid] = c["case_id"]
            writer.writerow(dict(review_id=rid, context=c['context'], title=c['title']))
            lines.extend([f"CASE {rid}", f"CONTEXT: {c['context']}", f"TITLE: {c['title']}", "TOPIC_MATCH:", "CONTENT_SUPPORT:", "LABEL:", "NOTES:", ""])
        files[f"review/{reviewer}.csv"] = buf.getvalue().encode()
        files[f"review/{reviewer}.txt"] = ("\n".join(lines).rstrip()+"\n").encode()
        review_map[reviewer] = mapping
    files["review_map.json"] = json_bytes(review_map)
    manifest = dict(version=1, source_commit=SOURCE_COMMIT, construction="assistant-authored synthetic contexts grounded in real benchmark identifiers and titles; not transcript quotations",
                    sources=30, cases=90, pairs=15, development_sources=6, test_sources=24,
                    review_status="pending", benchmark_sha256=digest(benchmark_path.read_bytes()),
                    source_specs_sha256=digest((HERE/'source_specs.json').read_bytes()),
                    files={k: digest(v) for k,v in sorted(files.items())},
                    prompts={"baseline":digest(files['prompts/baseline.txt']), "intervention":digest((HERE/'prompts/intervention.txt').read_bytes())})
    files['manifest.json'] = json_bytes(manifest)
    return files


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify committed assets without overwriting anything')
    args=parser.parse_args()
    for path,data in artifacts().items():
        p=HERE/path
        if args.check:
            if not p.exists() or p.read_bytes()!=data: raise SystemExit(f'Frozen asset differs: {path}')
        else:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    print('Verified frozen assets' if args.check else 'Built 30 sources, 90 cases, and two independent review orders')
