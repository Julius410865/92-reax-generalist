"""Score merges of a full model and a LoRA checkpoint: model + w * (LoRA delta), for several w, in GPU memory.

    python -m tools.train_generalist.merge_eval --model /models/danyloooah-core2 --adapter runs/train_50k/ckpt-521 \
        --weights 0.5,0.75,1.0 --prepared prepared/eval_all --reports reports_all --label core2+train_50k

The model is loaded by the validator's own ``JointRunner`` (its readout head is kept) and every LoRA target is replaced by
``(W.float() + w * (alpha / r) * B @ A).to(W.dtype)``, the formula ``export`` writes to disk, so a later export of the
chosen w serves the same weights. Each merge is scored like ``stage_check eval`` (test and select splits) into
``<reports>/<label>-w<w>.json``. Nothing is written to the model directory.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import common as C
from . import data as D
from . import export as E
from . import scoring as SC
from . import stage_check as S


def merged_runner(model_dir: str, adapter: str, w: float):
    import torch
    from reax_subnet.spec.joint import JointRunner
    runner = JointRunner.load(model_dir)
    deltas, scale = E.lora_deltas(adapter)
    params = dict(runner.model.named_parameters())
    missing = [k for k in deltas if k not in params]
    if missing:
        raise SystemExit(f"adapter targets tensors the model does not have: {missing[:3]}")
    with torch.no_grad():
        for k, (a, b) in deltas.items():
            p = params[k]
            p.copy_(E.merged_tensor(p, a.to(p.device), b.to(p.device), scale * w))
    return runner, len(deltas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--weights", default="0.5,0.75,1.0")
    ap.add_argument("--prepared", default="prepared/eval_all")
    ap.add_argument("--reports", default="reports_all")
    ap.add_argument("--label", required=True)
    a = ap.parse_args(argv)
    splits = {s: v for s in S.EVAL_SPLITS if (v := S._load_split(a.prepared, s)) is not None}
    for w in (float(x) for x in a.weights.split(",")):
        out = os.path.join(a.reports, f"{a.label}-w{w:g}.json")
        if os.path.exists(out):
            print(f"w {w:g}: {out} exists, skipped", flush=True)
            continue
        t0 = time.time()
        runner, n = merged_runner(a.model, a.adapter, w)
        print(f"w {w:g}: {n} tensors merged into {a.model} in {time.time() - t0:.0f} s", flush=True)
        report = {"label": f"{a.label}-w{w:g}", "base": os.path.abspath(a.model), "adapter": os.path.abspath(a.adapter),
                  "merge_weight": w, "path": "JointRunner (merged in memory)", "tokenizer": C.tokenizer_digest(a.model),
                  "splits": {}}
        for split, (items, digest) in splits.items():
            rows = D.render_rows(items, runner.tokenizer)
            items_by_id = {it["id"]: it for it in items}
            t1 = time.time()
            probs = runner.decide([S._served_row(r, items_by_id) for r in rows])
            secs = time.time() - t1
            resp = SC.responses_by_item(rows, probs)
            res = SC.score(items, resp)
            res.update(prepared_digest=digest, seconds=round(secs, 1), responses=resp)
            report["splits"][split] = res
            dev = res["dev_v51"]
            print(f"w {w:g} {split}: local {res['local']:.2f}  dev_v51 {dev if dev is None else round(dev, 2)}  "
                  f"item acc {res['item_accuracy']:.4f}  failed {res['failed_questions']}  {secs:.0f} s", flush=True)
        C.write_json(out, report)
        del runner
        __import__("torch").cuda.empty_cache()
    return 0


if __name__ == "__main__":
    sys.exit(main())
