"""Build a training set from fixed-size draws of given training files.

    python -I tools/select_take.py --out dataset/train_42k \
        --take "dataset/train_57k/train.jsonl:part=T:all" \
        --take "dataset/train_57k/train.jsonl:source=hf_openai_anthropic:5000" \
        --take "dataset/data/generalist/gen/expense_policy.train.jsonl::600"

Each --take is ``path:filter:count``: the rows of ``path`` whose field matches ``filter`` (``key=value``; empty = every
row), ``count`` of them (``all`` = every one) drawn per task type in proportion to its share (largest remainders),
ranked by sha256 of the row id, so the selection is fixed and reproducible. Rows are copied byte for byte (no
re-serialisation, so option order is untouched) and written sorted by id; a row id may appear only once. Held-out rows
(select / test) are never read. Writes manifest.json with the draw of every --take and the sha256 of the output.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ROOT)
from tools.select_mix import counts, read, stratified  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--take", action="append", required=True, help="path:key=value:count (filter and count optional)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    picked, draws = [], []
    for spec in a.take:
        path, filt, n = (spec.split(":") + ["", "all"])[:3]
        if any(x in path for x in ("select", "test", "heldout/")):    # the dev set may be trained on since 29 Oct
            raise SystemExit(f"{path}: a held-out file may never be trained on")
        pool = read(os.path.join(ROOT, path))
        if filt:
            key, _, val = filt.partition("=")
            pool = [r for r in pool if str(r[0].get(key)) == val]
        rows = pool if n in ("", "all") else stratified(pool, int(n), f"take|{path}")
        picked += rows
        draws.append({"path": path, "filter": filt or None, "pool": len(pool), "taken": len(rows),
                      "questions": sum(len(r[0]["questions"]) for r in rows), "by_task_type": counts(rows, "task_type")})
        print(f"{path} [{filt or 'all rows'}]: {len(rows)} of {len(pool)}", flush=True)
    ids = [r["id"] for r, _ in picked]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{len(ids) - len(set(ids))} row ids taken twice")
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "train.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(line for _, line in sorted(picked, key=lambda r: r[0]["id"]))
    manifest = {"total": len(picked), "questions": sum(d["questions"] for d in draws),
                "by_part": dict(collections.Counter(r["part"] for r, _ in picked)), "draws": draws,
                "rule": "per --take: rows matching the filter, the count drawn per task type in proportion, ranked by "
                        "sha256 of the id (salt 'take|<path>')",
                "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(json.dumps({k: manifest[k] for k in ("total", "questions", "by_part", "sha256")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
