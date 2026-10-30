"""The declared base's own answer distributions on a stage's training rows: the target of the KL-to-base term in train.py.

    python -m tools.train_generalist.teacher --base /models/mammoth-1 --prepared prepared/stage1

Inference only (nothing is trained): the base without any adapter, on the validator's numeric path (``common.answer_logits``:
bidirectional full attention, last prompt position x readout, softmax at T = 2), over every row of
``<prepared>/train.jsonl.gz``. Writes ``teacher.jsonl.gz`` (``{"id", "p"}`` in row order; ``p`` null for a row that was not
run) and ``teacher.meta.json`` (base, tokenizer, content digest of the rows). Every stage, also a continued one, is
regularised towards the declared base, never towards the previous stage.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from reax_subnet.spec import prompt as P

from . import common as C


def teacher_meta(base: str, prepared: str, fraction: float = 1.0) -> dict:
    return {"base": os.path.realpath(base), "tokenizer": C.tokenizer_digest(base),
            "rows_digest": C.content_digest(os.path.join(prepared, "train.jsonl.gz")), "fraction": float(fraction)}


def in_sample(row_id: str, fraction: float) -> bool:
    """The fixed sample of rows that get the base's answers (and so the KL term): sha256 of the row id below ``fraction``."""
    import hashlib
    return fraction >= 1.0 or int.from_bytes(hashlib.sha256(f"kl|{row_id}".encode()).digest()[:8], "big") / 2 ** 64 < fraction


def check(base: str, prepared: str, fraction: float = 1.0) -> str | None:
    """None if ``<prepared>/teacher.*`` belongs to these rows and this base, else the reason it does not."""
    mp = os.path.join(prepared, "teacher.meta.json")
    if not os.path.exists(mp) or not os.path.exists(os.path.join(prepared, "teacher.jsonl.gz")):
        return "no teacher file"
    have, want = C.read_json(mp), teacher_meta(base, prepared, fraction)
    have.setdefault("fraction", 1.0)
    bad = [k for k in want if have.get(k) != want[k]]
    return f"teacher made for another {', '.join(bad)}" if bad else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--fraction", type=float, default=1.0, help="answer only this fixed share of the rows (the KL sample)")
    a = ap.parse_args(argv)
    rows = list(C.read_jsonl(os.path.join(a.prepared, "train.jsonl.gz")))
    meta = teacher_meta(a.base, a.prepared, a.fraction)
    tmeta = C.read_json(os.path.join(a.prepared, "train.meta.json"))
    if tmeta.get("tokenizer") != meta["tokenizer"]:
        raise SystemExit(f"{a.prepared} was rendered with another tokenizer than {a.base}")
    t0 = time.time()
    model, weight, _ = C.load_backbone(a.base, a.device)
    model.eval()
    picked = [i for i, r in enumerate(rows) if in_sample(r["id"], a.fraction)]
    zs = [None] * len(rows)
    for i, z in zip(picked, C.answer_logits(model, weight, [rows[i] for i in picked])):
        zs[i] = z
    secs = time.time() - t0
    out = [{"id": r["id"], "p": None if z is None else P.softmax_t(z)} for r, z in zip(rows, zs)]
    C.write_jsonl(os.path.join(a.prepared, "teacher.jsonl.gz"), out)
    failed = sum(zs[i] is None for i in picked)
    tokens = sum(len(rows[i]["ids"]) for i in picked)
    agree = sum(1 for r, z in zip(rows, zs) if z is not None and max(range(len(z)), key=z.__getitem__) == r["gold"])
    meta.update(rows=len(rows), answered=len(picked) - failed, failed=failed, tokens=tokens, seconds=round(secs, 1),
                base_right=round(agree / max(1, len(picked) - failed), 4))
    C.write_json(os.path.join(a.prepared, "teacher.meta.json"), meta)
    print(f"teacher: {len(picked)} of {len(rows)} rows (fraction {a.fraction}), {failed} not run, {tokens} tokens in {secs:.0f} s "
          f"({tokens / max(secs, 1e-9):.0f} tok/s incl. load); base argmax = gold on {meta['base_right']:.2%} of the rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
