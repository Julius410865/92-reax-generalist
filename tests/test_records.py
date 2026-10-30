"""tools/records: shared helpers, and every built record domain in data/generalist/rec/ (schema, scrub list, labels,
manifest hashes). DEV-GUIDELINES.md section 9: label map, scrub list and split stability."""

from __future__ import annotations

import glob
import hashlib
import importlib
import json
import os
import re

import pytest

from reax_subnet.spec import v5
from tools.records import common as R

MANIFESTS = sorted(glob.glob(os.path.join(R.REC, "*.manifest.json")))
DOMAINS = [os.path.basename(p).split(".")[0] for p in MANIFESTS]


# ---------------------------------------------------------------------------------------------------------- helpers

def test_split_never_depends_on_other_records():
    keys = [f"k{i}" for i in range(2000)]
    alone = {k: R.split_of("d", k, 0.05) for k in keys}
    assert all(R.split_of("d", k, 0.05) == alone[k] for k in reversed(keys))
    shares = {s: sum(v == s for v in alone.values()) / len(keys) for s in R.SPLITS}
    assert 0.03 < shares["test"] < 0.07 and 0.03 < shares["select"] < 0.07
    assert R.split_of("other", "k1", 0.05) in R.SPLITS          # the domain is part of the hash


def test_take_caps_by_hash_order_and_never_moves_records():
    recs = [{"key": f"k{i}", "split": R.split_of("d", f"k{i}", 0.05)} for i in range(5000)]
    a = R.take(recs, "d")
    b = R.take(recs + [{"key": "new", "split": "train"}], "d")
    assert sum(r["split"] == "train" for r in a) == R.MAX_TRAIN
    assert all(r["split"] == R.split_of("d", r["key"], 0.05) for r in b)


def test_clip_cuts_at_a_sentence_boundary():
    t = "One two three. Four five six. Seven eight nine."
    assert R.clip(t, 30) == "One two three. Four five six."
    assert R.clip(t, 5) == "" and R.clip(t, 100) == t


def test_cap_classes_drops_small_classes_and_caps_large_ones():
    recs = [{"key": f"a{i}", "split": "train", "c": "a"} for i in range(400)]
    recs += [{"key": f"b{i}", "split": "train", "c": "b"} for i in range(30)]
    recs += [{"key": f"m{i}", "split": "train", "c": "m"} for i in range(40)]
    recs += [{"key": f"z{i}", "split": "train", "c": "z"} for i in range(5)]
    out, rep = R.cap_classes(recs, lambda r: r["c"], "d")
    n = {c: sum(r["c"] == c for r in out) for c in "abmz"}
    assert n["z"] == 0 and rep["classes_dropped_under_min"] == {"z": 5}
    assert n["a"] == 3 * 40 and n["b"] == 30 and n["m"] == 40          # median of (30, 40, 400) is 40


def test_take_never_undoes_the_class_cap():
    """cap_classes and take use different hash orders: when both limits bind, the capped class keeps its capped share."""
    recs = [{"key": f"big{i}", "split": "train", "c": "big"} for i in range(9000)]
    recs += [{"key": f"m{c}{i}", "split": "train", "c": c} for c in "abc" for i in range(500)]
    capped, rep = R.cap_classes(recs, lambda r: r["c"], "d")
    assert sum(r["c"] == "big" for r in capped) == 1500                    # 3 x the median (500)
    final = R.take(capped, "d")
    share = sum(r["c"] == "big" for r in final) / len(final)
    assert len(final) == R.MAX_TRAIN and share < 0.6                       # 1500 / 3000 = 0.5 expected; the bug gave 1.0


def test_mc_row_is_valid_and_its_option_order_is_fixed_per_record():
    kw = dict(domain="d", task_type="t", area="language", split="train", index=0, instructions="Record\n\nQuestion?",
              options=["x", "y", "z"], gold="y", source="s", source_id="1", snapshot="2026-10-27", record_date=None)
    a, b = R.mc_row(shuffle_key="r1", **kw), R.mc_row(shuffle_key="r1", **kw)
    assert a == b
    v5.validate_mirror_row(a)
    q = a["questions"][0]
    assert list(q["criteria"]) == ["A", "B", "C"] and q["criteria"][q["expected"]] == "y"
    positions = {R.mc_row(shuffle_key=f"r{i}", **kw)["questions"][0]["expected"] for i in range(60)}
    assert positions == {"A", "B", "C"}
    with pytest.raises(ValueError):
        R.mc_row(shuffle_key="r", **dict(kw, gold="q"))


def test_scrub_pattern_matches_whole_words_only():
    pat = R.scrub_pattern(["final", "last call"])
    assert R.scrub_hits("The Final text; a last call.", pat) == ["final", "last call"]
    assert R.scrub_hits("finality and finals", pat) == []


# ---------------------------------------------------------------------------------------------------- built domains

def _rows(domain):
    out = []
    for s in R.SPLITS:
        p = os.path.join(R.REC, f"{domain}.{s}.jsonl")
        if os.path.exists(p):
            out += [json.loads(l) for l in open(p, encoding="utf-8")]
    return out


@pytest.mark.parametrize("domain", DOMAINS)
def test_domain_rows_schema_and_labels(domain):
    m = json.load(open(os.path.join(R.REC, f"{domain}.manifest.json")))
    rows = _rows(domain)
    assert rows
    for r in rows:
        v5.validate_mirror_row(r)
        assert (r["tier"], r["public"], r["task_type"]) == ("mirror", False, m["task_type"])
        assert r["scope"] == {"N": "new_domain", "T": "same_skill"}[r["part"]]
        q = r["questions"][0]
        assert q["criteria"][q["expected"]] in set(m["labels"].values())       # the label map of the builder
        assert r["source"].endswith(m["snapshot"])


@pytest.mark.parametrize("domain", DOMAINS)
def test_domain_scrub_list_words_never_remain(domain):
    b = importlib.import_module(f"tools.records.build_{domain}")
    for r in _rows(domain):
        record = r["questions"][0]["instructions"].rsplit("\n\n", 1)[0]
        assert R.scrub_hits(record, b.SCRUB_RE) == [], r["id"]


@pytest.mark.parametrize("domain", DOMAINS)
def test_domain_manifest_hashes_match_the_files(domain):
    m = json.load(open(os.path.join(R.REC, f"{domain}.manifest.json")))
    for name, sha in m["files"].items():
        assert hashlib.sha256(open(os.path.join(R.REC, name), "rb").read()).hexdigest() == sha
