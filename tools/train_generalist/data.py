"""Stage data: load the sources of a stage config, split, filter, convert to eval-v5.1 items and render them as served.

    python -m tools.train_generalist.data --config data/stages/stage1.json --out prepared/eval --splits select,test
    python -m tools.train_generalist.data --config data/stages/stage1.json --out prepared/stage1 --splits train

Source kinds:
* ``s1``: rows of decisionmodels/sn92-generalist-train-v1 (one question each). Converted on load: ``choice`` options re-keyed
  A.. in their order; ``score`` levels re-keyed A.. in level order (never shuffled); ``noul`` becomes a yes/no question with
  ``yes`` first, as eval v5.1 renders yes/no (FORMAT.md).
* ``mirror``: eval-v5.1 typed rows (``questions``, ``part``, ``task_type`` ...), used as they are.
* a plain string entry in ``select`` / ``test`` is a ``mirror`` glob.

Held-out split (``s1_holdout``): by sha256 of the row's group (``ancestry.split_key``, else ``cf_pair``, else ``root``, else
the id), computed before any filter, so no stage ever trains on a select or test row whatever its filters are. A stage's
``take`` slice is over a second hash order of the filtered training rows; ``weight`` < 1 keeps that fraction of the slice
(again by hash). Rows are rendered with ``v5wire.cap_item`` (26 options), ``v5wire.flatten`` and ``prompt.render``.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import random
import string
import sys
from typing import Any, Iterable, Mapping

from reax_subnet.spec import v5wire

from . import common as C

EVAL_CAP_SEED = 0          # the fixed 26-option subset of an eval question (same for every model scored on it)
EVAL_GROUP_CAP = 20        # at most this many scored rows per held-out group (one template can hold >1,000 rows); the rest stay unused
FORBIDDEN_TRAIN = ("data/generalist/heldout/",)    # the dev set (eval-v5/) may be trained on since 29 Oct
SPLITS = ("train", "select", "test")


def _h(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def _frac(*parts: Any) -> float:
    return _h(*parts) / 2 ** 64


def group_key(row: Mapping[str, Any]) -> str:
    a = row.get("ancestry") or {}
    for k in ("split_key", "cf_pair", "root"):
        if a.get(k):
            return f"{k}:{a[k]}"
    return f"id:{row['id']}"


def holdout(row: Mapping[str, Any], cfg: Mapping[str, Any]) -> str:
    h = cfg.get("s1_holdout") or {}
    f = _frac("holdout", group_key(row))
    if f < h.get("select", 0.0):
        return "select"
    if f < h.get("select", 0.0) + h.get("test", 0.0):
        return "test"
    return "train"


def author_family(row: Mapping[str, Any]) -> str:
    a = row.get("ancestry") or {}
    return str(a.get("author_family") or row.get("author_family") or (row.get("generator") or {}).get("family") or "unknown")


def s1_item(row: Mapping[str, Any], source: str) -> dict[str, Any]:
    """An s1 row as an eval-v5.1 typed item (one question)."""
    q, qtype, exp = row["question"], row["question"]["type"], str(row["expected"])
    crit = q.get("criteria")
    if qtype == "noul":
        crit = crit or {}
        criteria = {"yes": crit.get("true", "Yes"), "no": crit.get("false", "No")}
        expected = {"true": "yes", "false": "no"}[exp]
    elif qtype == "score":
        keys = [str(i) for i in range(len(crit))]
        criteria = {string.ascii_uppercase[i]: v for i, v in enumerate(crit)}
        expected = string.ascii_uppercase[keys.index(exp)]
    elif qtype == "choice":
        keys = [str(k) for k in crit]
        if len(keys) > 26:
            raise ValueError("more than 26 options")
        criteria = {string.ascii_uppercase[i]: crit[k] for i, k in enumerate(crit)}
        expected = string.ascii_uppercase[keys.index(exp)]
    else:
        raise ValueError(f"unknown question type {qtype!r}")
    return {"id": row["id"], "state": row.get("state"), "idk": False, "part": "S1", "area": None, "gold": False,
            "task_type": f"s1:{row.get('category', 'other')}", "source": source, "qtypes": [qtype], "group": group_key(row),
            "questions": [{"instructions": q.get("instructions", ""), "criteria": criteria, "expected": expected}]}


def mirror_item(row: Mapping[str, Any], source: str) -> dict[str, Any]:
    out = dict(row)
    out["source"] = source
    out.setdefault("qtypes", ["yesno" if set(q["criteria"]) == {"yes", "no"} else "choice" for q in row["questions"]])
    return out


def augment(item: dict[str, Any], seed: Any) -> dict[str, Any]:
    """Shuffle the options of ``choice`` questions (gold position balance); yes/no and score levels keep their order."""
    rng = random.Random(f"augment|{seed}|{item['id']}")
    qs = []
    for q, qt in zip(item["questions"], item["qtypes"]):
        if qt in ("choice", "") and set(q["criteria"]) != {"yes", "no"}:
            keys = list(q["criteria"])
            rng.shuffle(keys)
            codes = [string.ascii_uppercase[i] for i in range(len(keys))] if len(keys) <= 26 else keys
            crit = {c: q["criteria"][k] for c, k in zip(codes, keys)}
            q = dict(q, criteria=crit, expected=codes[keys.index(str(q["expected"]))])
        qs.append(q)
    return dict(item, questions=qs)


# ------------------------------------------------------------------------------------------------------------ sources

def _files(pattern: str, root: str) -> list[str]:
    return sorted(glob.glob(os.path.join(root, pattern)))


def _entry(e: Any) -> dict[str, Any]:
    if not isinstance(e, str):
        return dict(e)
    base = os.path.basename(e).split(".")[0]
    return {"kind": "mirror", "glob": e, "name": os.path.basename(os.path.dirname(e)) if "*" in base else base}


def iter_s1(entry: Mapping[str, Any], cfg: Mapping[str, Any], split: str, root: str) -> Iterable[dict[str, Any]]:
    files = _files(entry["glob"], root)
    if not files:
        raise FileNotFoundError(f"source {entry.get('name')}: no file matches {entry['glob']}")
    tiers = entry.get("mix_tier")
    excl = set(entry.get("exclude_author_family") or ())
    for f in files:
        for row in C.read_jsonl(f):
            if holdout(row, cfg) != split:
                continue
            if tiers and row.get("mix_tier") not in tiers:
                continue
            if author_family(row) in excl:
                continue
            yield row


def load_entry(entry: Mapping[str, Any], cfg: Mapping[str, Any], split: str, root: str,
               stats: dict[str, Any]) -> list[dict[str, Any]]:
    name = entry.get("name") or entry["glob"]
    if split == "train" and any(x in entry["glob"] for x in FORBIDDEN_TRAIN):
        raise ValueError(f"source {name}: {entry['glob']} is an eval / held-out path and may never be trained on")
    items: list[dict[str, Any]] = []
    bad = 0
    capped_out = 0
    if entry.get("kind", "mirror") == "s1":
        rows = list(iter_s1(entry, cfg, split, root))
        if split != "train":
            by_group: dict[str, list] = {}
            for r in sorted(rows, key=lambda r: _h("evalcap", group_key(r), r["id"])):
                by_group.setdefault(group_key(r), []).append(r)
            kept = [r for g in by_group.values() for r in g[:EVAL_GROUP_CAP]]
            capped_out, rows = len(rows) - len(kept), sorted(kept, key=lambda r: r["id"])
        if split == "train":
            rows.sort(key=lambda r: _h("order", cfg.get("seed", 0), r["id"]))
            a, b = (entry.get("take") or [0, None])
            rows = rows[a:b]
            w = float(entry.get("weight", 1.0))
            if w < 1.0:
                rows = [r for r in rows if _frac("weight", name, r["id"]) < w]
        for r in rows:
            try:
                items.append(s1_item(r, name))
            except (ValueError, KeyError, TypeError):
                bad += 1
    else:
        files = _files(entry["glob"], root)
        if split == "train" and not files:
            raise FileNotFoundError(f"source {name}: no file matches {entry['glob']}")
        for f in files:
            for r in C.read_jsonl(f):
                if any(x in f for x in FORBIDDEN_TRAIN) and split == "train":
                    raise ValueError(f"{f}: may never be trained on")
                items.append(mirror_item(r, name))
        if split != "train" and any(it.get("group") for it in items):    # s1-derived eval rows: the same group cap
            by_group: dict[str, list] = {}
            for it in sorted(items, key=lambda it: _h("evalcap", it.get("group") or it["id"], it["id"])):
                by_group.setdefault(it.get("group") or it["id"], []).append(it)
            kept = [it for g in by_group.values() for it in g[:EVAL_GROUP_CAP]]
            capped_out, items = len(items) - len(kept), sorted(kept, key=lambda it: it["id"])
    stats[name] = {"items": len(items), "unconvertible": bad, "files": len(_files(entry["glob"], root))}
    if capped_out:
        stats[name]["over_group_cap"] = capped_out
    return items


def load_split(cfg: Mapping[str, Any], split: str, root: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = cfg["sources"] if split == "train" else cfg[split]
    stats: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for e in entries:
        items += load_entry(_entry(e), cfg, split, root, stats)
    ids = [it["id"] for it in items]
    if split != "train" and len(set(ids)) != len(ids):
        raise ValueError(f"{split}: duplicate item ids")
    return items, stats


# ----------------------------------------------------------------------------------------------------------- render

def render_rows(capped: list[dict[str, Any]], tok) -> list[dict[str, Any]]:
    """The served rows of (already capped) eval items with token ids and option keys, for one tokenizer. A row that cannot be
    rendered has no ids: a failed question, as on the validator."""
    rows = []
    for r in v5wire.flatten(capped):
        try:
            ids, rend = C.render_ids(tok, r)
        except Exception:
            ids, rend = [], None
        rows.append({"id": r["id"], "item": r["item"], "ids": ids, "keys": list(rend.keys) if rend else []})
    return rows


def prepare_eval(items: list[dict[str, Any]], tok) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """(capped items, served rows with ids/keys, stats). The items are what is scored (and fixed); the rows are re-rendered
    with each model's own tokenizer when it is scored (``render_rows``)."""
    capped = [v5wire.cap_item(it, EVAL_CAP_SEED) if "questions" in it else it for it in items]
    rows = render_rows(capped, tok)
    return capped, rows, {"items": len(capped), "questions": len(rows), "tokens": sum(len(r["ids"]) for r in rows),
                          "render_failed": sum(not r["ids"] for r in rows),
                          "over_max_length": sum(len(r["ids"]) > C.EVAL_MAX_LENGTH for r in rows)}


def prepare_train(items: list[dict[str, Any]], tok, cfg: Mapping[str, Any],
                  augment_sources: set[str]) -> tuple[list[dict], dict[str, Any]]:
    seed, max_len = cfg.get("seed", 0), int(cfg["max_len"])
    rows, too_long, failed, tokens = [], 0, 0, 0
    for it in items:
        if it["source"] in augment_sources:
            it = augment(it, seed)
        it = v5wire.cap_item(it, _h("cap", seed, it["id"]) % 2 ** 31)
        for r, q in zip(v5wire.flatten([it]), it["questions"]):
            try:
                ids, rend = C.render_ids(tok, r)
                gold = rend.keys.index(str(r["expected"]))
            except Exception:
                failed += 1
                continue
            if len(ids) > max_len:
                too_long += 1
                continue
            tokens += len(ids)
            rows.append({"id": r["id"], "source": it["source"], "ids": ids, "k": len(rend.keys), "gold": gold})
    rng = random.Random(f"shuffle|{seed}")
    rng.shuffle(rows)
    return rows, {"rows": len(rows), "tokens": tokens, "over_max_len": too_long, "render_failed": failed}


def config_digest(cfg: Mapping[str, Any], split: str) -> str:
    import json
    keys = ["s1_holdout", "seed", split] if split != "train" else ["s1_holdout", "seed", "max_len", "sources"]
    blob = json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--splits", default="train")
    ap.add_argument("--root", default=".", help="repository root the config globs are relative to")
    ap.add_argument("--tokenizer", default=None,
                    help="tokenizer.json or model dir (default: the config's base; $REAX_TOKENIZER only if the base is absent)")
    ap.add_argument("--max-rows", type=int, default=None, help="train only: keep the first N rows (smoke tests)")
    a = ap.parse_args(argv)
    cfg = C.read_json(a.config)
    tok_src = a.tokenizer or (cfg["base"] if os.path.exists(os.path.join(cfg["base"], "tokenizer.json"))
                              else os.environ.get("REAX_TOKENIZER") or cfg["base"])
    tok = C.load_tokenizer(tok_src)
    splits = [s.strip() for s in a.splits.split(",") if s.strip()]
    if any(s not in SPLITS for s in splits):
        ap.error(f"splits must be among {SPLITS}")
    for split in splits:
        items, stats = load_split(cfg, split, a.root)
        meta: dict[str, Any] = {"config": os.path.abspath(a.config), "stage": cfg.get("stage"), "split": split,
                                "digest": config_digest(cfg, split), "tokenizer": C.tokenizer_digest(tok_src),
                                "sources": stats}
        if split == "train":
            aug = {_entry(e).get("name") or _entry(e)["glob"] for e in cfg["sources"] if _entry(e).get("augment")}
            rows, st = prepare_train(items, tok, cfg, aug)
            if a.max_rows:
                rows = rows[: a.max_rows]
                st = dict(st, rows=len(rows), tokens=sum(len(r["ids"]) for r in rows), truncated_to=a.max_rows)
            C.write_jsonl(os.path.join(a.out, "train.jsonl.gz"), rows)
            meta.update(st)
        else:
            capped, rows, st = prepare_eval(items, tok)
            C.write_jsonl(os.path.join(a.out, f"{split}.items.jsonl.gz"), capped)
            C.write_jsonl(os.path.join(a.out, f"{split}.rows.jsonl.gz"), rows)
            meta.update(st)
        C.write_json(os.path.join(a.out, f"{split}.meta.json"), meta)
        print(f"{split}: " + ", ".join(f"{k} {v}" for k, v in meta.items() if k not in ("config", "sources")), flush=True)
        for name, s in stats.items():
            print(f"  {name}: {s}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
