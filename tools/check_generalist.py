"""DEV-GUIDELINES.md section 7 checks for one N domain; writes data/generalist/reports/<domain>.json.

    python -I tools/check_generalist.py <domain> [--kind rec|gen] [--snapshot 2026-10-27] [--tokenizer /models/mammoth-1]

Checks (a domain is merged only if every applicable one passes):
* schema: ``v5.validate_mirror_row`` on 100 % of the rows, plus the N row contract (tier mirror, part N, scope new_domain,
  public false, ``split`` = its file, no state, one area / gold / half per task type, position-code or yes/no keys, no IDK).
* determinism: the builder run again gives byte-identical files (``--rebuild``).
* scrub (records): no word of the builder's ``SCRUB`` list in any record text.
* leak (records): a bag-of-words naive Bayes on the record text alone, trained on train, tested on test and select, is
  not far above the best constant answer (<= +0.25); its most telling words are listed for review. For one-of-many
  category domains (area retrieval) the subject matter is the tested skill, so the margin is reported, not a gate.
* shortcut: picking the longest option, the option with the most word overlap with the text, or the most frequent gold
  position is not better than the best constant answer by more than 0.05.
* balance: every gold position within 5 points of uniform on train (select / test reported); yes share 40-60 %.
* duplicates: no normalised record text twice across the splits, the other built domains and eval-v5/devset-v1/dev.jsonl.
* licence: recorded in the manifest and not marked "verify".
* prompt length: p99 of the served prompt (validator rendering and template) <= 2,000 tokens.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.records import common as R  # noqa: E402

DEV = os.path.join(R.ROOT, "eval-v5", "devset-v1", "dev.jsonl")
REPORTS = os.path.join(R.ROOT, "data", "generalist", "reports")
GEN = os.path.join(R.ROOT, "data", "generalist", "gen")
P99_LIMIT = 2000
LEAK_MARGIN, SHORTCUT_MARGIN, BALANCE_PTS = 0.25, 0.05, 0.05


def load(domain: str, kind: str) -> dict[str, list[dict]]:
    base = R.REC if kind == "rec" else GEN
    out = {}
    for s in R.SPLITS:
        p = os.path.join(base, f"{domain}.{s}.jsonl")
        out[s] = [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
    return out


def record_text(q: dict) -> str:
    """The record / rules part of a question: the instructions without the final question sentence."""
    txt = q.get("instructions", "")
    return txt.rsplit("\n\n", 1)[0] if "\n\n" in txt else txt


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9'-]+", text.lower())


# ------------------------------------------------------------------------------------------------------------ checks

def check_schema(rows: dict[str, list[dict]]) -> dict:
    from reax_subnet.spec import v5
    bad, meta = [], set()
    for split, rs in rows.items():
        for r in rs:
            try:
                v5.validate_mirror_row(r)
            except Exception as exc:
                bad.append(f"{r.get('id')}: {exc}")
                continue
            errs = []
            scope = {"N": "new_domain", "T": "same_skill"}.get(r.get("part"))
            if (r.get("tier"), r.get("scope"), r.get("public"), r.get("split")) != ("mirror", scope, False, split):
                errs.append("tier/part/scope/public/split")
            if r.get("state") is not None:
                errs.append("state set")
            if r.get("idk") and r.get("task_type") != v5.OMNI_TYPE:
                errs.append("idk outside omniscience")
            for q in r["questions"]:
                keys = list(q["criteria"])
                if set(keys) != {"yes", "no"} and keys != v5.option_codes(len(keys)):
                    errs.append("keys are neither position codes nor yes/no")
                if set(keys) == {"yes", "no"} and keys != ["yes", "no"]:
                    errs.append("yes/no options not in the served order (yes first)")
                if "idk" in keys:
                    errs.append("IDK key in criteria")
            meta.add((r["task_type"], r["area"], r["gold"], r["half"]))
            if errs:
                bad.append(f"{r['id']}: {', '.join(errs)}")
    if len({m[0] for m in meta}) != len(meta):
        bad.append(f"a task type with more than one area / gold / half: {sorted(meta)}")
    n = sum(len(v) for v in rows.values())
    return {"pass": not bad and n > 0, "rows": n, "problems": bad[:20], "problem_count": len(bad)}


def check_scrub(rows, builder) -> dict:
    pat = getattr(builder, "SCRUB_RE", None)
    if pat is None:
        return {"pass": True, "applies": False}
    hits = [(r["id"], R.scrub_hits(record_text(r["questions"][0]), pat)) for rs in rows.values() for r in rs]
    hits = [h for h in hits if h[1]]
    return {"pass": not hits, "hits": hits[:20], "hit_count": len(hits)}


def check_leak(rows) -> dict:
    """Multinomial naive Bayes on record words (train -> select + test) vs the best constant answer."""
    def label(r):
        q = r["questions"][0]
        return q["criteria"][q["expected"]]
    tr = rows["train"]
    ev = rows["select"] + rows["test"]
    if not tr or not ev:
        return {"pass": True, "applies": False}
    classes = sorted({label(r) for r in tr})
    vocab = collections.Counter(w for r in tr for w in set(words(record_text(r["questions"][0]))))
    vocab = {w for w, n in vocab.items() if n >= 3}
    cnt = {c: collections.Counter() for c in classes}
    prior = collections.Counter(label(r) for r in tr)
    for r in tr:
        cnt[label(r)].update(w for w in words(record_text(r["questions"][0])) if w in vocab)
    tot = {c: sum(cnt[c].values()) + len(vocab) for c in classes}

    def predict(text):
        ws = [w for w in words(text) if w in vocab]
        return max(classes, key=lambda c: math.log(prior[c] / len(tr)) + sum(math.log((cnt[c][w] + 1) / tot[c]) for w in ws))
    acc = sum(predict(record_text(r["questions"][0])) == label(r) for r in ev) / len(ev)
    const = max(collections.Counter(label(r) for r in ev).values()) / len(ev)
    telling = {}
    for c in classes:
        others = {o for o in classes if o != c}
        score = {w: math.log((cnt[c][w] + 1) / tot[c]) - math.log((sum(cnt[o][w] for o in others) + 1) /
                                                                   sum(tot[o] for o in others)) for w in vocab}
        telling[c] = [w for w, _ in sorted(score.items(), key=lambda t: -t[1])[:12]]
    # One-of-many category domains (area retrieval, like the dev set's nhtsa_recall_component): the record's subject matter is
    # the skill being tested and always predicts the category; label names and synonyms are the scrub check's job. There the
    # margin is reported for review, not a gate. Status / severity domains keep the margin as a gate.
    category = ({r["area"] for rs in rows.values() for r in rs} == {"retrieval"}
                or {r["part"] for rs in rows.values() for r in rs} == {"T"})      # T sets: standard labelled tasks
    return {"pass": category or acc <= const + LEAK_MARGIN, "category_domain": category, "nb_accuracy": round(acc, 4),
            "best_constant": round(const, 4), "margin_allowed": None if category else LEAK_MARGIN, "telling_words": telling,
            "eval_items": len(ev)}


def check_shortcut(rows) -> dict:
    rs = [r for v in rows.values() for r in v]
    if not rs:
        return {"pass": False}
    res, const = {}, 0.0
    qs = [(r, q) for r in rs for q in r["questions"]]
    gold_text = collections.Counter(q["criteria"][q["expected"]] for _, q in qs)
    const = max(gold_text.values()) / len(qs)
    pos = collections.Counter(list(q["criteria"]).index(q["expected"]) for _, q in qs)
    best_pos = pos.most_common(1)[0][0]
    longest = overlap = position = 0
    for r, q in qs:
        keys = list(q["criteria"])
        texts = [str(q["criteria"][k]) for k in keys]
        if keys[max(range(len(texts)), key=lambda i: len(texts[i]))] == q["expected"]:
            longest += 1
        qw = set(words(q["instructions"]))
        if keys[max(range(len(texts)), key=lambda i: len(qw & set(words(texts[i]))))] == q["expected"]:
            overlap += 1
        if keys.index(q["expected"]) == best_pos:
            position += 1
    n = len(qs)
    res = {"longest_option": round(longest / n, 4), "most_word_overlap": round(overlap / n, 4),
           "most_frequent_position": round(position / n, 4), "best_constant_answer": round(const, 4)}
    chance = max(const, max(1 / len(q["criteria"]) for _, q in qs))
    res["pass"] = all(v <= chance + SHORTCUT_MARGIN for k, v in res.items() if k != "best_constant_answer")
    return res


def check_balance(rows) -> dict:
    out = {"pass": True}
    for split, rs in rows.items():
        qs = [q for r in rs for q in r["questions"]]
        if not qs:
            continue
        yesno = [q for q in qs if set(q["criteria"]) == {"yes", "no"}]
        mc = [q for q in qs if set(q["criteria"]) != {"yes", "no"}]
        info = {}
        if mc:
            ks = collections.Counter(len(q["criteria"]) for q in mc).most_common(1)[0][0]
            same = [q for q in mc if len(q["criteria"]) == ks]
            pos = collections.Counter(list(q["criteria"]).index(q["expected"]) for q in same)
            shares = [pos.get(i, 0) / len(same) for i in range(ks)]
            dev = max(abs(s - 1 / ks) for s in shares)
            info["gold_position_shares"] = [round(s, 3) for s in shares]
            info["max_deviation"] = round(dev, 3)
            if split == "train" and dev > BALANCE_PTS:
                out["pass"] = False
        if yesno:
            ys = sum(q["expected"] == "yes" for q in yesno) / len(yesno)
            info["yes_share"] = round(ys, 3)
            if split == "train" and not 0.40 <= ys <= 0.60:
                out["pass"] = False
        out[split] = info
    return out


def check_duplicates(domain: str, rows) -> dict:
    seen, dups = {}, []
    for split, rs in rows.items():
        for r in rs:
            for q in r["questions"]:
                k = norm(record_text(q))
                if k in seen and seen[k] != r["id"]:
                    dups.append((r["id"], seen[k]))
                seen.setdefault(k, r["id"])
    others = []
    for p in sorted(glob.glob(os.path.join(R.REC, "*.jsonl")) + glob.glob(os.path.join(GEN, "*.jsonl")) + [DEV]):
        if os.path.basename(p).startswith(domain + "."):
            continue
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            for q in r.get("questions", []):
                k = norm(record_text(q))
                if k in seen:
                    others.append((seen[k], os.path.basename(p), r.get("id")))
    return {"pass": not dups and not others, "within_domain": dups[:20], "against_other_files": others[:20],
            "count": len(dups) + len(others)}


def check_licence(manifest: dict) -> dict:
    lic = manifest.get("licence") or {}
    name = json.dumps(lic).lower()
    return {"pass": bool(lic) and "verify" not in name, "licence": lic}


def check_prompt_length(rows, tokenizer: str) -> dict:
    from transformers import PreTrainedTokenizerFast
    from reax_subnet.spec import prompt as P
    from reax_subnet.spec import v5wire
    from reax_subnet.spec.templates import template_path
    tok = PreTrainedTokenizerFast(tokenizer_file=os.path.join(tokenizer, "tokenizer.json") if os.path.isdir(tokenizer) else tokenizer)
    tok.chat_template = open(template_path("qwen.jinja"), encoding="utf-8").read()
    lens = []
    for rs in rows.values():
        for r in v5wire.flatten([v5wire.cap_item(x, 0) for x in rs]):
            rend = P.render(r["state"], r["question"])
            text = tok.apply_chat_template([{"role": "system", "content": rend.system}, {"role": "user", "content": rend.user}],
                                           tokenize=False, add_generation_prompt=True, enable_thinking=False)
            lens.append(len(tok.encode(text, add_special_tokens=False)))
    lens.sort()
    p99 = lens[min(len(lens) - 1, int(0.99 * len(lens)))]
    return {"pass": p99 <= P99_LIMIT, "p50": lens[len(lens) // 2], "p99": p99, "max": lens[-1], "limit": P99_LIMIT}


def check_determinism_gen(task: str) -> dict:
    """Generate the task again into a temporary folder: every file byte-identical to the stored one."""
    import tempfile
    from tools import gen_generalist as G
    files = sorted(glob.glob(os.path.join(GEN, f"{task}.*.jsonl")))
    before = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files}
    with tempfile.TemporaryDirectory() as tmp:
        G.generate(G.task_modules()[task], tmp)
        after = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                 for p in glob.glob(os.path.join(tmp, f"{task}.*.jsonl"))}
    return {"pass": bool(before) and before == after, "files": len(before), "changed": sorted(k for k in before if before[k] != after.get(k))}


def check_second_solver(rows, mod) -> dict:
    """The task's solve_text reads only the rendered question and must give the stored gold key on 100 % of questions."""
    n, bad = 0, []
    for rs in rows.values():
        for r in rs:
            for j, q in enumerate(r["questions"]):
                n += 1
                try:
                    got = mod.solve_text(q)
                except Exception as exc:
                    got = f"error: {type(exc).__name__}: {exc}"
                if got != q["expected"]:
                    bad.append((f"{r['id']}#{j}", q["expected"], got))
    return {"pass": n > 0 and not bad, "questions": n, "disagreements": len(bad), "examples": bad[:10]}


def check_boundary_tests(task: str) -> dict:
    path = os.path.join(R.ROOT, "tests", f"test_gen_{task}.py")
    if not os.path.exists(path):
        return {"pass": False, "problem": f"missing {os.path.relpath(path, R.ROOT)}"}
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", path], capture_output=True, text=True, cwd=R.ROOT,
                         env=dict(os.environ, CUDA_VISIBLE_DEVICES=""))
    tail = (run.stdout.strip().splitlines() or [""])[-1]
    return {"pass": run.returncode == 0 and " passed" in tail, "summary": tail}


def check_determinism(domain: str, kind: str, snapshot: str | None) -> dict:
    if kind == "gen":
        return check_determinism_gen(domain)
    base = R.REC
    files = sorted(glob.glob(os.path.join(base, f"{domain}.*.jsonl")))
    before = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files}
    script = os.path.join(R.ROOT, "tools", "records", f"build_{domain}.py")
    cmd = [sys.executable, "-I", script] + (["--snapshot", snapshot] if snapshot else [])
    run = subprocess.run(cmd, capture_output=True, text=True)
    after = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in files}
    return {"pass": run.returncode == 0 and before == after, "files": len(before),
            "changed": sorted(k for k in before if before[k] != after.get(k)), "returncode": run.returncode}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("domain")
    ap.add_argument("--kind", default="rec", choices=("rec", "gen"))
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--tokenizer", default="/models/mammoth-1")
    ap.add_argument("--no-rebuild", action="store_true")
    a = ap.parse_args(argv)
    rows = load(a.domain, a.kind)
    manifest = json.load(open(os.path.join(R.REC if a.kind == "rec" else GEN, f"{a.domain}.manifest.json")))
    builder = importlib.import_module(f"tools.records.build_{a.domain}") if a.kind == "rec" else None
    report = {"domain": a.domain, "kind": a.kind, "rows": {s: len(v) for s, v in rows.items()}, "checks": {}}
    c = report["checks"]
    c["schema"] = check_schema(rows)
    if not a.no_rebuild:
        c["determinism"] = check_determinism(a.domain, a.kind, a.snapshot or manifest.get("snapshot"))
    if a.kind == "rec":
        c["scrub"] = check_scrub(rows, builder)
        c["leak"] = check_leak(rows)
        c["licence"] = check_licence(manifest)
    else:
        mod = importlib.import_module(f"tools.gen.{a.domain}")
        c["second_solver"] = check_second_solver(rows, mod)
        c["boundary_tests"] = check_boundary_tests(a.domain)
    c["shortcut"] = check_shortcut(rows)
    c["balance"] = check_balance(rows)
    c["duplicates"] = check_duplicates(a.domain, rows)
    c["prompt_length"] = check_prompt_length(rows, a.tokenizer)
    report["pass"] = all(v.get("pass") for v in c.values())
    os.makedirs(REPORTS, exist_ok=True)
    json.dump(report, open(os.path.join(REPORTS, f"{a.domain}.json"), "w"), indent=1, ensure_ascii=False)
    for k, v in c.items():
        detail = {x: y for x, y in v.items() if x not in ("pass", "telling_words", "problems", "hits", "within_domain", "against_other_files")}
        print(f"  {'PASS' if v.get('pass') else 'FAIL'}  {k:14s} {json.dumps(detail, ensure_ascii=False)[:230]}")
    print(f"{a.domain}: {'PASS' if report['pass'] else 'FAIL'} -> {os.path.relpath(os.path.join(REPORTS, a.domain + '.json'), R.ROOT)}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
