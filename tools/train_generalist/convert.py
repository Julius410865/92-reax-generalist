"""Repackage a Qwen3.5 causal checkpoint (``Qwen3_5ForConditionalGeneration``, e.g. baselabs/mammoth-1) into the joint-readout
layout the validator serves (``spec/joint.detect``): no weight value changes.

    python -m tools.train_generalist.convert --src /models/mammoth-1-hf --out /models/mammoth-1 \
        --base-id baselabs/mammoth-1@61cec44c281c693992e3d6ebeb44dd3402dfa186

* weights: tensor names ``model.X`` -> ``X`` (the ``Qwen3_5Model`` layout), ``lm_head.weight`` dropped; values and dtypes
  unchanged, same shard files.
* ``readout.safetensors``: the ``lm_head`` rows of 255 answer codes (A..Z, then the two-letter codes that are single tokens,
  as in reax-1.1), [255, hidden], unscaled (a uniform scale never changes the argmax the score reads).
* ``decision_config.json`` (format 2, noncausal full attention, last-position pooling, codes and their token ids in the
  checkpoint's own tokenizer, the base identity) and ``joint_config.json`` (``joint.JOINT_PROTOCOL``) added.
* ``config.json``: ``architectures`` = ``["Qwen3_5Model"]`` and ``language_model_only: false``; every other value unchanged.
* tokenizer files copied; the source's own serving code (``*.py``, patches, scripts) is not.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from reax_subnet.spec import joint as J
from reax_subnet.spec import v5

from . import common as C

N_CODES = 255
COPY = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "processor_config.json", "LICENSE", "NOTICE")
PREFIX = "model."


def answer_codes(tokenizer_json: str, n: int = N_CODES) -> tuple[list[str], list[int]]:
    """A..Z, then the two-letter codes AA, AB, ... that are single tokens of this tokenizer, until ``n`` codes (the rule behind
    reax-1.1's list, which skips e.g. 'BQ'); with their token ids. ``joint.detect`` needs A..Z first and single tokens."""
    tok = C.read_json(tokenizer_json)
    vocab = dict(tok["model"]["vocab"]) if isinstance(tok["model"]["vocab"], dict) else {
        v[0]: i for i, v in enumerate(tok["model"]["vocab"])}
    vocab.update({t["content"]: t["id"] for t in tok.get("added_tokens", [])})
    cands = list(v5.LETTERS) + [a + b for a in v5.LETTERS for b in v5.LETTERS]
    if any(c not in vocab for c in v5.LETTERS):
        raise SystemExit("the letters A..Z are not single tokens of this tokenizer")
    codes = [c for c in cands if c in vocab][:n]
    if len(codes) < n:
        raise SystemExit(f"only {len(codes)} single-token answer codes")
    return codes, [vocab[c] for c in codes]


def convert(src: str, out: str, base_id: str, delete_src: bool = False) -> None:
    from safetensors.torch import load_file, save_file
    repo, rev = base_id.split("@")
    cfg = C.read_json(os.path.join(src, "config.json"))
    if cfg.get("architectures") != ["Qwen3_5ForConditionalGeneration"] or cfg.get("model_type") != "qwen3_5":
        raise SystemExit(f"{src}: expected a qwen3_5 Qwen3_5ForConditionalGeneration checkpoint")
    if any(k in cfg for k in ("auto_map", "quantization_config")):
        raise SystemExit(f"{src}: auto_map / quantization_config present")
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"{out} exists and is not empty")
    os.makedirs(out, exist_ok=True)
    wmap = C.read_json(os.path.join(src, "model.safetensors.index.json"))["weight_map"]
    codes, ids = answer_codes(os.path.join(src, "tokenizer.json"))
    new_map, readout = {}, None
    for shard in sorted(set(wmap.values())):
        t = load_file(os.path.join(src, shard))
        renamed = {}
        for k, v in t.items():
            if k == "lm_head.weight":
                readout = v[ids].clone().contiguous()
            elif k.startswith(PREFIX):
                renamed[k[len(PREFIX):]] = v
            else:
                raise SystemExit(f"unexpected tensor {k}")
        if renamed:                 # a shard that held only lm_head is dropped (detect refuses unreferenced files)
            save_file(renamed, os.path.join(out, shard), metadata={"format": "pt"})
            new_map.update({k: shard for k in renamed})
        print(f"{shard}: {len(renamed)} tensors", flush=True)
        del t, renamed
        if delete_src:              # disk: never hold two full copies
            os.remove(os.path.join(src, shard))
    if readout is None:
        raise SystemExit("no lm_head.weight in the source")
    save_file({"weight": readout}, os.path.join(out, "readout.safetensors"), metadata={"format": "pt"})
    total = sum(os.path.getsize(os.path.join(out, s)) for s in set(new_map.values()))
    C.write_json(os.path.join(out, "model.safetensors.index.json"), {"metadata": {"total_size": total}, "weight_map": new_map})
    cfg["architectures"] = ["Qwen3_5Model"]
    cfg["language_model_only"] = False
    C.write_json(os.path.join(out, "config.json"), cfg)
    C.write_json(os.path.join(out, "decision_config.json"), {
        "format_version": 2, "base_model": repo, "revision": rev, "attention_mode": "noncausal_full_attention",
        "pooling": "last", "temperature": 2.0, "max_pixels": 1638400, "codes": codes, "token_ids": ids})
    C.write_json(os.path.join(out, "joint_config.json"), J.JOINT_PROTOCOL)
    for f in COPY:
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), out)
    write_modifications(out, base_id)
    info = J.detect(out, category="generalist", now_ts=float("inf"))
    print(f"joint readout OK: {len(info.codes)} codes, hidden {info.hidden_size}; {out}")


def write_modifications(out: str, base_id: str) -> None:
    """MODIFICATIONS.md step 1 (carried into every export): what the repackaging changed."""
    with open(os.path.join(out, "MODIFICATIONS.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Modifications\n\nThis model is a modified version of `{base_id}`.\n\n"
                 "## Step 1: REAX joint-readout package (no weight value changed)\n\n"
                 "| Part | Change |\n|---|---|\n"
                 "| `config.json` | `architectures` set to `[\"Qwen3_5Model\"]`, `language_model_only: false` added; every other value unchanged |\n"
                 "| weights | tensor names `model.X` -> `X` (the Qwen3_5Model layout), `lm_head.weight` dropped; values and dtypes unchanged |\n"
                 "| `readout.safetensors` | added: the `lm_head` rows of the 255 REAX answer codes (A..Z, then single-token two-letter codes) |\n"
                 "| `decision_config.json`, `joint_config.json` | added: REAX joint protocol v3, the answer codes and their token ids, the base identity |\n"
                 "| not carried over | the base's own serving code and assets |\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-id", required=True, help="<hf id>@<40-hex revision> of the source checkpoint")
    ap.add_argument("--delete-src", action="store_true", help="delete each source shard once its converted copy is written")
    a = ap.parse_args(argv)
    if "@" not in a.base_id or len(a.base_id.split("@")[1]) != 40:
        ap.error("--base-id must be <hf id>@<40-hex revision>")
    convert(a.src, a.out, a.base_id, a.delete_src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
