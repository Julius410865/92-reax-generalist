"""tools/train_generalist: data conversion, splits, rendering parity, scoring, and an end-to-end run on a tiny random
Qwen3.5 joint-readout model (needs torch + transformers + peft and the REAX tokenizer: REAX_TOKENIZER=<tokenizer.json>)."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import string

import pytest

from reax_subnet.spec import prompt as P
from reax_subnet.spec import v5, v5wire
from tools.train_generalist import common as C
from tools.train_generalist import data as D
from tools.train_generalist import scoring as SC

TOKENIZER = os.environ.get("REAX_TOKENIZER", "")
needs_tok = pytest.mark.skipif(not os.path.exists(TOKENIZER), reason="set REAX_TOKENIZER to a REAX tokenizer.json")


def s1_row(i, qtype="choice", n=4, expected=None, family="qwen", tier="core", group=None):
    if qtype == "choice":
        crit, exp = {str(k): f"opt{k}" for k in range(n)}, expected or "2"
    elif qtype == "score":
        crit, exp = [f"level{k}" for k in range(n)], expected or "1"
    else:
        crit, exp = {"false": "No", "true": "Yes"}, expected or "true"
    return {"id": f"r{i}", "category": "math_quant", "state": {"x": i}, "expected": exp, "mix_tier": tier,
            "question": {"type": qtype, "instructions": f"Q{i}?", "criteria": crit},
            "ancestry": {"author_family": family, "split_key": group or f"g{i}", "root": f"root{i}"}}


# ------------------------------------------------------------------------------------------------------- conversion

def test_choice_rekeyed_in_order():
    it = D.s1_item(s1_row(1, "choice", 4, "2"), "src")
    q = it["questions"][0]
    assert list(q["criteria"]) == ["A", "B", "C", "D"] and q["criteria"]["C"] == "opt2" and q["expected"] == "C"


def test_score_levels_keep_order_and_are_never_shuffled():
    it = D.s1_item(s1_row(1, "score", 5, "3"), "src")
    assert list(it["questions"][0]["criteria"].values()) == [f"level{k}" for k in range(5)]
    assert it["questions"][0]["expected"] == "D"
    for seed in range(20):
        assert D.augment(it, seed)["questions"] == it["questions"]


def test_noul_becomes_yes_first():
    it = D.s1_item(s1_row(1, "noul", expected="false"), "src")
    q = it["questions"][0]
    assert list(q["criteria"]) == ["yes", "no"] and q["expected"] == "no"
    assert D.augment(it, 3)["questions"] == it["questions"]


def test_augment_keeps_gold_text_and_balances_positions():
    it = D.s1_item(s1_row(1, "choice", 6, "0"), "src")
    pos = set()
    for seed in range(60):
        q = D.augment(dict(it, id=f"x{seed}"), 0)["questions"][0]
        assert q["criteria"][q["expected"]] == "opt0" and list(q["criteria"]) == list(string.ascii_uppercase[:6])
        pos.add(q["expected"])
    assert len(pos) == 6


# ----------------------------------------------------------------------------------------------------------- splits

def _write(tmp_path, rows, name="train-00000.jsonl.gz"):
    d = tmp_path / "hf"
    d.mkdir(exist_ok=True)
    with gzip.open(d / name, "wt") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return "hf/train-*.jsonl.gz"


def _cfg(glob, excl=(), take=(0, None), weight=1.0):
    src = {"name": "hf", "kind": "s1", "glob": glob, "mix_tier": ["core"], "exclude_author_family": list(excl),
           "take": list(take), "weight": weight, "augment": True}
    ev = {"kind": "s1", "name": "hf", "glob": glob, "exclude_author_family": list(excl)}
    return {"stage": "t", "base": "x", "seed": 0, "max_len": 4096, "s1_holdout": {"select": 0.1, "test": 0.2},
            "sources": [src], "select": [ev], "test": [ev]}


def test_holdout_by_group_ignores_filters(tmp_path):
    rows = [s1_row(i, family=["openai", "qwen", "anthropic"][i % 3], group=f"g{i // 3}") for i in range(900)]
    g = _write(tmp_path, rows)
    split = {r["id"]: D.holdout(r, _cfg(g)) for r in rows}
    for k in range(300):          # a group never straddles splits
        assert len({split[f"r{3 * k + j}"] for j in range(3)}) == 1
    a, _ = D.load_split(_cfg(g), "test", str(tmp_path))
    b, _ = D.load_split(_cfg(g, excl=("openai", "anthropic")), "test", str(tmp_path))
    assert {i["id"] for i in b} <= {i["id"] for i in a}
    assert all(split[i["id"]] == "test" for i in b)
    tr, _ = D.load_split(_cfg(g), "train", str(tmp_path))
    held = {i["id"] for s in ("select", "test") for i in D.load_split(_cfg(g), s, str(tmp_path))[0]}
    assert not held & {i["id"] for i in tr}
    assert 0.2 < len(held) / len(rows) < 0.4


def test_author_filter_take_and_weight(tmp_path):
    rows = [s1_row(i, family="openai" if i % 2 else "qwen") for i in range(600)]
    g = _write(tmp_path, rows)
    excl, _ = D.load_split(_cfg(g, excl=("openai",)), "train", str(tmp_path))
    assert excl and all(int(i["id"][1:]) % 2 == 0 for i in excl)
    a, _ = D.load_split(_cfg(g, take=(0, 50)), "train", str(tmp_path))
    b, _ = D.load_split(_cfg(g, take=(50, None)), "train", str(tmp_path))
    full, _ = D.load_split(_cfg(g), "train", str(tmp_path))
    assert len(a) == 50 and not {i["id"] for i in a} & {i["id"] for i in b}
    assert len(a) + len(b) == len(full)
    w, _ = D.load_split(_cfg(g, take=(0, 50), weight=0.25), "train", str(tmp_path))
    assert {i["id"] for i in w} <= {i["id"] for i in a} and 3 <= len(w) <= 25


def test_eval_split_caps_rows_per_group(tmp_path):
    rows = [s1_row(i, group="big" if i < 500 else f"g{i}") for i in range(2000)]
    g = _write(tmp_path, rows)
    cfg = _cfg(g)
    cfg["s1_holdout"] = {"select": 0.0, "test": 1.0}
    test, stats = D.load_split(cfg, "test", str(tmp_path))
    big = [it for it in test if it["group"] == "split_key:big"]
    assert len(big) == D.EVAL_GROUP_CAP and stats["hf"]["over_group_cap"] == 500 - D.EVAL_GROUP_CAP
    again, _ = D.load_split(cfg, "test", str(tmp_path))
    assert [it["id"] for it in again] == [it["id"] for it in test]


def test_cluster_bootstrap_counts_correlated_rows_once():
    gold = ["AB"[(k // 2) % 2] for k in range(200)]          # balanced gold keys: the constant baseline is 50 %

    def items(clustered):
        return [{"id": f"i{k}", "task_type": "s1:a", "part": "S1", "area": None, "gold": False, "idk": False, "source": "hf",
                 "group": f"c{k // 20}" if clustered else f"c{k}",
                 "questions": [{"criteria": {"A": "x", "B": "y"}, "expected": gold[k]}]} for k in range(200)]

    def answers(right):
        return {f"i{k}": [{c: float((c == gold[k]) == right(k)) for c in "AB"}] for k in range(200)}

    # model a is right on whole clusters (all 20 rows of a template), b is right on alternate rows
    a, b = answers(lambda k: (k // 20) % 2 == 0), answers(lambda k: k % 2 == 0)
    se_cl = SC.paired(items(True), a, b, boot=300)["local"]["se"]
    se_rows = SC.paired(items(False), a, b, boot=300)["local"]["se"]
    assert se_cl > 2 * se_rows


def test_heldout_paths_never_trained(tmp_path):
    cfg = _cfg("x")
    cfg["sources"] = [{"name": "h", "kind": "mirror", "glob": "data/generalist/heldout/*.jsonl"}]
    with pytest.raises(ValueError):
        D.load_split(cfg, "train", str(tmp_path))


# -------------------------------------------------------------------------------------------------------- rendering

@needs_tok
def test_rendering_is_the_validators():
    tok = C.load_tokenizer(TOKENIZER)
    it = D.s1_item(s1_row(7, "noul"), "src")
    row = v5wire.flatten([it])[0]
    ids, r = C.render_ids(tok, row)
    text = tok.decode(ids)
    assert text.startswith("<|im_start|>system\n" + P.SYSTEM) and text.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert "A: Yes\nB: No\nAnswer with one option letter only." in text and r.keys == ("yes", "no")


@needs_tok
def test_eval_rows_are_capped_at_26():
    tok = C.load_tokenizer(TOKENIZER)
    crit = {v5.option_codes(40)[k]: f"o{k}" for k in range(40)}
    it = {"id": "big", "state": None, "idk": False, "part": "N", "task_type": "t", "area": None, "gold": False,
          "questions": [{"instructions": "pick", "criteria": crit, "expected": "AH"}]}
    capped, rows, st = D.prepare_eval([it], tok)
    q = capped[0]["questions"][0]
    assert len(q["criteria"]) == 26 and q["criteria"][q["expected"]] == crit["AH"] and len(rows[0]["keys"]) == 26
    assert st["render_failed"] == 0


# ---------------------------------------------------------------------------------------------------------- scoring

def _items(n=60):
    return [{"id": f"i{k}", "task_type": "s1:a" if k % 2 else "s1:b", "part": "S1", "area": None, "gold": False, "idk": False,
             "questions": [{"criteria": {"A": "x", "B": "y", "C": "z"}, "expected": "ABC"[k % 3]}]} for k in range(n)]


def test_scoring_perfect_and_paired():
    items = _items()
    right = {it["id"]: [{c: (1.0 if c == it["questions"][0]["expected"] else 0.0) for c in "ABC"}] for it in items}
    wrong = {it["id"]: [{c: (1.0 if c == "ABC"[("ABC".index(it["questions"][0]["expected"]) + 1) % 3] else 0.0) for c in "ABC"}]
             for it in items}
    assert SC.score(items, right)["local"] == pytest.approx(100.0)
    assert SC.score(items, wrong)["local"] == pytest.approx(0.0)
    p = SC.paired(items, right, wrong, boot=50)
    assert p["local"]["gain"] == pytest.approx(100.0) and p["changed_items"] == len(items)
    same = SC.paired(items, right, right, boot=50)
    assert same["local"]["gain"] == 0 and same["changed_items"] == 0


def test_gzip_output_is_deterministic(tmp_path):
    rows = [{"id": i, "x": "é" * i} for i in range(50)]
    C.write_jsonl(str(tmp_path / "a.jsonl.gz"), rows)
    C.write_jsonl(str(tmp_path / "b.jsonl.gz"), rows)
    assert (tmp_path / "a.jsonl.gz").read_bytes() == (tmp_path / "b.jsonl.gz").read_bytes()
    assert list(C.read_jsonl(str(tmp_path / "a.jsonl.gz"))) == rows
    assert C.content_digest(str(tmp_path / "a.jsonl.gz")) == C.content_digest(str(tmp_path / "b.jsonl.gz"))


def _mixed_items():
    """24 hf items (s1, 2 categories) and 12 dev items (typed T, area knowledge), single questions with balanced gold."""
    out = []
    for k in range(48):
        out.append({"id": f"h{k}", "source": "hf", "task_type": "s1:a" if k % 2 else "s1:b", "part": "S1", "area": None,
                    "gold": False, "idk": False, "group": f"g{k}",
                    "questions": [{"criteria": {"A": "x", "B": "y"}, "expected": "AB"[(k // 2) % 2]}]})
    for k in range(24):
        out.append({"id": f"d{k}", "source": "dev", "task_type": "logic" if k % 2 else "arith", "part": "T",
                    "area": "knowledge", "gold": False, "idk": False,
                    "questions": [{"criteria": {"A": "x", "B": "y"}, "expected": "AB"[(k // 2) % 2]}]})
    return out


def _answers(items, right):
    return {it["id"]: [{c: float((c == it["questions"][0]["expected"]) == right(it)) for c in "AB"}] for it in items}


def _write_reports(tmp_path, items, models: dict):
    os.makedirs(tmp_path / "prepared" / "eval", exist_ok=True)
    os.makedirs(tmp_path / "reports", exist_ok=True)
    ip = str(tmp_path / "prepared" / "eval" / "test.items.jsonl.gz")
    C.write_jsonl(ip, items)
    from tools.train_generalist.stage_check import _digest
    for label, resp in models.items():
        C.write_json(str(tmp_path / "reports" / f"{label}.json"),
                     {"label": label, "splits": {"test": {"prepared_digest": _digest(ip), "responses": resp}}})


@pytest.mark.parametrize("hf_right,dev_right,verdict", [
    (lambda k: True, lambda k: k < 20, "TRANSFER LOSS"),     # hf up, dev down: the in-distribution gain must not hide it
    (lambda k: k < 12, lambda k: True, "NO GAIN"),            # dev fine, hf not better
    (lambda k: True, lambda k: k < 22, "TRANSFER LOSS"),      # even a one-item dev drop stops the stage
    (lambda k: True, lambda k: True, "IMPROVED"),
])
def test_compare_rules(tmp_path, monkeypatch, hf_right, dev_right, verdict):
    from tools.train_generalist import stage_check as SCK
    items = _mixed_items()
    num = lambda it: int(it["id"][1:])
    base = _answers(items, lambda it: (num(it) < 12) if it["source"] == "hf" else (num(it) < 23))
    stage = _answers(items, lambda it: hf_right(num(it)) if it["source"] == "hf" else dev_right(num(it)))
    _write_reports(tmp_path, items, {"base": base, "stage1": stage})
    cfg = tmp_path / "stage1.json"
    cfg.write_text(json.dumps({"checks": {"learn": ["hf"], "transfer": ["dev", "gen"]}}))
    monkeypatch.chdir(tmp_path)
    assert SCK.main(["compare", "--stage", "stage1", "--prev", "base", "--config", str(cfg)]) == 0
    out = json.load(open("reports/stage1.compare.json"))
    assert out["verdict"] == verdict and out["learn"] == ["hf"] and out["transfer"] == ["dev"]


def test_submit_line_judges_transfer_not_hf(tmp_path, monkeypatch):
    from tools.train_generalist import stage_check as SCK
    items = _mixed_items()
    num = lambda it: int(it["id"][1:])
    base = _answers(items, lambda it: (num(it) < 12) if it["source"] == "hf" else (num(it) < 20))
    stage = _answers(items, lambda it: True if it["source"] == "hf" else (num(it) < 20))     # hf gain only
    champ = _answers(items, lambda it: (num(it) < 24) if it["source"] == "hf" else (num(it) < 20))
    _write_reports(tmp_path, items, {"base": base, "stage1": stage, "champion": champ})
    monkeypatch.chdir(tmp_path)
    assert SCK.main(["compare", "--stage", "stage1", "--prev", "base"]) == 0
    out = json.load(open("reports/stage1.compare.json"))
    assert out["verdict"] == "IMPROVED" and out["submit"] == "NOT A CANDIDATE"     # local is up, transfer is not
    assert out["vs_champion"]["local"]["gain"] > 0 and out["vs_champion"]["transfer"]["gain"] == 0


def test_multi_question_item_needs_every_question():
    it = {"id": "m", "task_type": "t", "part": "T", "area": "tools", "gold": False, "idk": False,
          "questions": [{"criteria": {"yes": "Yes", "no": "No"}, "expected": "yes"}] * 2}
    r = SC.score([it], {"m": [{"yes": 0.9, "no": 0.1}, {"yes": 0.2, "no": 0.8}]})
    assert r["item_accuracy"] == 0.0


# ------------------------------------------------------------------------------------------------ tiny model, e2e

def _tiny_model_dir(path: str) -> str:
    import torch
    from safetensors.torch import save_file
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5Config
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model
    vocab = json.load(open(TOKENIZER))
    n_vocab = max(max(vocab["model"]["vocab"].values()), max(t["id"] for t in vocab["added_tokens"])) + 1
    cfg = Qwen3_5Config(
        text_config={"vocab_size": n_vocab, "hidden_size": 64, "intermediate_size": 128, "num_hidden_layers": 4,
                     "num_attention_heads": 2, "num_key_value_heads": 1, "head_dim": 32, "linear_num_key_heads": 2,
                     "linear_num_value_heads": 2, "linear_key_head_dim": 16, "linear_value_head_dim": 16,
                     "full_attention_interval": 4, "max_position_embeddings": 4096},
        vision_config={"depth": 1, "hidden_size": 32, "intermediate_size": 64, "num_heads": 2, "out_hidden_size": 64})
    cfg.architectures = ["Qwen3_5Model"]
    torch.manual_seed(0)
    m = Qwen3_5Model(cfg)
    m.save_pretrained(path, safe_serialization=True)
    save_file({"weight": torch.randn(26, 64) * 0.5}, os.path.join(path, "readout.safetensors"))
    ids = [vocab["model"]["vocab"][c] for c in string.ascii_uppercase]
    json.dump({"format_version": 2, "base_model": "test/tiny", "revision": "0" * 40, "attention_mode": "noncausal_full_attention",
               "pooling": "last", "temperature": 2.0, "max_pixels": 1638400, "codes": list(string.ascii_uppercase),
               "token_ids": ids}, open(os.path.join(path, "decision_config.json"), "w"))
    from reax_subnet.spec.joint import JOINT_PROTOCOL
    json.dump(JOINT_PROTOCOL, open(os.path.join(path, "joint_config.json"), "w"))
    shutil.copy(TOKENIZER, os.path.join(path, "tokenizer.json"))
    json.dump({"tokenizer_class": "PreTrainedTokenizerFast"}, open(os.path.join(path, "tokenizer_config.json"), "w"))
    open(os.path.join(path, "LICENSE"), "w").write("Apache-2.0\n")
    return path


def _device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


@needs_tok
def test_decide_matches_joint_runner(tmp_path):
    torch = pytest.importorskip("torch")
    from reax_subnet.spec.joint import JointRunner
    mdir = _tiny_model_dir(str(tmp_path / "m"))
    model, weight, _ = C.load_backbone(mdir, _device())
    tok = C.load_tokenizer(mdir)
    items = [D.s1_item(s1_row(i, ["choice", "noul", "score"][i % 3], 3 + i % 4), "s") for i in range(12)]
    capped, rows, _ = D.prepare_eval(items, tok)
    mine = C.decide(model, weight, rows)
    runner = object.__new__(JointRunner)          # the hook is already installed by load_backbone
    runner.model, runner.tokenizer, runner.weight = model, tok, weight
    runner.max_length, runner.batch_tokens, runner.batch_size = 8192, 8192, 4
    theirs = runner.decide([dict(r, id=x["id"]) for r, x in zip(v5wire.flatten(capped), rows)])
    for a, b in zip(mine, theirs):
        assert a is not None and set(a) == set(b) and all(abs(a[k] - b[k]) < 1e-6 for k in a)


@needs_tok
def test_convert_causal_checkpoint_to_joint(tmp_path):
    torch = pytest.importorskip("torch")
    from safetensors.torch import load_file
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5ForConditionalGeneration
    from tools.train_generalist import convert as K
    tiny = _tiny_model_dir(str(tmp_path / "joint"))           # reuse its config for a causal twin
    cfg = json.load(open(os.path.join(tiny, "config.json")))
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5Config
    c = Qwen3_5Config.from_dict(cfg)
    c.architectures = ["Qwen3_5ForConditionalGeneration"]
    torch.manual_seed(1)
    src = Qwen3_5ForConditionalGeneration(c)
    sdir = str(tmp_path / "causal")
    src.save_pretrained(sdir, safe_serialization=True, max_shard_size="20MB")
    shutil.copy(TOKENIZER, os.path.join(sdir, "tokenizer.json"))
    json.dump({"tokenizer_class": "PreTrainedTokenizerFast"}, open(os.path.join(sdir, "tokenizer_config.json"), "w"))
    out = str(tmp_path / "conv")
    K.convert(sdir, out, "test/causal@" + "1" * 40)
    dc = json.load(open(os.path.join(out, "decision_config.json")))
    ref = json.load(open(os.path.join(os.path.dirname(TOKENIZER), "decision_config.json"))) if os.path.exists(
        os.path.join(os.path.dirname(TOKENIZER), "decision_config.json")) else None
    if ref:
        assert dc["codes"] == ref["codes"] and dc["token_ids"] == ref["token_ids"]
    ro = load_file(os.path.join(out, "readout.safetensors"))["weight"]
    assert torch.equal(ro, src.lm_head.weight.detach()[dc["token_ids"]])
    dev = _device()
    model, weight, _ = C.load_backbone(out, dev)
    src = src.to(dev).eval()
    from reax_subnet.spec import joint as J
    J.enable_full_attention(src.model.language_model)
    ids = torch.tensor([[248045, 9707, 25, 362, 13, 248046]], device=dev)
    with torch.no_grad():
        a = C.last_hidden(model, ids)
        b = src.model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).last_hidden_state[:, -1]
    assert torch.allclose(a.float(), b.float(), atol=1e-2, rtol=1e-2)


@needs_tok
def test_end_to_end_tiny(tmp_path, monkeypatch):
    pytest.importorskip("peft")
    from tools.train_generalist import export as E
    from tools.train_generalist import stage_check as SCK
    from tools.train_generalist import train as TR
    mdir = _tiny_model_dir(str(tmp_path / "base"))
    rows = [s1_row(i, ["choice", "noul", "score"][i % 3], 3 + i % 3, expected=None) for i in range(240)]
    g = _write(tmp_path, rows)
    cfg = _cfg(g)
    cfg["base"] = mdir
    cfg["train"] = {"kl_to_base": 0.5}
    cfg["checks"] = {"learn": ["hf"], "transfer": ["dev", "gen"]}
    cfg["test"] = cfg["test"] + [os.path.abspath("eval-v5/devset-v1/dev.jsonl")]
    cp = tmp_path / "stage1.json"
    cp.write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    assert D.main(["--config", str(cp), "--out", "prepared/eval", "--splits", "select,test", "--tokenizer", mdir]) == 0
    assert D.main(["--config", str(cp), "--out", "prepared/stage1", "--splits", "train", "--tokenizer", mdir]) == 0
    dev = _device()
    from tools.train_generalist import teacher as TE
    with pytest.raises(SystemExit):        # KL-to-base is configured: training refuses to run without the base's answers
        TR.main(["--config", str(cp), "--prepared", "prepared/stage1", "--eval", "prepared/eval", "--out", "runs/x",
                 "--device", dev])
    assert TE.check(mdir, "prepared/stage1") == "no teacher file"
    assert TE.main(["--base", mdir, "--prepared", "prepared/stage1", "--device", dev]) == 0
    assert TE.check(mdir, "prepared/stage1") is None
    assert TR.main(["--config", str(cp), "--prepared", "prepared/stage1", "--eval", "prepared/eval", "--out", "runs/stage1",
                    "--batch-tokens", "1500", "--eval-every", "4", "--lr", "3e-3", "--lr-min", "1e-3", "--device", dev]) == 0
    log = [json.loads(l) for l in open("runs/stage1/log.jsonl")]
    steps = [r for r in log if "loss" in r]
    losses = [r["loss"] for r in steps]
    assert all(l == l and l < 1e9 for l in losses) and len(losses) >= 4
    assert sum(r["ce"] for r in steps[-3:]) / 3 < sum(r["ce"] for r in steps[:3]) / 3
    assert steps[0]["kl"] is not None and 0 <= steps[0]["kl"] < 1e-3     # the adapter starts as a no-op: model == base
    assert all(r["loss"] == pytest.approx(r["ce"] + 0.5 * r["kl"], rel=1e-4, abs=1e-6) for r in steps)
    with gzip.open("prepared/stage1/teacher.jsonl.gz", "rt") as fh:  # a re-prepare of the same rows keeps the teacher valid
        n_teacher = sum(1 for _ in fh)
    assert D.main(["--config", str(cp), "--out", "prepared/stage1", "--splits", "train", "--tokenizer", mdir]) == 0
    assert TE.check(mdir, "prepared/stage1") is None and n_teacher == 168
    best = json.load(open("runs/stage1/best.json"))
    assert os.path.isdir(best["path"]) and [d for d in os.listdir("runs/stage1") if d.startswith("ckpt-")]
    if dev == "cuda":
        assert SCK.main(["eval", "--base", mdir, "--prepared", "prepared/eval", "--label", "base", "--out", "reports/base.json"]) == 0
    else:
        assert SCK.main(["eval", "--base", mdir, "--adapter", best["path"], "--prepared", "prepared/eval", "--label", "base",
                         "--out", "reports/base.json"]) == 0
    assert SCK.main(["eval", "--base", mdir, "--adapter", best["path"], "--prepared", "prepared/eval", "--label", "stage1",
                     "--out", "reports/stage1.json"]) == 0
    assert SCK.main(["compare", "--stage", "stage1", "--prev", "base", "--config", str(cp)]) == 0
    v = json.load(open("reports/stage1.compare.json"))["verdict"]
    assert v in ("IMPROVED", "NO GAIN", "REGRESSION", "NOT UPDATED", "TRANSFER LOSS")
    assert SCK.main(["weights", "--adapter", best["path"]]) == 0
    import time
    from reax_subnet.spec import rules as R
    monkeypatch.setattr(R, "_wall_clock", time.time)     # the open class (Qwen3_5Model joint readout) is live
    os.remove(os.path.join(mdir, "LICENSE"))           # like mammoth-1: the base ships no LICENSE file
    with pytest.raises(SystemExit):                     # refused before any merge without a licence text
        E.main(["--base", mdir, "--adapter", best["path"], "--out", "submit/x", "--hotkey", "5" + "A" * 47,
                "--base-id", "test/tiny@" + "0" * 40, "--licence", "mit"])
    with pytest.raises(SystemExit):                     # a licence the validator does not accept is refused
        E.main(["--base", mdir, "--adapter", best["path"], "--out", "submit/x", "--hotkey", "5" + "A" * 47,
                "--base-id", "test/tiny@" + "0" * 40, "--licence", "cc-by-nc-4.0", "--licence-file", "lic.txt"])
    open("lic.txt", "w").write("MIT License (test)\n")
    json.dump({"repo": "decisionmodels/sn92-generalist-train-v1", "revision": "x", "licence": "cc-by-4.0"}, open("src.json", "w"))
    assert E.main(["--base", mdir, "--adapter", best["path"], "--out", "submit/stage1", "--hotkey", "5" + "A" * 47,
                   "--base-id", "test/tiny@" + "0" * 40, "--licence", "mit", "--licence-file", "lic.txt",
                   "--data-manifest", "src.json"] + (["--serve-check"] if dev == "cuda" else [])) == 0
    assert os.path.exists("submit/stage1/LICENSE") and "sn92-generalist-train-v1" in open("submit/stage1/NOTICE").read()
    assert json.load(open("submit/stage1/reax-specialist.json"))["licence"] == "mit"
    assert SCK.main(["weights", "--adapter", best["path"], "--merged", "submit/stage1", "--base", mdir]) == 0


def test_kl_sample_is_fixed_and_about_the_fraction():
    from tools.train_generalist import teacher as TE
    ids = [f"r{i}" for i in range(4000)]
    a = [i for i in ids if TE.in_sample(i, 0.25)]
    assert a == [i for i in ids if TE.in_sample(i, 0.25)] and 0.22 < len(a) / len(ids) < 0.28
    assert all(TE.in_sample(i, 1.0) for i in ids)


@needs_tok
def test_partial_kl_teacher_and_training(tmp_path, monkeypatch):
    pytest.importorskip("peft")
    from tools.train_generalist import teacher as TE
    from tools.train_generalist import train as TR
    mdir = _tiny_model_dir(str(tmp_path / "base"))
    g = _write(tmp_path, [s1_row(i, ["choice", "noul", "score"][i % 3], 3 + i % 3) for i in range(200)])
    cfg = _cfg(g)
    cfg.update(base=mdir, train={"kl_to_base": 0.5, "kl_fraction": 0.5})
    cp = tmp_path / "c.json"
    cp.write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    assert D.main(["--config", str(cp), "--out", "prepared/s", "--splits", "train", "--tokenizer", mdir]) == 0
    dev = _device()
    assert TE.main(["--base", mdir, "--prepared", "prepared/s", "--device", dev, "--fraction", "0.5"]) == 0
    t = list(C.read_jsonl("prepared/s/teacher.jsonl.gz"))
    have = [x["p"] is not None for x in t]
    assert 0.3 < sum(have) / len(have) < 0.7
    assert TE.check(mdir, "prepared/s", 0.5) is None and TE.check(mdir, "prepared/s", 1.0) is not None
    assert TR.main(["--config", str(cp), "--prepared", "prepared/s", "--out", "runs/s", "--no-eval", "--batch-rows", "16", "--micro-batch", "4", "--micro-tokens", "4096",
                    "--lr", "3e-3", "--device", dev]) == 0
    steps = [json.loads(l) for l in open("runs/s/log.jsonl") if '"loss"' in l]
    assert steps and all(r["kl"] is not None and r["loss"] >= r["ce"] - 1e-6 for r in steps)


@needs_tok
def test_padded_pass_equals_one_at_a_time(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from peft import LoraConfig, get_peft_model
    from tools.train_generalist import train as TR
    mdir = _tiny_model_dir(str(tmp_path / "m"))
    dev = _device()
    model, weight, _ = C.load_backbone(mdir, dev)
    model = model.float()
    tok = C.load_tokenizer(mdir)
    items = [D.s1_item(s1_row(i, ["choice", "noul", "score"][i % 3], 3 + i % 4), "s") for i in range(6)]
    rows = [{"ids": C.render_ids(tok, r)[0]} for r in v5wire.flatten(items)]
    seqs = [r["ids"] for r in rows]
    assert len({len(s) for s in seqs}) > 1                      # different lengths, so real padding happens
    with torch.no_grad():
        one = torch.cat([C.last_hidden_padded(model, [s], dev) for s in seqs])
        pad = C.last_hidden_padded(model, seqs, dev)
    assert torch.allclose(one, pad, atol=1e-4, rtol=1e-4)
    # the same gradient through a LoRA, padded or not
    lm = get_peft_model(model, LoraConfig(r=4, lora_alpha=8, target_modules=TR.TARGETS))
    for n, p in lm.named_parameters():
        if "lora_B" in n:
            torch.nn.init.normal_(p, std=0.02)
    grads = []
    for passes in ([[s] for s in seqs], [seqs]):
        lm.zero_grad()
        for mb in passes:
            C.last_hidden_padded(lm, mb, dev).float().pow(2).sum().backward()
        grads.append(torch.cat([p.grad.flatten() for n, p in lm.named_parameters() if p.grad is not None]))
    assert torch.allclose(grads[0], grads[1], atol=1e-4, rtol=1e-3)


def test_micro_batches_respect_size_and_token_limits():
    from tools.train_generalist import train as TR
    group = [{"ids": [0] * n} for n in (10, 300, 50, 50, 900, 20, 400, 60)]
    mbs = TR.micro_batches(group, 3, 1000)
    assert sorted(len(r["ids"]) for mb in mbs for r in mb) == sorted(len(r["ids"]) for r in group)
    assert all(len(mb) <= 3 and max(len(r["ids"]) for r in mb) * len(mb) <= 1000 or len(mb) == 1 for mb in mbs)
    assert TR.micro_batches(group, 1, 1000) == [[r] for r in sorted(group, key=lambda r: len(r["ids"]))]
