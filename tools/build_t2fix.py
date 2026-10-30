"""Repaired copy of dataset/t2 for training: no row removed; rows with an answer shortcut or too few options repaired.

    python -I tools/build_t2fix.py --out dataset/t2fix

Reads dataset/t2 (never changed) and eval-v5/devset-v1/dev.jsonl. Writes:
* train.jsonl: every MIX-train row, with two repairs (REBALANCE, PAD), plus REFILL rows, plus half of the dev items
  (DEV_TRAIN_SHARE, the same share of every task type, ranked by sha256 of the id);
  plus every train row of the EXTRA types (dataset/t2/EXTRA-MANIFEST.json, added 29 Oct);
* hf_s1.jsonl: a byte copy of MIX-hf_s1;
* dev_holdout.jsonl: the other dev items, the dev check of runs trained on train.jsonl;
* select_extra.jsonl / test_extra.jsonl: the select / test rows of the EXTRA types (held out, never trained on);
* manifest.json: every repair with its counts and before / after distributions, sha256 of inputs and outputs.
Unchanged rows are copied byte for byte; a repaired row is re-serialised in the file's own style (compact separators,
ensure_ascii=False, key order kept), with only option texts changed (REBALANCE) or options appended (PAD).

REBALANCE (shipping_rate, every variant but the zone one): most wrong options were cheaper than the correct answer, so
the answer sat at a fixed position among the options sorted by value (courier: 4th cheapest in 54 %, never cheapest),
a shortcut the dev items do not have. Each item gets a target position drawn from the dev items' distribution
(sha256 of the id); wrong options d are replaced by their mirror 2 x gold - d (the same error size on the other side)
until the answer sits there. The question, the answer and its text stay as they are.
PAD (next_api / tool_retrieval, the gen-1 rows with 8-26 options): options appended up to PAD_TO = 26, what the live eval
serves (FORMAT.md section 2: the gold option plus 25 sampled). New options come from other rows of the same source and
never name a resource that occurs in the item (its options or its text), so none of them can also be correct.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import sys
from decimal import Decimal

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ROOT)
from tools.select_mix import counts, read, stratified  # noqa: E402

T2 = os.path.join(ROOT, "dataset/t2")
DEV = os.path.join(ROOT, "eval-v5/devset-v1/dev.jsonl")
DEV_TRAIN_SHARE = 0.5

REBALANCE = {"shipping_rate": ("own_gen-1_shipping_rate", "own_t2_shipping_rate_air", "own_t2_shipping_rate_courier",
                               "own_t2_shipping_rate_gen", "own_t2_shipping_rate_pallet", "own_t2_shipping_rate_postal")}
PAD = {"next_api": ("own_gen-1_next_api",), "tool_retrieval": ("own_gen-1_tool_retrieval",)}
PAD_TO = 26
VERBS = ("archive", "cancel", "create", "delete", "export", "get", "list", "update")
REFILL = {"tool_call_decision": "own_gen-1_tool_call_decision"}   # unused t2 rows of the type, as many questions as it has
MONEY = re.compile(r"^([A-Z]{3}) ([\d,]+(?:\.\d+)?)$")
EXTRA = ("congress_bill_status", "ghsa_severity", "ntrs_subject_category", "ntsb_injury_severity", "ted_cpv_division",
         "asf_podling_outcome", "insurance_payout", "loan_approval", "warranty_claim", "coupon_stacking", "library_fine",
         "toll_charge", "building_permit_fee", "sla_credit", "arxiv_category_api", "wildguard_aegis")   # file stems in dataset/t2


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def frac(*parts) -> float:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16) / 2 ** 256


def dump(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"


# ------------------------------------------------------------------------------------------------------------- rebalance
def money(text: str) -> tuple[str, Decimal, int] | None:
    m = MONEY.match(text)
    if not m:
        return None
    num = m.group(2)
    return m.group(1), Decimal(num.replace(",", "")), len(num.split(".")[1]) if "." in num else 0


def fmt(cur: str, v: Decimal, decimals: int) -> str:
    return f"{cur} {v:,.{decimals}f}"          # thousands separator: every value >= 1000 in t2 has one


def position(q: dict) -> int | None:
    """1-based position of the gold option among the options sorted by value (None: not all money)."""
    vals = {k: money(t) for k, t in q["criteria"].items()}
    if None in vals.values():
        return None
    g = vals[q["expected"]][1]
    return 1 + sum(v[1] < g for k, v in vals.items() if k != q["expected"])


def nearest_mean(q: dict) -> bool | None:
    vals = {k: money(t) for k, t in q["criteria"].items()}
    if None in vals.values():
        return None
    mean = sum(v[1] for v in vals.values()) / len(vals)
    return min(vals, key=lambda k: (abs(vals[k][1] - mean), k)) == q["expected"]


def dev_positions(dev: list) -> dict[int, collections.Counter]:
    """Gold positions of the dev items of each type in REBALANCE, by option count."""
    out: dict = collections.defaultdict(collections.Counter)
    for r, _ in dev:
        if r["task_type"] in REBALANCE:
            for q in r["questions"]:
                p = position(q)
                if p is not None:
                    out[r["task_type"]][p] += 1
    return out


def target(dist: collections.Counter, n_options: int, row_id: str) -> int:
    w = {p: c for p, c in dist.items() if p <= n_options}
    u, acc = frac("t2fix", "position", row_id) * sum(w.values()), 0
    for p in sorted(w):
        acc += w[p]
        if u < acc:
            return p
    return max(w)


def rebalance(row: dict, dist: collections.Counter) -> tuple[dict | None, str]:
    """(repaired row or None, outcome). Moves the gold to its target position by mirroring wrong options."""
    q = row["questions"][0]
    vals = {k: money(t) for k, t in q["criteria"].items()}
    if len(row["questions"]) != 1 or None in vals.values():
        return None, "not_money"
    cur, g, dec = vals[q["expected"]]
    want = target(dist, len(vals), row["id"]) - 1                     # wrong options that must stay below the gold
    below = [k for k in vals if k != q["expected"] and vals[k][1] < g]
    above = [k for k in vals if k != q["expected"] and vals[k][1] > g]
    move, side = (below, "up") if len(below) > want else (above, "down")
    need = abs(len(below) - want)
    if need == 0:
        return None, "at_target"
    taken = {v[1] for v in vals.values()}
    new = dict(q["criteria"])
    for k in sorted(move, key=lambda k: frac("t2fix", "mirror", row["id"], k)):
        if need == 0:
            break
        m = 2 * g - vals[k][1]
        if m <= 0 or m in taken:
            continue
        taken.discard(vals[k][1])
        taken.add(m)
        new[k] = fmt(cur, m, dec)
        need -= 1
    if new == q["criteria"]:
        return None, "no_valid_mirror"
    out = dict(row)
    out["questions"] = [dict(q, criteria=new)]
    return out, ("moved_" + side) if need == 0 else ("short_" + side)


# ------------------------------------------------------------------------------------------------------------------ pad
def op_name(text: str) -> str:
    return text.split(":", 1)[0].strip()


def resource(name: str) -> str:
    for v in VERBS:
        if name.startswith(v + "_"):
            name = name[len(v) + 1:]
            break
    return name[:-1] if name.endswith("s") else name


def pad(row: dict, pool: list[str]) -> tuple[dict | None, int]:
    """(row with options appended up to PAD_TO, options added). New options name no resource of the item."""
    q = row["questions"][0]
    keys = list(q["criteria"])
    if len(row["questions"]) != 1 or keys != [chr(65 + i) for i in range(len(keys))] or len(keys) >= PAD_TO:
        return None, 0
    text = q["instructions"].lower()
    have = set(q["criteria"].values())
    used = {resource(op_name(t)) for t in have}
    new = dict(q["criteria"])
    for cand in sorted(pool, key=lambda t: frac("t2fix", "pad", row["id"], t)):
        if len(new) >= PAD_TO:
            break
        res = resource(op_name(cand))
        if cand in have or res in used or res.replace("_", " ") in text or res in text:
            continue
        new[chr(65 + len(new))] = cand
        used.add(res)
    if len(new) == len(keys):
        return None, 0
    out = dict(row)
    out["questions"] = [dict(q, criteria=new)]
    return out, len(new) - len(keys)


def pools(rows: list) -> dict[tuple[str, str], list[str]]:
    """Option texts of every PAD source, deduplicated, from the given (training) rows."""
    out: dict = collections.defaultdict(set)
    for r, _ in rows:
        if r["source"] in PAD.get(r["task_type"], ()):
            for q in r["questions"]:
                out[(r["task_type"], r["source"])].update(q["criteria"].values())
    return {k: sorted(v) for k, v in out.items()}


def repair(rows: list, dist: dict, pool: dict) -> tuple[list, dict]:
    """Apply REBALANCE and PAD to (row, line) pairs; returns the new pairs and the counts of what was done."""
    done: dict = collections.defaultdict(collections.Counter)
    out = []
    for r, line in rows:
        new = None
        if r["source"] in REBALANCE.get(r["task_type"], ()):
            new, outcome = rebalance(r, dist[r["task_type"]])
            done[f"rebalance|{r['source']}"][outcome] += 1
        elif r["source"] in PAD.get(r["task_type"], ()):
            new, added = pad(r, pool[(r["task_type"], r["source"])])
            done[f"pad|{r['source']}"]["padded" if new else "unchanged"] += 1
            done[f"pad|{r['source']}"]["options_added"] += added
        out.append((new, dump(new)) if new else (r, line))
    return out, {k: dict(v) for k, v in done.items()}


def shortcut_stats(rows: list) -> dict[str, dict]:
    """Per REBALANCE source: gold position shares and the 'nearest to the mean' rate."""
    pos: dict = collections.defaultdict(collections.Counter)
    near: dict = collections.defaultdict(list)
    for r, _ in rows:
        if r["task_type"] in REBALANCE:
            for q in r["questions"]:
                p, m = position(q), nearest_mean(q)
                if p is not None:
                    pos[r["source"]][p] += 1
                    near[r["source"]].append(m)
    return {s: {"n": sum(c.values()), "position": {p: round(c[p] / sum(c.values()), 3) for p in sorted(c)},
                "nearest_mean": round(sum(near[s]) / len(near[s]), 3)} for s, c in sorted(pos.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = os.path.join(ROOT, a.out)
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"{a.out} exists and is not empty")
    mix = read(os.path.join(T2, "MIX-train.jsonl"))
    dev = read(DEV)
    dist = dev_positions(dev)
    fixed, done = repair(mix, dist, pools(mix))

    refill = []
    in_mix = {r["id"] for r, _ in mix}
    for tt, variant in REFILL.items():
        need = sum(len(r["questions"]) for r, _ in mix if r["task_type"] == tt and r["source"] == variant)
        spare = [x for x in read(os.path.join(T2, f"{tt}.train.jsonl")) if x[0]["id"] not in in_mix]
        spare.sort(key=lambda x: hashlib.sha256(f"refill|{tt}|{x[0]['id']}".encode()).hexdigest())
        got = 0
        for x in spare:
            if got >= need:
                break
            refill.append(x)
            got += len(x[0]["questions"])

    dev_train = stratified(dev, round(len(dev) * DEV_TRAIN_SHARE), "t2fix|dev")
    train_ids = {r["id"] for r, _ in dev_train}
    dev_hold = [x for x in dev if x[0]["id"] not in train_ids]

    extra = {s: [x for stem in EXTRA for x in read(os.path.join(T2, f"{stem}.{s}.jsonl"))] for s in ("train", "select", "test")}
    rows = fixed + refill + dev_train + extra["train"]
    ids = [r["id"] for r, _ in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{len(ids) - len(set(ids))} row ids twice")
    held = {r["id"] for s in ("select", "test") for r, _ in extra[s]}
    if held & set(ids):
        raise SystemExit("an EXTRA select / test row is also a train row")
    os.makedirs(out, exist_ok=True)
    for name, rs in (("train.jsonl", rows), ("dev_holdout.jsonl", dev_hold), ("select_extra.jsonl", extra["select"]),
                     ("test_extra.jsonl", extra["test"])):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.writelines(line for _, line in sorted(rs, key=lambda x: x[0]["id"]))
    shutil.copyfile(os.path.join(T2, "MIX-hf_s1.jsonl"), os.path.join(out, "hf_s1.jsonl"))
    files = ("train.jsonl", "hf_s1.jsonl", "dev_holdout.jsonl", "select_extra.jsonl", "test_extra.jsonl")
    before, after = counts(mix, "task_type"), counts(rows, "task_type")
    manifest = {
        "rule": "every MIX-train row (REBALANCE / PAD repairs) plus REFILL plus dev_train; hf_s1 = MIX-hf_s1; see tools/build_t2fix.py",
        "rebalance": {"sources": REBALANCE, "dev_positions": {t: dict(sorted(c.items())) for t, c in dist.items()},
                      "method": "target position from the dev distribution (sha256 of the id); wrong options d -> 2 x gold - d"},
        "pad": {"sources": PAD, "to": PAD_TO, "method": "options of other rows of the same source; no resource of the item"},
        "repairs": done,
        "shortcut_before": shortcut_stats(mix), "shortcut_after": shortcut_stats(fixed),
        "shortcut_dev": shortcut_stats([x for x in dev if x[0]["task_type"] in REBALANCE]),
        "refill_rows": len(refill), "refill_questions": sum(len(r["questions"]) for r, _ in refill),
        "dev_train": len(dev_train), "dev_holdout": len(dev_hold), "dev_train_by_type": counts(dev_train, "task_type"),
        "extra": {"types": EXTRA, "rows": {s: len(v) for s, v in extra.items()},
                  "train_by_task_type": counts(extra["train"], "task_type")},
        "train": {"rows": len(rows), "questions": sum(len(r["questions"]) for r, _ in rows),
                  "by_task_type": {k: {"before": before.get(k, 0), "after": after.get(k, 0)} for k in sorted(set(before) | set(after))}},
        "inputs_sha256": {os.path.relpath(p, ROOT): sha(p) for p in (os.path.join(T2, "MIX-train.jsonl"), os.path.join(T2, "MIX-hf_s1.jsonl"),
                                                                      os.path.join(T2, "tool_call_decision.train.jsonl"), DEV)
                                                                      + tuple(os.path.join(T2, f"{e}.{s}.jsonl") for e in EXTRA for s in ("train", "select", "test"))},
        "outputs_sha256": {n: sha(os.path.join(out, n)) for n in files},
    }
    with open(os.path.join(out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(json.dumps({k: manifest[k] for k in ("repairs", "shortcut_dev", "shortcut_before", "shortcut_after", "refill_rows",
                                               "refill_questions", "dev_train", "dev_holdout")}, indent=1))
    print("train:", manifest["train"]["rows"], "rows,", manifest["train"]["questions"], "questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
