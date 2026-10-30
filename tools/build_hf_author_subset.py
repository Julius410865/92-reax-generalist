"""Store the rows of decisionmodels/sn92-generalist-train-v1 written by given author families as training items.

    python -I tools/build_hf_author_subset.py --families openai,anthropic --out dataset/openai_anthropic

Each row is converted exactly as the stage loader converts ``s1`` rows (tools/train_generalist/data.py ``s1_item``):
choice options re-keyed A.. in their order, score levels A.. in level order, noul -> yes / no with yes first; the gold key
in ``expected``. Splits use the stage configs' held-out rule (sha256 of the row's group, ``s1_holdout`` of
data/stages/stage1.json): train rows go to train.jsonl, held-out rows to select.jsonl / test.jsonl (never trained on).
Output files are sorted by id and deterministic; manifest.json records counts, the source revision and every sha256.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ROOT)
from tools.train_generalist import common as C  # noqa: E402
from tools.train_generalist import data as D  # noqa: E402

HF = os.path.join(ROOT, "data", "generalist", "hf", "sn92-generalist-train-v1")
KEEP = ("category", "lang", "mix_tier", "gold_basis", "qtype")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--families", default="openai,anthropic")
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset", "openai_anthropic"))
    ap.add_argument("--config", default=os.path.join(ROOT, "data", "stages", "stage1.json"))
    a = ap.parse_args(argv)
    fams = set(a.families.split(","))
    cfg = C.read_json(a.config)
    src = C.read_json(os.path.join(HF, "SOURCE.json"))
    by_split: dict[str, list[dict]] = {s: [] for s in D.SPLITS}
    bad = 0
    for f in sorted(glob.glob(os.path.join(HF, "train-*.jsonl.gz"))):
        for row in C.read_jsonl(f):
            fam = D.author_family(row)
            if fam not in fams:
                continue
            try:
                item = D.s1_item(row, "hf_openai_anthropic")
            except (ValueError, KeyError, TypeError):
                bad += 1
                continue
            split = D.holdout(row, cfg)
            item.update({k: row.get(k) for k in KEEP}, author_family=fam, split=split,
                        source_dataset=f"decisionmodels/sn92-generalist-train-v1@{src['revision']}")
            by_split[split].append(item)
    os.makedirs(a.out, exist_ok=True)
    files, stats = {}, {}
    for split, items in by_split.items():
        items.sort(key=lambda it: it["id"])
        path = os.path.join(a.out, f"{split}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for it in items:
                q = it["questions"][0]
                assert q["expected"] in q["criteria"], it["id"]
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")   # never sort_keys: it would reorder yes/no options
        files[os.path.basename(path)] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        stats[split] = {"rows": len(items),
                        "by_category": dict(collections.Counter(it["category"] for it in items).most_common()),
                        "by_author_family": dict(collections.Counter(it["author_family"] for it in items).most_common()),
                        "by_question_type": dict(collections.Counter(it["qtype"] for it in items).most_common()),
                        "programmatic_gold": sum(it.get("gold_basis") == "programmatic" for it in items)}
    manifest = {"source": f"decisionmodels/sn92-generalist-train-v1@{src['revision']}", "licence": "CC-BY-4.0",
                "note": "rows whose author family is " + " / ".join(sorted(fams)) + "; their providers' terms restrict using outputs "
                        "to build competing models: the owner decided to use them for training",
                "author_families": sorted(fams), "heldout_rule": cfg.get("s1_holdout"), "unconvertible": bad,
                "format": "one training item per line: state, questions[0] {instructions, criteria A.. / yes,no, expected}",
                "splits": stats, "files": files}
    C.write_json(os.path.join(a.out, "manifest.json"), manifest)
    for s, v in stats.items():
        print(f"{s}: {v['rows']} rows")
    print(f"unconvertible {bad}; files in {os.path.relpath(a.out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
