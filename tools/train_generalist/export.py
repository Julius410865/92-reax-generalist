"""Merge a LoRA checkpoint into the base and write a submission directory in the validator's joint-readout layout.

    python -m tools.train_generalist.export --base /models/reax-1.1 --adapter runs/stage1/ckpt-N --out submit/stage1 \
        --hotkey <ss58> --base-id decisionmodels/reax-1.1@<40 hex>

W = W(base) + (alpha / r) * B @ A in fp32, stored in the base tensor's dtype, shard names and tensor names unchanged.
Only files the validator downloads are written (``rules.DOWNLOAD_PATTERNS``) plus README / MODIFICATIONS / NOTICE; the
readout head, configs and tokenizer are copied unchanged. The result is checked with the validator's own
``fetch.inspect_dir`` (every submission rule, joint readout included) before the command reports success.
Nothing is uploaded or committed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import random
import shutil
import sys
from typing import Any

from reax_subnet.spec import rules as R

from . import common as C

COPY = ("config.json", "decision_config.json", "joint_config.json", "readout.safetensors", "tokenizer.json",
        "tokenizer_config.json", "processor_config.json", "chat_template.jinja", "LICENSE", "NOTICE")
PEFT_PREFIX = "base_model.model."


def lora_deltas(adapter: str) -> tuple[dict[str, tuple[Any, Any]], float]:
    """{base tensor name: (A, B)} and the scale alpha / r of a PEFT checkpoint."""
    from safetensors.torch import load_file
    cfg = C.read_json(os.path.join(adapter, "adapter_config.json"))
    if cfg.get("use_rslora") or cfg.get("use_dora"):
        raise SystemExit("rsLoRA / DoRA adapters are not supported by this merge")
    scale = float(cfg["lora_alpha"]) / float(cfg["r"])
    t = load_file(os.path.join(adapter, "adapter_model.safetensors"))
    out: dict[str, list] = {}
    for k, v in t.items():
        if not k.startswith(PEFT_PREFIX) or ".lora_" not in k:
            raise SystemExit(f"unexpected adapter tensor {k}")
        mod, part = k[len(PEFT_PREFIX):].rsplit(".lora_", 1)
        slot = out.setdefault(mod + ".weight", [None, None])
        slot[0 if part.startswith("A") else 1] = v
    if any(a is None or b is None for a, b in out.values()):
        raise SystemExit("adapter has unpaired lora_A / lora_B tensors")
    return {k: (a, b) for k, (a, b) in out.items()}, scale


def merged_tensor(w, a, b, scale):
    return (w.float() + scale * (b.float() @ a.float())).to(w.dtype)


def _index(model_dir: str) -> dict[str, str]:
    p = os.path.join(model_dir, "model.safetensors.index.json")
    if os.path.exists(p):
        return C.read_json(p)["weight_map"]
    from safetensors import safe_open
    with safe_open(os.path.join(model_dir, "model.safetensors"), "pt") as fh:
        return {k: "model.safetensors" for k in fh.keys()}


def data_attributions(manifests: list[str]) -> list[str]:
    """One attribution line per data source, from the dataset manifests (their licence / notice fields)."""
    lines = []
    for p in manifests:
        m = C.read_json(p)
        if "domains" in m:              # dataset/n_records/manifest.json: one entry per record domain
            for d, v in m["domains"].items():
                lic = v.get("licence") or {}
                name = lic.get("name") if isinstance(lic, dict) else str(lic)
                notice = f"; {lic['notice']}" if isinstance(lic, dict) and lic.get("notice") else ""
                url = f" ({lic['url']})" if isinstance(lic, dict) and lic.get("url") else ""
                lines.append(f"{d} (snapshot {v.get('snapshot')}): {name}{url}{notice}")
        else:                           # a Hugging Face dataset (SOURCE.json or a subset manifest)
            src = m.get("source") or f"{m.get('repo')}@{m.get('revision')}"
            lines.append(f"{src}: {m.get('licence')} (credit: REAX / decisionmodels)")
    return lines


def serve_check(out: str, n: int = 8) -> list[str]:
    """Load the export with the validator's own JointRunner (GPU) and answer n dev questions: every answer must be a
    probability distribution over exactly the question's options."""
    import math
    from reax_subnet.spec import v5wire
    from reax_subnet.spec.joint import JointRunner
    dev = os.path.join(os.path.dirname(__file__), "..", "..", "eval-v5", "devset-v1", "dev.jsonl")
    items = [v5wire.cap_item(it, 0) for it in C.read_jsonl(dev)][:n]
    rows = v5wire.flatten(items)
    probs = JointRunner.load(out).decide(rows)
    bad = []
    for r, p in zip(rows, probs):
        if p is None or set(p) != set(r["question"]["criteria"]) or not math.isclose(sum(p.values()), 1.0, abs_tol=1e-3):
            bad.append(f"{r['id']}: answer {p} is not a distribution over {list(r['question']['criteria'])}")
    print(f"serve check: {len(rows)} dev questions answered by JointRunner, {len(bad)} malformed")
    return bad


def export(base: str, adapter: str, out: str, hotkey: str, base_id: str, licence: str, licence_file: str | None = None,
           data_manifests: list[str] = (), weight: float = 1.0) -> None:
    from safetensors.torch import load_file, save_file
    if licence not in R.LICENCE_ALLOWLIST:
        raise SystemExit(f"--licence {licence!r} is not on the validator's allowlist {R.LICENCE_ALLOWLIST}")
    has_licence = any(os.path.exists(os.path.join(base, n)) for n in R.LICENSE_FILES)
    if not has_licence and not licence_file:
        raise SystemExit(f"{base} has no LICENSE file and the validator requires one: pass --licence-file <text of the {licence} licence>")
    deltas, scale = lora_deltas(adapter)
    wmap = _index(base)
    missing = [k for k in deltas if k not in wmap]
    if missing:
        raise SystemExit(f"adapter targets tensors the base does not have: {missing[:3]}")
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"{out} exists and is not empty")
    os.makedirs(out, exist_ok=True)
    for shard in sorted(set(wmap.values())):
        t = load_file(os.path.join(base, shard))
        n = 0
        for k in list(t):
            if k in deltas:
                a, b = deltas[k]
                t[k] = merged_tensor(t[k], a, b, scale * weight)
                n += 1
        save_file(t, os.path.join(out, shard), metadata={"format": "pt"})
        print(f"{shard}: {n} merged", flush=True)
        del t
    if os.path.exists(os.path.join(base, "model.safetensors.index.json")):
        shutil.copy2(os.path.join(base, "model.safetensors.index.json"), out)
    for f in COPY:
        if os.path.exists(os.path.join(base, f)):
            shutil.copy2(os.path.join(base, f), out)
    if not has_licence:
        shutil.copy2(licence_file, os.path.join(out, "LICENSE"))
    C.write_json(os.path.join(out, R.MANIFEST_NAME), {"schema": R.MANIFEST_SCHEMA, "category": "generalist", "hotkey": hotkey,
                                                      "base_model": base_id, "licence": licence})
    attributions = data_attributions(data_manifests)
    base_notice = ""
    if os.path.exists(os.path.join(base, "NOTICE")):
        base_notice = open(os.path.join(base, "NOTICE"), encoding="utf-8").read().rstrip() + "\n\n"
    with open(os.path.join(out, "NOTICE"), "w", encoding="utf-8") as fh:
        fh.write(base_notice + f"Base model: {base_id} (licence: {licence}).\n\nTraining data:\n"
                 + "".join(f"- {line}\n" for line in attributions))
    meta = C.read_json(os.path.join(adapter, "adapter_config.json"))
    mods = ""
    if os.path.exists(os.path.join(base, "MODIFICATIONS.md")):
        with open(os.path.join(base, "MODIFICATIONS.md"), encoding="utf-8") as fh:
            mods = fh.read().rstrip() + "\n\n"
    with open(os.path.join(out, "MODIFICATIONS.md"), "w", encoding="utf-8") as fh:
        fh.write(mods + f"## SN92 generalist entry (fine-tune of {base_id})\n\n"
                 f"* One LoRA (rank {meta['r']}, alpha {meta['lora_alpha']}) on the language model's attention, linear-attention "
                 "and MLP projections, merged in fp32 into the weights of " + (f"`{os.path.basename(os.path.normpath(base))}`" if weight == 1.0
                 else f"`{os.path.basename(os.path.normpath(base))}` at weight {weight:g}") + " and stored in bf16. Readout head, configs and "
                 "tokenizer unchanged.\n* Trained through the REAX joint readout at the validator's fixed temperature (2). "
                 "Training data and its licences: see NOTICE.\n")
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(f"---\nlicense: {licence}\nbase_model: {base_id.split('@')[0]}\nbase_model_relation: finetune\ntags:\n- sn92\n"
                 f"- decision-model\n---\n\n# SN92 generalist entry\n\nFine-tune of `{base_id}` in the REAX joint-readout layout "
                 "(Qwen3_5Model backbone + readout head). See MODIFICATIONS.md, NOTICE and LICENSE.\n")


def validator_check(out: str, hotkey: str) -> list[str]:
    from reax_subnet.spec import fetch as F
    return list(F.inspect_dir(out, category="generalist", hotkey=hotkey).violations)


def check_merged(merged: str, base: str, adapter: str, samples: int = 24, weight: float = 1.0) -> list[str]:
    """Problems of a merged export: tensors not changed, or not equal to base + delta, or base tensors altered elsewhere."""
    from safetensors import safe_open
    problems: list[str] = []
    deltas, scale = lora_deltas(adapter)
    scale *= weight
    wb, wm = _index(base), _index(merged)
    if set(wb) != set(wm):
        problems.append("merged tensor names differ from the base")
        return problems
    rng = random.Random(0)
    picks = rng.sample(sorted(deltas), min(samples, len(deltas)))
    others = rng.sample(sorted(k for k in wb if k not in deltas), min(4, len(wb) - len(deltas)))
    same = 0
    for k in picks + others:
        with safe_open(os.path.join(base, wb[k]), "pt") as fb, safe_open(os.path.join(merged, wm[k]), "pt") as fm:
            b, m = fb.get_tensor(k), fm.get_tensor(k)
        if k in deltas:
            if (m == b).all():
                same += 1
                problems.append(f"{k}: unchanged from the base")
            elif not (m == merged_tensor(b, *deltas[k], scale)).all():
                problems.append(f"{k}: differs from base + LoRA delta")
        elif not (m == b).all():
            problems.append(f"{k}: not a LoRA target but changed")
    print(f"merged check: {len(picks)} LoRA tensors and {len(others)} other tensors sampled, {same} unchanged")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hotkey", required=True, help="the committing hotkey's ss58 address (public; no key material)")
    ap.add_argument("--base-id", required=True, help="<hf id>@<40-hex revision> of the declared base")
    ap.add_argument("--licence", required=True, help="the model's licence: the base's (mammoth-1: mit; reax-1.1: apache-2.0)")
    ap.add_argument("--licence-file", default=None, help="licence text to ship as LICENSE when the base has none")
    ap.add_argument("--data-manifest", action="append", default=[], help="manifest of a dataset trained on (repeat); goes to NOTICE")
    ap.add_argument("--serve-check", action="store_true", help="also load the export with the validator's JointRunner (GPU)")
    ap.add_argument("--weight", type=float, default=1.0, help="merge weight w: W + w * (alpha / r) * B @ A (merge_eval's w)")
    a = ap.parse_args(argv)
    if "@" not in a.base_id or len(a.base_id.split("@")[1]) != 40:
        ap.error("--base-id must be <hf id>@<40-hex revision>")
    export(a.base, a.adapter, a.out, a.hotkey, a.base_id, a.licence, a.licence_file, a.data_manifest, a.weight)
    v = validator_check(a.out, a.hotkey)
    if a.serve_check:
        v += serve_check(a.out)
    if v:
        print("VALIDATOR RULES: PROBLEMS\n  " + "\n  ".join(v))
        return 1
    print(f"VALIDATOR RULES: OK ({a.out}); nothing uploaded or committed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
