"""Select a fixed number of training rows from the dataset folder into dataset/<name>/train.jsonl.

    python -I tools/select_subset.py --total 50000 --out dataset/train_50k

Every row of dataset/n_records/train.jsonl is kept (the only training data in the eval-v5.1 question format); the rest
of the total comes from dataset/openai_anthropic/train.jsonl, drawn per category in proportion to the category's share
(largest remainders), ranked by sha256 of the row id, so the selection is fixed and reproducible. Held-out rows
(select / test) are not touched. Writes manifest.json with the counts and the sha256 of the output.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def rank(row_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"select|{row_id}".encode()).digest()[:8], "big")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--total", type=int, default=50000)
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset", "train_50k"))
    a = ap.parse_args(argv)
    n_rec = [l for l in open(os.path.join(ROOT, "dataset", "n_records", "train.jsonl"), encoding="utf-8")]
    oa = [json.loads(l) for l in open(os.path.join(ROOT, "dataset", "openai_anthropic", "train.jsonl"), encoding="utf-8")]
    need = a.total - len(n_rec)
    if need < 0:
        raise SystemExit(f"--total {a.total} is smaller than the {len(n_rec)} N-record rows")
    by_cat = collections.defaultdict(list)
    for r in oa:
        by_cat[r["category"]].append(r)
    exact = {c: need * len(v) / len(oa) for c, v in by_cat.items()}
    quota = {c: int(x) for c, x in exact.items()}
    for c in sorted(exact, key=lambda c: exact[c] - quota[c], reverse=True)[: need - sum(quota.values())]:
        quota[c] += 1
    picked = [r for c in sorted(by_cat) for r in sorted(by_cat[c], key=lambda r: rank(r["id"]))[: quota[c]]]
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "train.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(n_rec)
        for r in sorted(picked, key=lambda r: r["id"]):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {"total": len(n_rec) + len(picked), "from_n_records": len(n_rec), "from_openai_anthropic": len(picked),
                "openai_anthropic_by_category": dict(sorted(quota.items(), key=lambda kv: -kv[1])),
                "rule": "all N-record rows + openai_anthropic rows per category in proportion, ranked by sha256 of the id",
                "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
