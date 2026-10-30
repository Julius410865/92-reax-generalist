"""What training and scoring share with the validator: its renderer, tokenizer set-up, model loading and joint forward.

Everything here calls or copies ``reax_subnet.spec.joint`` / ``spec.prompt`` so a trained model is scored exactly as the
validator serves it: one question per prompt (``prompt.render``), the fixed ``qwen.jinja`` template with thinking off, full
attention bidirectional, the readout at the last prompt position, softmax at ``prompt.READOUT_TEMPERATURE``.
"""

from __future__ import annotations

import gzip
import json
import math
import os
from typing import Any, Iterable, Iterator, Mapping, Sequence

from reax_subnet.spec import joint as J
from reax_subnet.spec import prompt as P
from reax_subnet.spec.templates import template_path

EVAL_MAX_LENGTH = 8192     # JointRunner's max_length: longer prompts are failed items for every model alike


def load_tokenizer(path: str):
    """The validator's tokenizer: the Rust tokenizer file only, with the fixed qwen template (JointRunner.load)."""
    from transformers import PreTrainedTokenizerFast
    tok_file = path if path.endswith(".json") else os.path.join(path, "tokenizer.json")
    tok = PreTrainedTokenizerFast(tokenizer_file=tok_file)
    with open(template_path("qwen.jinja"), encoding="utf-8") as fh:
        tok.chat_template = fh.read()
    return tok


def tokenizer_digest(path: str) -> str:
    """sha256 (16 hex) of a model's tokenizer.json: token ids are only valid for the tokenizer they were made with
    (reax-1.1 and mammoth-1 share the vocabulary but not the pre-tokenizer)."""
    import hashlib
    tok_file = path if path.endswith(".json") else os.path.join(path, "tokenizer.json")
    with open(tok_file, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def render_ids(tok, row: Mapping[str, Any]) -> tuple[list[int], P.Rendered]:
    """Token ids of one served row (a ``v5wire.flatten`` row), exactly as ``JointRunner.decide`` builds them."""
    r = P.render(row["state"], row["question"])
    text = tok.apply_chat_template([{"role": "system", "content": r.system}, {"role": "user", "content": r.user}],
                                   tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return tok.encode(text, add_special_tokens=False), r


def load_backbone(model_dir: str, device: str = "cuda"):
    """(model, readout weight, JointReadout) loaded as ``JointRunner.load`` does, with the full-attention mask hook installed."""
    import torch
    from safetensors.torch import load_file
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5Config
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model
    from reax_subnet.spec import rules as R
    info = J.detect(model_dir, category="generalist", now_ts=float("inf"))
    if info is None:
        raise ValueError(f"{model_dir}: not a joint-readout model")
    torch.backends.cuda.enable_cudnn_sdp(False)
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    config = Qwen3_5Config.from_dict(R.read_json_file(os.path.join(model_dir, "config.json")))
    model, loading = Qwen3_5Model.from_pretrained(model_dir, config=config, local_files_only=True, trust_remote_code=False,
                                                  use_safetensors=True, dtype=dtype, attn_implementation="sdpa",
                                                  device_map={"": device}, output_loading_info=True)
    if any(loading.get(k) for k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise ValueError(f"{model_dir}: missing/unexpected/mismatched weights {loading}")
    weight = load_file(os.path.join(model_dir, "readout.safetensors"))["weight"].to(device=device, dtype=dtype)
    J.enable_full_attention(model.language_model)
    return model, weight, info


def last_hidden(model, ids):
    """Hidden state at the last position, as JointRunner computes it (no padding: callers batch equal lengths)."""
    import torch
    out = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).last_hidden_state
    return out[:, -1]


def last_hidden_padded(model, seqs: Sequence[Sequence[int]], device):
    """Hidden state at each sequence's last real token, for right-padded sequences in one pass. With one sequence it is
    ``last_hidden``. Right padding cannot change a real position: full attention masks the padded keys, the recurrent
    layers are causal, positions count from 0 as without padding."""
    import torch
    if len(seqs) == 1:
        return last_hidden(model, torch.tensor([list(seqs[0])], device=device))
    width = max(len(s) for s in seqs)
    ids = torch.zeros((len(seqs), width), dtype=torch.long, device=device)
    mask = torch.zeros((len(seqs), width), dtype=torch.long, device=device)
    for j, s in enumerate(seqs):
        ids[j, :len(s)] = torch.tensor(list(s), device=device)
        mask[j, :len(s)] = 1
    out = model(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
    return out[torch.arange(len(seqs), device=device), mask.sum(1) - 1]


def answer_logits(model, weight, rows: Sequence[Mapping[str, Any]], *, batch_tokens: int = 8192, batch_size: int = 4,
                  max_length: int = EVAL_MAX_LENGTH) -> list[list[float] | None]:
    """The option logits of prepared rows (``ids`` + ``keys``, or ``ids`` + ``k``), the numeric path of
    ``JointRunner.decide``: equal-length batches, BF16 linear readout -> float logits, the first n logits.
    None for a row that was not run (too long, out of memory) or gave a non-finite logit."""
    import torch
    results: list[list[float] | None] = [None] * len(rows)
    plans = sorted(((len(r["ids"]), i) for i, r in enumerate(rows) if 0 < len(r["ids"]) <= max_length))
    device = weight.device
    while plans:
        length = plans[0][0]
        count = min(batch_size, max(1, batch_tokens // length))
        group = []
        while plans and plans[0][0] == length and len(group) < count:
            group.append(plans.pop(0)[1])
        try:
            ids = torch.tensor([rows[i]["ids"] for i in group], device=device)
            with torch.inference_mode():
                logits = torch.nn.functional.linear(last_hidden(model, ids), weight).float().cpu().tolist()
        except torch.OutOfMemoryError:
            torch.cuda.empty_cache()
            continue
        for i, z in zip(group, logits):
            n = rows[i]["k"] if "k" in rows[i] else len(rows[i]["keys"])
            z = z[:n]
            if all(math.isfinite(v) for v in z):
                results[i] = z
    return results


def decide(model, weight, rows: Sequence[Mapping[str, Any]], **kw) -> list[dict[str, float] | None]:
    """Answer distributions of prepared eval rows: ``answer_logits``, softmax at T = 2, keyed by the option keys."""
    return [None if z is None else dict(zip(r["keys"], P.softmax_t(z)))
            for r, z in zip(rows, answer_logits(model, weight, rows, **kw))]


# ---------------------------------------------------------------------------------------------------------------- files

def write_jsonl(path: str, rows: Iterable[Mapping[str, Any]]) -> int:
    """JSONL (gzip if ``.gz``). The gzip header carries no time or name, so the same rows give the same bytes."""
    import io
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    n = 0
    tmp = path + ".tmp"
    with open(tmp, "wb") as raw:
        gz = gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") if path.endswith(".gz") else None
        with io.TextIOWrapper(gz if gz is not None else raw, encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
                n += 1
    os.replace(tmp, path)
    return n


def content_digest(path: str) -> str:
    """sha256 (16 hex) of a (possibly gzipped) file's content, independent of the gzip header."""
    import hashlib
    h = hashlib.sha256()
    with (gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")) as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def read_jsonl(path: str) -> Iterator[dict[str, Any]]:
    with (gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8")) as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
