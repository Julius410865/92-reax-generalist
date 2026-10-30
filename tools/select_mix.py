"""Build a training set from every T-part row, rows a previous set did not use, and a replay of rows it did use.

    python -I tools/select_mix.py --prev dataset/train_50k --new 30000 --replay 15000 --out dataset/train_61k

Every T-part row (dataset/data/generalist/t/*.train.jsonl) is taken. --new rows come from the dataset/openai_anthropic
and dataset/n_records training rows the previous set did not use; --replay rows come from the previous set. Both draws
are taken per task type in proportion to its share of the pool (largest remainders), ranked by sha256 of the row id with
the draw's own salt, so the selection is fixed and reproducible. Rows are copied byte for byte (no re-serialisation, so option order is untouched) and written sorted
by id. Held-out rows (select / test) are never read. Writes manifest.json with the counts and the sha256 of the output.
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
T_GLOB = os.path.join("dataset", "data", "generalist", "t", "*.train.jsonl")
OTHER = (os.path.join("dataset", "openai_anthropic", "train.jsonl"), os.path.join("dataset", "n_records", "train.jsonl"))


def rank(salt: str, row_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{salt}|{row_id}".encode()).digest()[:8], "big")


def read(path: str) -> list[tuple[dict, str]]:
    """(row, its raw line) for every row of a JSONL file."""
    with open(path, encoding="utf-8") as fh:
        return [(json.loads(line), line if line.endswith("\n") else line + "\n") for line in fh if line.strip()]


def stratified(pool: list[tuple[dict, str]], n: int, salt: str) -> list[tuple[dict, str]]:
    """n rows of pool, per task type in proportion to its share (largest remainders), ranked by sha256 of the id."""
    if n > len(pool):
        raise SystemExit(f"asked for {n} rows from a pool of {len(pool)}")
    by = collections.defaultdict(list)
    for r in pool:
        by[r[0]["task_type"]].append(r)
    exact = {t: n * len(v) / len(pool) for t, v in by.items()}
    quota = {t: int(x) for t, x in exact.items()}
    for t in sorted(exact, key=lambda t: (exact[t] - quota[t], t), reverse=True)[: n - sum(quota.values())]:
        quota[t] += 1
    return [r for t in sorted(by) for r in sorted(by[t], key=lambda r: rank(salt, r[0]["id"]))[: quota[t]]]


def counts(rows: list[tuple[dict, str]], key: str) -> dict[str, int]:
    return dict(collections.Counter(r[0][key] for r in rows).most_common())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prev", default=os.path.join(ROOT, "dataset", "train_50k"))
    ap.add_argument("--new", type=int, default=30000)
    ap.add_argument("--replay", type=int, default=15000)
    ap.add_argument("--n-records", type=int, default=0, help="rows of dataset/n_records/train.jsonl, used before or not")
    ap.add_argument("--all", action="append", default=[], help="another training file taken whole (repeat)")
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset", "train_61k"))
    a = ap.parse_args(argv)
    prev = read(os.path.join(a.prev, "train.jsonl"))
    used = {r["id"] for r, _ in prev}
    t_rows = [r for p in sorted(glob.glob(os.path.join(ROOT, T_GLOB))) for r in read(p)]
    whole = [r for p in a.all for r in read(os.path.join(ROOT, p))]
    other = [r for p in OTHER for r in read(os.path.join(ROOT, p)) if r[0]["id"] not in used]
    if any(r["id"] in used for r, _ in t_rows + whole):
        raise SystemExit("rows taken whole are already in the previous set")
    new = stratified(other, a.new, "new")
    replay = stratified(prev, a.replay, "replay")
    n_rec = stratified(read(os.path.join(ROOT, OTHER[1])), a.n_records, "n_records") if a.n_records else []
    picked = t_rows + whole + new + replay + n_rec
    ids = [r["id"] for r, _ in picked]
    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate row ids in the selection")
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "train.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(line for _, line in sorted(picked, key=lambda r: r[0]["id"]))
    manifest = {"total": len(picked), "t_part": len(t_rows), "whole_files": {p: sum(1 for _ in open(os.path.join(ROOT, p))) for p in a.all},
                "new": len(new), "replay": len(replay), "n_records": len(n_rec),
                "previous_set": os.path.relpath(a.prev, ROOT), "t_part_by_task_type": counts(t_rows, "task_type"),
                "whole_by_task_type": counts(whole, "task_type"),
                "new_by_part": counts(new, "part"), "new_by_task_type": counts(new, "task_type"),
                "replay_by_part": counts(replay, "part"), "replay_by_task_type": counts(replay, "task_type"),
                "n_records_by_task_type": counts(n_rec, "task_type"),
                "pool": {"t_rows": len(t_rows), "unused_other_rows": len(other), "previous_rows": len(prev)},
                "rule": "all T-part rows and the --all files; new: unused openai_anthropic / n_records rows per task type in "
                        "proportion; replay: previous-set rows per task type in proportion; n_records: dataset/n_records rows per "
                        "task type in proportion; ranked by sha256 of the id (salts 'new', 'replay', 'n_records')",
                "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(json.dumps({k: v for k, v in manifest.items() if not k.endswith("task_type")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
