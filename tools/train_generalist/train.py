"""LoRA training through the validator's joint readout.

    python -m tools.train_generalist.train --config data/stages/stage1.json --prepared prepared/stage1 \
        --eval prepared/eval --out runs/stage1 [--init-adapter runs/stage0/ckpt-N]

Each training row is one served question (``data.prepare_train``): one sequence, the full-attention mask hook of
``spec.joint``, the hidden state at the last prompt position, the frozen readout head, logits of the question's options
divided by the readout temperature (2), cross-entropy against the gold option with label smoothing, plus
``kl_to_base`` x KL(p_base || p_model) towards the declared base's own answer distribution (``teacher.py``; weight from the
stage config's ``train.kl_to_base``, ``--kl-weight`` overrides, 0 = off). Each question weighs the same in its step. Sequences are never
padded or packed (the validator batches equal lengths only); gradients accumulate over ``--batch-rows`` questions (or ``--batch-tokens``) per optimizer
step. LoRA sits on the language model's projections; the vision tower and the readout head stay frozen.

Every ``--eval-every`` steps (and at the end) the adapter is saved as ``ckpt-<step>`` and scored on the select split
(``scoring.score``: ``local``); ``best.json`` names the best checkpoint. ``log.jsonl`` has one line per step and per eval.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from typing import Any

from reax_subnet.spec import prompt as P

from . import common as C
from . import scoring as SC

EMA = 0.9                # weight of the history in the logged moving averages
TARGETS = r"language_model\.layers\.\d+\.(self_attn\.(q_proj|k_proj|v_proj|o_proj)|linear_attn\.(in_proj_qkv|in_proj_z|out_proj)|mlp\.(gate_proj|up_proj|down_proj))"


def lora_model(model, args):
    from peft import LoraConfig, PeftModel, get_peft_model
    if args.init_adapter:
        return PeftModel.from_pretrained(model, args.init_adapter, is_trainable=True)
    cfg = LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout, target_modules=TARGETS, bias="none")
    return get_peft_model(model, cfg)


def micro_batches(group: list[dict], size: int, max_tokens: int) -> list[list[dict]]:
    """The questions of one optimizer step in GPU passes of up to ``size`` sequences of similar length, at most
    ``max_tokens`` padded tokens each (size 1 = one question per pass, the unpadded path)."""
    rows = sorted(group, key=lambda r: len(r["ids"]))
    out, cur = [], []
    for r in rows:
        if cur and (len(cur) >= size or len(r["ids"]) * (len(cur) + 1) > max_tokens):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def lr_at(step: int, total: int, args) -> float:
    warm = max(1, int(args.warmup * total))
    if step < warm:
        return args.lr * (step + 1) / warm
    p = (step - warm) / max(1, total - warm)
    return args.lr_min + 0.5 * (args.lr - args.lr_min) * (1 + math.cos(math.pi * min(1.0, p)))


def batches(rows: list[dict], budget: int, by_rows: bool = False) -> list[list[dict]]:
    """Optimizer-step groups: ``budget`` questions each (``by_rows``), else ``budget`` tokens."""
    out, cur, n = [], [], 0
    for r in rows:
        cur.append(r)
        n += 1 if by_rows else len(r["ids"])
        if n >= budget:
            out.append(cur)
            cur, n = [], 0
    if cur:
        out.append(cur)
    return out


def evaluate(model, weight, ev: dict[str, Any], args) -> dict[str, Any]:
    model.eval()
    probs = C.decide(model, weight, ev["rows"])
    model.train()
    res = SC.score(ev["items"], SC.responses_by_item(ev["rows"], probs))
    return {k: res[k] for k in ("local", "item_accuracy", "failed_questions", "items")}


def load_eval(path: str, split: str, limit: int | None, tok) -> dict[str, Any] | None:
    """The prepared eval items (fixed) and their rows rendered with this model's tokenizer."""
    from . import data as D
    ip = os.path.join(path, f"{split}.items.jsonl.gz")
    if not os.path.exists(ip):
        return None
    items = list(C.read_jsonl(ip))
    if limit and len(items) > limit:
        keep = set(it["id"] for it in random.Random("evalsub").sample(items, limit))
        items = [it for it in items if it["id"] in keep]
    return {"items": items, "rows": D.render_rows(items, tok)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--eval", default="prepared/eval")
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default=None, help="model dir (default: the config's base)")
    ap.add_argument("--init-adapter", default=None, help="continue this LoRA checkpoint (fresh optimizer)")
    ap.add_argument("--rank", type=int, default=32)
    ap.add_argument("--alpha", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--lr", type=float, default=2.5e-5)
    ap.add_argument("--lr-min", type=float, default=1e-5)
    ap.add_argument("--warmup", type=float, default=0.05)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--label-smoothing", type=float, default=0.05)
    ap.add_argument("--kl-weight", type=float, default=None, help="KL-to-base weight (default: the config's train.kl_to_base, else 0)")
    ap.add_argument("--batch-rows", type=int, default=96, help="questions per optimizer step (each weighs the same)")
    ap.add_argument("--batch-tokens", type=int, default=None, help="instead of --batch-rows: tokens per optimizer step")
    ap.add_argument("--micro-batch", type=int, default=1, help="questions per GPU pass, right-padded (1 = unpadded)")
    ap.add_argument("--micro-tokens", type=int, default=8192, help="max padded tokens per GPU pass")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--eval-max", type=int, default=800, help="score a fixed random subset of N select items per eval (0 = all)")
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--keep-all", action="store_true", help="keep every checkpoint (default: the best and the latest)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    # the config's train block sets the defaults of the flags it names (micro_batch, eval_every, lr, ...); a flag given
    # on the command line still wins. kl_to_base / kl_fraction are read below.
    known = {act.dest for act in ap._actions}
    cfg_train = (C.read_json(ap.parse_known_args(argv)[0].config).get("train") or {})
    unknown = sorted(k for k in cfg_train if k not in known and k not in ("kl_to_base", "kl_fraction"))
    if unknown:
        ap.error(f"config train block: unknown settings {unknown}")
    ap.set_defaults(**{k: v for k, v in cfg_train.items() if k in known})
    a = ap.parse_args(argv)

    import torch
    torch.manual_seed(a.seed)
    cfg = C.read_json(a.config)
    base = a.base or cfg["base"]
    os.makedirs(a.out, exist_ok=True)
    log_path = os.path.join(a.out, "log.jsonl")
    rows = list(C.read_jsonl(os.path.join(a.prepared, "train.jsonl.gz")))
    if not rows:
        raise SystemExit("no training rows")
    tmeta = C.read_json(os.path.join(a.prepared, "train.meta.json"))
    if tmeta.get("tokenizer") != C.tokenizer_digest(base):
        raise SystemExit(f"{a.prepared} was rendered with another tokenizer ({tmeta.get('tokenizer')}) than {base} "
                         f"({C.tokenizer_digest(base)}): prepare it again for this base")
    tok = C.load_tokenizer(base)
    kl_w = a.kl_weight if a.kl_weight is not None else float((cfg.get("train") or {}).get("kl_to_base", 0.0))
    kl_frac = float((cfg.get("train") or {}).get("kl_fraction", 1.0))      # KL on this fixed share of the rows
    teacher: dict[str, Any] = {}
    if kl_w > 0:
        from . import teacher as TE
        why = TE.check(base, a.prepared, kl_frac)
        if why:
            raise SystemExit(f"KL-to-base needs the base's answers on these rows ({why}): "
                             f"python -m tools.train_generalist.teacher --base {base} --prepared {a.prepared} --fraction {kl_frac}")
        trows = list(C.read_jsonl(os.path.join(a.prepared, "teacher.jsonl.gz")))
        if [t["id"] for t in trows] != [r["id"] for r in rows]:
            raise SystemExit("teacher rows do not match the training rows")
        teacher = {id(r): t["p"] for r, t in zip(rows, trows)}
    reps = max(1, math.ceil(a.epochs))
    ordered = []
    for e in range(reps):
        r = rows[:]
        if e:
            random.Random(f"epoch|{a.seed}|{e}").shuffle(r)
        ordered += r
    ordered = ordered[: int(len(rows) * a.epochs)]
    plan = batches(ordered, a.batch_tokens, False) if a.batch_tokens else batches(ordered, a.batch_rows, True)
    total = min(len(plan), a.max_steps) if a.max_steps else len(plan)
    ev = None if a.no_eval else load_eval(a.eval, "select", a.eval_max or None, tok)

    model, weight, info = C.load_backbone(base, a.device)
    model.requires_grad_(False)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    model = lora_model(model, a)
    trainable = [p for p in model.parameters() if p.requires_grad]
    n_train = sum(p.numel() for p in trainable)
    opt = torch.optim.AdamW(trainable, lr=a.lr, weight_decay=a.weight_decay, betas=(0.9, 0.999))
    wf = weight.float()
    temp = P.READOUT_TEMPERATURE
    start = time.time()
    meta = {"base": base, "init_adapter": a.init_adapter, "rows": len(ordered), "steps": total, "trainable_params": n_train,
            "tokens": sum(len(r["ids"]) for r in ordered), "kl_to_base": kl_w, "kl_fraction": kl_frac, "args": vars(a)}
    C.write_json(os.path.join(a.out, "train.meta.json"), meta)
    print(f"train: {len(ordered)} rows, {meta['tokens']} tokens, {total} steps, {n_train / 1e6:.1f} M trainable", flush=True)

    best: dict[str, Any] | None = None
    ema: dict[str, float] = {}
    tokens_done = 0

    def checkpoint(step: int) -> None:
        nonlocal best
        path = os.path.join(a.out, f"ckpt-{step}")
        model.save_pretrained(path)
        rec: dict[str, Any] = {"step": step, "path": path}
        if ev is not None:
            t0 = time.time()
            rec["select"] = evaluate(model, weight, ev, a)
            rec["eval_s"] = round(time.time() - t0, 1)
            if best is None or (rec["select"]["local"] or -1e9) > (best["select"]["local"] or -1e9):
                best = rec
        else:
            best = rec
        with open(log_path, "a") as fh:
            fh.write(__import__("json").dumps({"eval": rec}) + "\n")
        C.write_json(os.path.join(a.out, "best.json"), best)
        if not a.keep_all:          # ~0.8 GB each: keep the best and the latest only
            for d in os.listdir(a.out):
                p = os.path.join(a.out, d)
                if d.startswith("ckpt-") and p not in (best["path"], path):
                    __import__("shutil").rmtree(p)
        print(f"ckpt {step}: {rec.get('select')}", flush=True)

    model.train()
    for step in range(total):
        lr = lr_at(step, total, a)
        for g in opt.param_groups:
            g["lr"] = lr
        group = plan[step]
        ntok = sum(len(r["ids"]) for r in group)
        nrow = len(group)               # every question weighs the same (the score counts questions, not tokens)
        loss_sum, ce_sum, kl_sum, t0 = 0.0, 0.0, 0.0, time.time()
        for mb in micro_batches(group, a.micro_batch, a.micro_tokens):
            h_all = C.last_hidden_padded(model, [r["ids"] for r in mb], a.device).float()
            mb_loss = 0.0
            for r, h in zip(mb, h_all):
                z = torch.nn.functional.linear(h[None], wf[: r["k"]]) / temp
                ce = torch.nn.functional.cross_entropy(z, torch.tensor([r["gold"]], device=a.device),
                                                       label_smoothing=a.label_smoothing)
                loss = ce
                p = teacher.get(id(r)) if kl_w > 0 else None
                if p is not None:
                    pt = torch.tensor([p], device=a.device, dtype=torch.float32)
                    kl = torch.sum(pt * (torch.log(pt.clamp_min(1e-12)) - torch.log_softmax(z, dim=-1)))
                    loss = ce + kl_w * kl
                    kl_sum += float(kl.detach())
                if not torch.isfinite(loss):
                    raise SystemExit(f"non-finite loss at step {step}, row {r['id']}")
                mb_loss = mb_loss + loss / nrow
                loss_sum += float(loss.detach())
                ce_sum += float(ce.detach())
            mb_loss.backward()
        gnorm = float(torch.nn.utils.clip_grad_norm_(trainable, 1.0))
        opt.step()
        opt.zero_grad(set_to_none=True)
        tokens_done += ntok
        dt = time.time() - t0
        rec = {"step": step + 1, "loss": loss_sum / nrow, "ce": ce_sum / nrow, "kl": kl_sum / nrow if kl_w > 0 else None,
               "lr": lr, "rows": nrow, "tokens": ntok, "grad_norm": gnorm,
               "tok_s": ntok / dt, "elapsed_s": round(time.time() - start, 1),
               "max_mem_gb": round(torch.cuda.max_memory_allocated() / 2 ** 30, 1) if a.device.startswith("cuda") else None}
        for k in ("loss", "ce", "kl"):          # moving averages: the trend, without the batch-to-batch noise
            if rec[k] is not None:
                ema[k] = rec[k] if k not in ema else EMA * ema[k] + (1 - EMA) * rec[k]
                rec[f"{k}_avg"] = ema[k]
        with open(log_path, "a") as fh:
            fh.write(__import__("json").dumps(rec) + "\n")
        if step % 5 == 0 or step + 1 == total:
            kl_txt = f" (ce {rec['ce']:.4f} kl {rec['kl']:.4f})" if kl_w > 0 else ""
            print(f"step {step + 1}/{total} loss {rec['loss']:.4f} (avg {rec['loss_avg']:.4f}){kl_txt} lr {lr:.2e} "
                  f"{rec['tok_s']:.0f} tok/s mem {rec['max_mem_gb']} GB", flush=True)
        if (step + 1) % a.eval_every == 0 and step + 1 < total:
            checkpoint(step + 1)
    checkpoint(total)
    meta.update(best=best, wall_s=round(time.time() - start, 1), tokens_done=tokens_done)
    C.write_json(os.path.join(a.out, "train.meta.json"), meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
