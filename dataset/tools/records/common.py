"""Shared pieces of the T-type builders (tools/records/build_<task>.py): pinned downloads, v5.1 rows, hash splits, writing.

Every builder follows data/generalist/DEV-GUIDELINES.md. Rules that this module enforces:

* raw files are fetched once into ``data/generalist/raw/<task>/`` with their URL, revision and sha256 in ``SOURCE.json``;
  a re-run on another machine downloads the same pinned files and refuses a file whose sha256 differs;
* a row's split comes from ``sha256(<task>|<group key>)``, never from its position, so near-copies stay together;
* all randomness comes from ``rng(<task>, <parts>)`` (string seeds), so the output is byte-identical on every run.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "generalist" / "raw"
OUT = ROOT / "data" / "generalist" / "t"
DEV = ROOT / "eval-v5" / "devset-v1" / "dev.jsonl"
COLLECTED = "2026-10-27"
SPLIT_SIZES = {"select": 150, "test": 150}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
USER_AGENT = "reax-generalist-builder/1 (training-data build; contact via repo)"


def code(i: int) -> str:
    """Option code of position ``i``: A..Z, then AA, AB, ... (FORMAT.md)."""
    return LETTERS[i] if i < 26 else LETTERS[i // 26 - 1] + LETTERS[i % 26]


def rng(*parts: Any) -> random.Random:
    return random.Random("|".join(str(p) for p in parts))


def unit(*parts: Any) -> float:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:13], 16) / 16 ** 13


def split_of(task: str, group: str, n_groups_hint: int | None = None, select: float = 0.03, test: float = 0.03) -> str:
    """'select' / 'test' / 'train' by the hash of the group key. The shares only need to leave enough held-out groups;
    ``write_splits`` cuts select and test to 150 items each and train to its target."""
    h = unit("split", task, group)
    return "select" if h < select else "test" if h < select + test else "train"


def fetch(task: str, url: str, name: str, sha256: str | None = None) -> Path:
    """Download ``url`` once to raw/<task>/<name>; with ``sha256`` the file must match (pinned sources)."""
    d = RAW / task
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    if not p.exists():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as r, open(p.with_suffix(p.suffix + ".part"), "wb") as fh:
            while chunk := r.read(1 << 20):
                fh.write(chunk)
        p.with_suffix(p.suffix + ".part").rename(p)
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    if sha256 and got != sha256:
        raise SystemExit(f"{p}: sha256 {got} differs from the pinned {sha256}; the source changed")
    return p


def hf_file(task: str, repo: str, revision: str, path: str, sha256: str | None = None) -> Path:
    """One file of a Hugging Face dataset repo at a pinned revision."""
    url = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}"
    return fetch(task, url, path.replace("/", "__"), sha256)


def record_source(task: str, entries: Sequence[Mapping[str, Any]], licence: str, licence_url: str, notes: str = "") -> None:
    """raw/<task>/SOURCE.json: every raw file with its URL and sha256, the licence and how the data was used."""
    d = RAW / task
    files = {}
    for e in entries:
        p = d / e["name"]
        files[e["name"]] = {"url": e["url"], "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
    (d / "SOURCE.json").write_text(json.dumps({"task": task, "licence": licence, "licence_url": licence_url,
                                               "downloaded": COLLECTED, "files": files, "notes": notes}, indent=1) + "\n")


def row(task: str, meta: Mapping[str, Any], source: str, source_id: str, questions: Sequence[Mapping[str, Any]],
        *, idk: bool = False) -> dict[str, Any]:
    """A v5.1 typed row with the dev set's metadata for ``task`` (``meta`` = area, gold, half [, component]); the id is
    set by ``write_splits``."""
    out = {"id": None, "tier": "mirror", "half": meta["half"], "area": meta["area"], "scope": "same_skill", "part": "T",
           "task_type": task, "gold": bool(meta["gold"]), "source": source, "source_id": str(source_id),
           "collected": COLLECTED, "collected_utc": f"{COLLECTED}T00:00:00Z", "public": False, "fresh": False, "idk": idk,
           "questions": [dict(q) for q in questions]}
    if meta.get("component"):
        out["component"] = meta["component"]
    return out


def mc(texts: Sequence[str], gold: int, r: random.Random) -> tuple[dict[str, str], str]:
    """Lettered options in a shuffled order; returns (criteria, expected key)."""
    order = list(range(len(texts)))
    r.shuffle(order)
    return {code(i): texts[o] for i, o in enumerate(order)}, code(order.index(gold))


def dev_meta(task: str) -> dict[str, Any]:
    """area / gold / half / component of ``task`` exactly as in the dev set."""
    for line in open(DEV, encoding="utf-8"):
        d = json.loads(line)
        if d["task_type"] == task:
            return {k: d.get(k) for k in ("area", "gold", "half", "component")}
    raise SystemExit(f"{task}: not a dev task type")


def write_splits(task: str, rows_by_split: Mapping[str, Iterable[dict[str, Any]]], train_target: int) -> dict[str, int]:
    """Cut select / test to 150 and train to ``train_target`` (in a hash order, so the cut is stable), number the ids and
    write data/generalist/t/<task>.<split>.jsonl. Returns the counts."""
    sys.path.insert(0, str(ROOT / "src"))
    from reax_subnet.spec.v5 import validate_mirror_row

    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split in ("train", "select", "test"):
        rows = sorted(rows_by_split.get(split, ()), key=lambda r: unit("order", task, r["source_id"],
                                                                     json.dumps(r["questions"], sort_keys=True)))
        keep = train_target if split == "train" else SPLIT_SIZES[split]
        if len(rows) < keep:
            print(f"{task}: only {len(rows)} {split} rows for a target of {keep}", file=sys.stderr)
        rows = rows[:keep]
        with open(OUT / f"{task}.{split}.jsonl", "w", encoding="utf-8") as fh:
            for i, r in enumerate(rows):
                r = dict(r, id=f"rec-{task}-{split}-{i}")
                validate_mirror_row(r)
                fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
        counts[split] = len(rows)
    return counts
