"""Did a stage really change and improve the model?

    stage_check eval    --base DIR [--adapter CKPT] --prepared prepared/eval --label NAME --out reports/NAME.json
    stage_check compare --stage stage2 --prev stage1 [--reports reports] [--prepared prepared/eval]
    stage_check weights --adapter CKPT [--prev-adapter CKPT] [--merged DIR --base DIR]

``eval`` without ``--adapter`` runs the validator's own ``spec.joint.JointRunner`` on the model directory (bit for bit the
serving path); with ``--adapter`` it runs the same numeric path (``common.decide``) on the base plus the LoRA checkpoint.
Both score the test split and the select split (``--splits test`` for one; ``--sample N`` scores a fixed random subset
of N items per split, the same subset for every model, so two models scored with the same N compare item by item).

``compare`` verdict on the test split (vs ``--prev``), with the stage config's ``checks`` (``--config``): ``learn`` = the
sources the stage trains towards, ``transfer`` = the v5.1-format sources it must not lose (default: s1 sources learn,
typed sources transfer):
* NOT UPDATED: no test item changed its result.
* TRANSFER LOSS: a transfer source's paired gain is below 0.
* REGRESSION: a task type with >= 40 items, or a non-transfer source, is more than 2 points and 2 SE below.
* NO GAIN: a learn source's paired gain is <= 0 or <= 2 SE.
* IMPROVED otherwise.
With ``reports/champion.json`` present a submit line follows: CANDIDATE only when the verdict is IMPROVED, the stage beats
the champion on ``transfer`` (all v5.1-format items pooled) by max(--min-gain, 2 SE), and no s1 source is behind the
champion by more than 2 SE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from typing import Any

from . import common as C
from . import scoring as SC

EVAL_SPLITS = ("test", "select")


def _digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_split(prepared: str, split: str):
    ip = os.path.join(prepared, f"{split}.items.jsonl.gz")
    if not os.path.exists(ip):
        return None
    return list(C.read_jsonl(ip)), _digest(ip)


# ---------------------------------------------------------------------------------------------------------------- eval

def cmd_eval(a) -> int:
    import time
    splits = {s: _load_split(a.prepared, s) for s in EVAL_SPLITS}
    splits = {s: v for s, v in splits.items() if v is not None}
    if "test" not in splits:
        raise SystemExit(f"{a.prepared}: no test split")
    if a.splits:
        splits = {s: v for s, v in splits.items() if s in a.splits.split(",")}
    t0 = time.time()
    if a.adapter:
        from peft import PeftModel
        model, weight, _ = C.load_backbone(a.base)
        model = PeftModel.from_pretrained(model, a.adapter).eval()
        run = lambda rows: C.decide(model, weight, rows)
    else:
        from reax_subnet.spec.joint import JointRunner
        runner = JointRunner.load(a.base)

        def run(rows):
            # JointRunner renders the served rows itself, exactly as on the validator.
            return runner.decide([_served_row(r, items_by_id) for r in rows])
    load_s = time.time() - t0
    from . import data as D
    tok = C.load_tokenizer(a.base)
    report: dict[str, Any] = {"label": a.label, "base": os.path.abspath(a.base),
                              "adapter": os.path.abspath(a.adapter) if a.adapter else None,
                              "path": "adapter (common.decide)" if a.adapter else "JointRunner", "load_s": round(load_s, 1),
                              "tokenizer": C.tokenizer_digest(a.base), "splits": {}}
    for split, (items, digest) in splits.items():
        if a.max_items:
            items = items[: a.max_items]
        if a.sample and len(items) > a.sample:     # seeded by the split only: the same items for every model
            keep = {it["id"] for it in random.Random(f"stage_check|{split}").sample(items, a.sample)}
            items = [it for it in items if it["id"] in keep]
        rows = D.render_rows(items, tok)       # this model's own tokenizer
        items_by_id = {it["id"]: it for it in items}
        t1 = time.time()
        probs = run(rows)
        secs = time.time() - t1
        resp = SC.responses_by_item(rows, probs)
        res = SC.score(items, resp)
        tokens = sum(len(r["ids"]) for r in rows)
        res.update(prepared_digest=digest, seconds=round(secs, 1), tokens=tokens, tok_s=round(tokens / max(secs, 1e-9)))
        res["responses"] = resp
        report["splits"][split] = res
        print(f"{a.label} {split}: local {res['local']:.2f}  dev_v51 {res['dev_v51'] if res['dev_v51'] is None else round(res['dev_v51'], 2)}"
              f"  item acc {res['item_accuracy']:.4f}  failed {res['failed_questions']}  {secs:.0f} s ({res['tok_s']} tok/s)",
              flush=True)
    C.write_json(a.out, report)
    return 0


def _served_row(r: dict, items_by_id: dict) -> dict:
    """The ``v5wire.flatten`` row of a prepared row (JointRunner input)."""
    from reax_subnet.spec import v5wire
    it = items_by_id[r["item"]]
    j = int(r["id"].rsplit("#", 1)[1])
    flat = v5wire.flatten([dict(it, questions=[it["questions"][j]])])[0]
    return dict(flat, id=r["id"])


# ------------------------------------------------------------------------------------------------------------- compare

def _report(reports: str, label: str) -> dict:
    p = os.path.join(reports, f"{label}.json")
    if not os.path.exists(p):
        raise SystemExit(f"missing report {p} (run stage_check eval --label {label})")
    return C.read_json(p)


def _behind(groups: dict, min_items: int = SC.MIN_GROUP_ITEMS) -> list[str]:
    return [g for g, v in groups.items() if v["items"] >= min_items and v["gain"] is not None and v["se"] is not None
            and v["gain"] < -2.0 and v["gain"] < -2 * v["se"]]


def stage_checks(config: str | None, items: list) -> tuple[list[str], list[str]]:
    """(learn, transfer) sources of a stage, restricted to the sources the test split has. From the stage config's
    ``checks`` block; without one: the s1 sources learn, the typed (v5.1-format) sources are transfer."""
    srcs = SC._sources(items)
    present = {s.name for s in srcs}
    ch = (C.read_json(config).get("checks") or {}) if config else {}
    learn = ch.get("learn", [s.name for s in srcs if not s.typed])
    transfer = ch.get("transfer", [s.name for s in srcs if s.typed])
    return [s for s in learn if s in present], [s for s in transfer if s in present]


def _fmt(x: float | None, sign: bool = True) -> str:
    return "-" if x is None else (f"{x:+.2f}" if sign else f"{x:.2f}")


def cmd_compare(a) -> int:
    items = list(C.read_jsonl(os.path.join(a.prepared, "test.items.jsonl.gz")))
    digest = _digest(os.path.join(a.prepared, "test.items.jsonl.gz"))
    cur, prev = _report(a.reports, a.stage), _report(a.reports, a.prev)
    earlier = [lab for lab in (a.earlier or "").split(",") if lab]
    for r in [cur, prev] + [_report(a.reports, e) for e in earlier]:
        if r["splits"]["test"]["prepared_digest"] != digest:
            raise SystemExit(f"report {r['label']} was scored on another test split; re-score it (never change the test split)")
    learn, transfer = stage_checks(a.config, items)
    resp = lambda r: r["splits"]["test"]["responses"]
    pc = SC.paired(items, resp(cur), resp(prev), transfer_sources=transfer)
    base = _report(a.reports, "base") if os.path.exists(os.path.join(a.reports, "base.json")) else None
    pb = SC.paired(items, resp(cur), resp(base), transfer_sources=transfer) if base and a.prev != "base" else (pc if base else None)
    cols = (["base"] if base and a.prev != "base" else []) + earlier + [a.prev, a.stage]
    scores = {lab: SC.score(items, resp(_report(a.reports, lab)), transfer_sources=transfer) for lab in cols}
    print(f"\n{a.stage} vs {a.prev} on the test split ({len(items)} items, {pc['changed_items']} changed results)")
    hdr = f"{'group':40s} {'n':>5s} " + " ".join(f"{c[:10]:>10s}" for c in cols) + f" {'delta':>7s} {'SE':>5s}"
    print(hdr)

    def row(name, v, vals):
        cells = " ".join("         -" if x is None else f"{x:10.2f}" for x in vals)
        gain = "      -" if v["gain"] is None else f"{v['gain']:+7.2f}"
        print(f"{name[:40]:40s} {v['items']:5d} {cells} {gain} {(v['se'] or 0):5.2f}")

    print("-" * len(hdr) + "\nper task type")
    for g in sorted(pc["groups"]):
        row(g, pc["groups"][g], [scores[c]["groups"].get(g) for c in cols])
    print("-" * len(hdr) + "\nper source")
    for s in sorted(pc["sources"]):
        row(s, pc["sources"][s], [scores[c]["sources"].get(s) for c in cols])
    row("TRANSFER (the transfer sources pooled)", pc["transfer"], [scores[c]["transfer"] for c in cols])
    row("LOCAL (mean over sources)", pc["local"], [scores[c]["local"] for c in cols])

    src = pc["sources"]
    no_gain = [s for s in learn if src[s]["gain"] is None or src[s]["gain"] <= 0 or src[s]["gain"] <= 2 * (src[s]["se"] or 0)]
    lost = [s for s in transfer if src[s]["gain"] is not None and src[s]["gain"] < 0]
    behind = _behind(pc["groups"]) + _behind({k: v for k, v in src.items() if k not in transfer})
    print(f"\nchecks ({'config ' + a.config if a.config else 'defaults'}):")
    for s in learn:
        v = src[s]
        print(f"  learn    {s}: gain {_fmt(v['gain'])} vs 2 SE {2 * (v['se'] or 0):.2f} -> {'FAIL' if s in no_gain else 'ok'}")
    for s in transfer:
        v = src[s]
        print(f"  transfer {s}: gain {_fmt(v['gain'])} (SE {(v['se'] or 0):.2f}), must be >= 0 -> {'FAIL' if s in lost else 'ok'}")
    print(f"  regression (>= {SC.MIN_GROUP_ITEMS} items, > 2 points and 2 SE below): {', '.join(behind) or 'none'}")
    if pc["changed_items"] == 0:
        verdict, why = "NOT UPDATED", "no test item changed its result"
    elif lost:
        verdict, why = "TRANSFER LOSS", "below the previous stage on: " + ", ".join(lost)
    elif behind:
        verdict, why = "REGRESSION", "behind: " + ", ".join(behind)
    elif no_gain or not learn:
        verdict, why = "NO GAIN", ("no gain > 2 SE on: " + ", ".join(no_gain)) if learn else "no learn source in the test split"
    else:
        verdict, why = "IMPROVED", "learn sources > 2 SE, transfer sources not below, no regression"
    print(f"\nVERDICT {a.stage}: {verdict} ({why})")
    out: dict[str, Any] = {"stage": a.stage, "prev": a.prev, "verdict": verdict, "reason": why, "learn": learn,
                           "transfer": transfer, "vs_prev": pc, "vs_base": pb, "test_digest": digest}
    champ_p = os.path.join(a.reports, "champion.json")
    if os.path.exists(champ_p):
        ch = C.read_json(champ_p)
        if ch["splits"]["test"]["prepared_digest"] != digest:
            raise SystemExit("champion report was scored on another test split")
        pch = SC.paired(items, resp(cur), resp(ch), transfer_sources=transfer)
        t = pch["transfer"]
        tg, tse = t["gain"], t["se"] or 0.0
        bar = max(a.min_gain, 2 * tse)
        typed = {s.name for s in SC._sources(items) if s.typed}
        clearly_behind = [s for s, v in pch["sources"].items() if s not in typed and v["gain"] is not None
                          and v["gain"] < -2 * (v["se"] or 0)]
        ok = verdict == "IMPROVED" and tg is not None and tg >= bar and not clearly_behind
        line = (f"SUBMIT {a.stage}: {'CANDIDATE' if ok else 'NOT A CANDIDATE'} vs champion {ch['label']}: "
                f"transfer gain {_fmt(tg)} (SE {tse:.2f}, bar {bar:.2f}), local gain {_fmt(pch['local']['gain'])}"
                + (f", clearly behind on: {', '.join(clearly_behind)}" if clearly_behind else "")
                + ("" if verdict == "IMPROVED" else f", verdict {verdict}"))
        out.update(vs_champion=pch, submit="CANDIDATE" if ok else "NOT A CANDIDATE", submit_line=line)
        print(line)
    else:
        print("SUBMIT: no reports/champion.json yet (stage_check eval --base <champion dir> --label champion)")
    C.write_json(os.path.join(a.reports, f"{a.stage}.compare.json"), out)
    return 0


# ------------------------------------------------------------------------------------------------------------- weights

def _lora_tensors(path: str) -> dict:
    from safetensors.torch import load_file
    return load_file(os.path.join(path, "adapter_model.safetensors"))


def cmd_weights(a) -> int:
    import torch
    problems: list[str] = []
    cur = _lora_tensors(a.adapter)
    bs = [k for k in cur if "lora_B" in k]
    nb = sum(float(cur[k].float().norm() ** 2) for k in bs) ** 0.5
    print(f"adapter {a.adapter}: {len(cur)} tensors, |B| = {nb:.4g}")
    if nb == 0.0:
        problems.append("adapter is zero (lora_B all zero): no update")
    if a.prev_adapter:
        prev = _lora_tensors(a.prev_adapter)
        if set(prev) != set(cur):
            problems.append("adapter tensor names differ from the previous stage")
        else:
            d = sum(float((cur[k].float() - prev[k].float()).norm() ** 2) for k in cur) ** 0.5
            n = sum(float(prev[k].float().norm() ** 2) for k in prev) ** 0.5
            print(f"moved since {a.prev_adapter}: |delta| = {d:.4g} (relative {d / max(n, 1e-12):.4g})")
            if d == 0.0:
                problems.append("adapter did not move since the previous stage")
    if a.merged:
        from . import export as E
        problems += E.check_merged(a.merged, a.base, a.adapter, samples=a.samples)
    if problems:
        print("WEIGHT CHECK: PROBLEMS\n  " + "\n  ".join(problems))
        return 1
    print("WEIGHT CHECK: OK (no problems)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--base", required=True)
    e.add_argument("--adapter")
    e.add_argument("--prepared", default="prepared/eval")
    e.add_argument("--label", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--max-items", type=int, default=None, help="score only the first N items of each split (smoke tests)")
    e.add_argument("--sample", type=int, default=None, help="score a fixed random subset of N items of each split")
    e.add_argument("--splits", default=None, help="comma-separated splits to score (default: test and select)")
    c = sub.add_parser("compare")
    c.add_argument("--stage", required=True)
    c.add_argument("--prev", required=True)
    c.add_argument("--earlier", default="", help="comma-separated earlier stage labels to show as columns")
    c.add_argument("--reports", default="reports")
    c.add_argument("--prepared", default="prepared/eval")
    c.add_argument("--config", default=None, help="the stage config (its checks block); default: s1 learn, typed transfer")
    c.add_argument("--min-gain", type=float, default=1.0, help="champion margin floor (eval v5.1: 1.0)")
    w = sub.add_parser("weights")
    w.add_argument("--adapter", required=True)
    w.add_argument("--prev-adapter")
    w.add_argument("--merged")
    w.add_argument("--base")
    w.add_argument("--samples", type=int, default=24)
    a = ap.parse_args(argv)
    return {"eval": cmd_eval, "compare": cmd_compare, "weights": cmd_weights}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
