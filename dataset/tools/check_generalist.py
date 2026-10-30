"""Checks a built T type before it is merged (data/generalist/DEV-GUIDELINES.md, section 7).

    python -I tools/check_generalist.py <task> [--rebuild] [--tokenizer /models/reax-1.1/tokenizer.json]

Reads data/generalist/t/<task>.{train,select,test}.jsonl and writes data/generalist/reports/<task>.json. Exit 0 only when
every check passes. ``--rebuild`` runs tools/records/build_<task>.py twice into scratch folders and requires byte-identical
output (determinism); it uses the raw files already downloaded.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from reax_subnet.spec.v5 import validate_mirror_row  # noqa: E402
from tools.records import common as C  # noqa: E402

SPLITS = ("train", "select", "test")
META = ("tier", "half", "area", "scope", "part", "task_type", "gold", "public", "idk")
SHORTCUT_SLACK = 0.15   # a cue may beat chance by at most this much accuracy ...
DEV_SLACK = 0.10        # ... or the dev set's own items of the type by at most this much
POSITION_SLACK = 0.05   # gold position: uniform +- this, for questions with at most 6 options
YES_SHARE = (0.40, 0.60)


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def qkey(q: dict) -> str:
    return norm(q.get("instructions", "")) + " || " + " | ".join(norm(v) for v in q["criteria"].values())


def load(task: str) -> dict[str, list[dict]]:
    out = {}
    for s in SPLITS:
        p = C.OUT / f"{task}.{s}.jsonl"
        out[s] = [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []
    return out


def words(t: str) -> set[str]:
    return {w for w in norm(t).split() if len(w) > 2}


def check(task: str, tokenizer: str | None) -> dict:
    data = load(task)
    res: dict = {"task": task, "counts": {s: len(v) for s, v in data.items()}, "checks": {}}
    ok = res["checks"]
    meta = C.dev_meta(task)
    dev_ref = next(json.loads(l) for l in open(C.DEV, encoding="utf-8") if json.loads(l)["task_type"] == task)

    # 1. schema and metadata
    bad = []
    for s, rows in data.items():
        for r in rows:
            try:
                validate_mirror_row(r)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{r.get('id')}: {exc}")
            want = {k: dev_ref.get(k) for k in META if k != "public"} | {"public": False}
            diff = {k: (r.get(k), want[k]) for k in META if r.get(k) != want[k]}
            if diff:
                bad.append(f"{r.get('id')}: metadata {diff}")
            if not r["id"].startswith(f"rec-{task}-{s}-"):
                bad.append(f"{r['id']}: id does not name its split")
    ok["schema"] = {"pass": not bad and all(data.values()), "problems": bad[:10], "n_problems": len(bad)}

    # 2. sizes
    ok["sizes"] = {"pass": res["counts"]["select"] == 150 and res["counts"]["test"] == 150 and res["counts"]["train"] > 0,
                   "counts": res["counts"]}

    # 3. duplicates and leakage: across splits, against the dev set; source groups never in two splits
    dev_keys = {qkey(q) for l in open(C.DEV, encoding="utf-8") for q in json.loads(l)["questions"]}
    dev_text = {norm(q["instructions"]) for l in open(C.DEV, encoding="utf-8") for q in json.loads(l)["questions"]}
    seen: dict[str, str] = {}
    dup_cross = dup_dev = 0
    groups = collections.defaultdict(set)
    for s, rows in data.items():
        for r in rows:
            groups[r["source_id"]].add(s)
            for q in r["questions"]:
                k = qkey(q)
                if k in dev_keys or norm(q["instructions"]) in dev_text:
                    dup_dev += 1
                if k in seen and seen[k] != s:
                    dup_cross += 1
                seen.setdefault(k, s)
    split_groups = sum(1 for v in groups.values() if len(v) > 1)
    ok["leakage"] = {"pass": dup_cross == 0 and dup_dev == 0 and split_groups == 0, "cross_split_duplicates": dup_cross,
                     "dev_duplicates": dup_dev, "groups_in_two_splits": split_groups}
    dup_within = sum(c - 1 for c in collections.Counter(qkey(q) for r in data["train"] for q in r["questions"]).values() if c > 1)
    ok["train_duplicates"] = {"pass": dup_within <= 0.01 * max(1, len(data["train"])), "n": dup_within}

    # 4. answer balance: gold position (few options), yes share (yes/no), gold-text concentration
    allq = [q for rows in data.values() for r in rows for q in r["questions"]]
    pos = collections.Counter()
    k_small = collections.Counter()
    yes = n_yesno = 0
    gold_text = collections.Counter()
    for q in allq:
        keys = list(q["criteria"])
        if keys == ["yes", "no"]:
            n_yesno += 1
            yes += q["expected"] == "yes"
            continue
        gold_text[norm(q["criteria"][q["expected"]])] += 1
        if len(keys) <= 6:
            pos[(len(keys), keys.index(q["expected"]))] += 1
            k_small[len(keys)] += 1
    pos_dev = {k: max(abs(pos[(k, i)] / n - 1 / k) for i in range(k)) for k, n in k_small.items() if n >= 50}
    yes_share = yes / n_yesno if n_yesno else None
    top_gold = gold_text.most_common(1)[0][1] / max(1, sum(gold_text.values())) if gold_text else 0.0
    n_classes = len(gold_text)
    ok["balance"] = {"pass": all(v <= POSITION_SLACK for v in pos_dev.values())
                     and (yes_share is None or YES_SHARE[0] <= yes_share <= YES_SHARE[1]),
                     "gold_position_max_deviation": {str(k): round(v, 3) for k, v in pos_dev.items()},
                     "yes_share": None if yes_share is None else round(yes_share, 3),
                     "top_gold_text_share": round(top_gold, 3), "distinct_gold_texts": n_classes}

    # 5. shortcut test on the served form (more than 26 options are capped as the trainer and the validator do): pick the
    # longest / shortest option / the option sharing most words with the question. A cue fails when it beats chance by
    # SHORTCUT_SLACK and also the dev set's own items of this type by DEV_SLACK (a property the live items share is no
    # build error, e.g. intent names that repeat words of the utterance)
    def cue_stats(items: list[dict]) -> tuple[dict[str, float], float, int]:
        from tools.train_generalist import data as D

        cues, chance, n = collections.Counter(), 0.0, 0
        for it in items:
            for seed in (0, 1):
                for q in D.cap_item(it, seed)["questions"]:
                    crit = q["criteria"]
                    keys = list(crit)
                    n += 1
                    chance += 1 / len(keys)
                    lens = {k: len(str(crit[k])) for k in keys}
                    ov = {k: len(words(crit[k]) & words(q.get("instructions", ""))) for k in keys}
                    for name, score, pick in (("longest", lens, max), ("shortest", lens, min), ("overlap", ov, max)):
                        best = pick(score.values())
                        top = [k for k in keys if score[k] == best]
                        cues[name] += (1 / len(top)) if q["expected"] in top else 0.0
        return ({k: round(v / n, 3) for k, v in cues.items()} if n else {}), (chance / n if n else 0.0), n

    cue_acc, chance, n = cue_stats([r for rows in data.values() for r in rows])
    dev_items = [json.loads(l) for l in open(C.DEV, encoding="utf-8") if json.loads(l)["task_type"] == task]
    dev_acc, _, _ = cue_stats(dev_items)
    limit = {k: round(max(chance + SHORTCUT_SLACK, dev_acc.get(k, 0.0) + DEV_SLACK), 3) for k in cue_acc}
    ok["shortcuts"] = {"pass": all(v <= limit[k] for k, v in cue_acc.items()), "chance": round(chance, 3),
                       "cue_accuracy": cue_acc, "dev_cue_accuracy": dev_acc, "limit": limit, "questions": n}

    # 6. prompt length (served form: capped to 26 options), with the model's tokenizer if given
    if tokenizer:
        from tools.train_generalist import data as D

        tmp = tempfile.mkdtemp()
        shutil.copy(tokenizer, Path(tmp) / "tokenizer.json")
        rend = D.Renderer(tmp)
        lens = []
        for r in data["select"] + data["test"] + data["train"][:1000]:
            for x in D.flatten_item(D.cap_item(r, 0)):
                lens.append(len(rend.encode(x["state"], x["question"])[0]))
        lens.sort()
        p99 = lens[min(len(lens) - 1, int(0.99 * len(lens)))]
        ok["prompt_tokens"] = {"pass": p99 <= 2000, "p50": lens[len(lens) // 2], "p99": p99, "max": lens[-1]}

    # 7. source recorded
    src = C.RAW / task / "SOURCE.json"
    sj = json.loads(src.read_text()) if src.exists() else {}
    ok["source"] = {"pass": bool(sj.get("licence")) and bool(sj.get("files")) and "verify" not in str(sj.get("licence")).lower(),
                    "licence": sj.get("licence"), "files": len(sj.get("files", {}))}

    res["sha256"] = {s: hashlib.sha256((C.OUT / f"{task}.{s}.jsonl").read_bytes()).hexdigest()
                     for s in SPLITS if (C.OUT / f"{task}.{s}.jsonl").exists()}
    res["pass"] = all(v["pass"] for v in ok.values())
    return res


def rebuild_identical(task: str) -> dict:
    """Run the builder twice with different hash seeds; both outputs must equal the files on disk."""
    builder = ROOT / "tools" / "records" / f"build_{task}.py"
    shas = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        before = {s: (C.OUT / f"{task}.{s}.jsonl").read_bytes() for s in SPLITS}
        subprocess.run([sys.executable, "-I", str(builder)], check=True, env=env, cwd=ROOT, stdout=subprocess.DEVNULL)
        shas.append({s: hashlib.sha256((C.OUT / f"{task}.{s}.jsonl").read_bytes()).hexdigest() for s in SPLITS})
        if any((C.OUT / f"{task}.{s}.jsonl").read_bytes() != before[s] for s in SPLITS):
            return {"pass": False, "note": f"output changed on the run with PYTHONHASHSEED={seed}"}
    return {"pass": shas[0] == shas[1], "sha256": shas[0]}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--tokenizer", default=os.environ.get("REAX_TOKENIZER", ""))
    a = ap.parse_args(argv)
    res = check(a.task, a.tokenizer or None)
    if a.rebuild:
        res["checks"]["determinism"] = rebuild_identical(a.task)
        res["pass"] = all(v["pass"] for v in res["checks"].values())
    out = ROOT / "data" / "generalist" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.task}.json").write_text(json.dumps(res, indent=1) + "\n")
    for name, v in res["checks"].items():
        print(f"{'PASS' if v['pass'] else 'FAIL'}  {name:16s} {json.dumps({k: x for k, x in v.items() if k != 'pass'})[:220]}")
    print("ALL PASS" if res["pass"] else "NOT PASSING")
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
