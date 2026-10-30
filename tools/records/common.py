"""Shared pieces of the record domains (DEV-GUIDELINES.md sections 2, 4, 5).

* fetch: ``fetch_file`` stores a raw response unmodified under data/generalist/raw/<domain>/<snapshot>/ and records its URL,
  time and sha256 in ``fetch.json`` there. Raw files are untrusted data: build scripts parse them as data only (run them with
  ``python -I``; they add only the repository root to ``sys.path``).
* rows: ``mc_row`` builds one eval-v5.1 mirror row (tier mirror, part N, scope new_domain, public false): the record text in
  ``questions[0].instructions``, no state, options keyed by position codes A, B, ... in an order shuffled per record (gold
  position balance), the gold key from the record's structured label.
* splits: ``split_of`` assigns a record's group (recall number, bill id, ...) to test / select / train by sha256 thresholds, so
  a record never changes split on a re-fetch; ``take`` then caps each split by the same hash order.
* classes: ``cap_classes`` drops classes with fewer than ``MIN_CLASS`` records and caps every class at 3x the median class
  count of its split.
* text: ``clip`` cuts at a sentence boundary; ``scrub_hits`` finds outcome words that must not remain (the builders' tests
  assert there are none).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import re
import string
import urllib.request
from typing import Any, Iterable, Mapping, Sequence

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data", "generalist", "raw")
REC = os.path.join(ROOT, "data", "generalist", "rec")
SPLITS = ("train", "select", "test")
MAX_TRAIN, MAX_EVAL = 3000, 150
MIN_CLASS = 20
CLASS_CAP_X_MEDIAN = 3
FRESH_FROM = dt.date(2026, 8, 1)
USER_AGENT = "reax-subnet-records/1.0 (training-data build; respects documented rate limits)"
LETTERS = string.ascii_uppercase


# ------------------------------------------------------------------------------------------------------------ fetch

def raw_dir(domain: str, snapshot: str) -> str:
    d = os.path.join(RAW, domain, snapshot)
    os.makedirs(d, exist_ok=True)
    return d


def fetch_file(domain: str, snapshot: str, url: str, name: str, *, headers: Mapping[str, str] | None = None,
               data: bytes | None = None, timeout: int = 300) -> str:
    """Download ``url`` unmodified to raw/<domain>/<snapshot>/<name> (skipped if already recorded) and log it in fetch.json."""
    d = raw_dir(domain, snapshot)
    path = os.path.join(d, name)
    log_path = os.path.join(d, "fetch.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else {"domain": domain, "snapshot": snapshot, "files": {}}
    if name in log["files"] and os.path.exists(path):
        return path
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        status = resp.status
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(body)
    log["files"][name] = {"url": url, "method": "POST" if data else "GET", "status": status, "bytes": len(body),
                          "sha256": hashlib.sha256(body).hexdigest(),
                          "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(log_path, "w") as fh:
        json.dump(log, fh, indent=1)
    return path


def verify_raw(domain: str, snapshot: str) -> list[str]:
    """Problems with the raw files of a snapshot: missing files or a sha256 that differs from fetch.json."""
    d = os.path.join(RAW, domain, snapshot)
    log = json.load(open(os.path.join(d, "fetch.json")))
    out = []
    for name, meta in log["files"].items():
        p = os.path.join(d, name)
        if not os.path.exists(p):
            out.append(f"{name}: missing")
        elif hashlib.sha256(open(p, "rb").read()).hexdigest() != meta["sha256"]:
            out.append(f"{name}: sha256 differs from fetch.json")
    return out


# ------------------------------------------------------------------------------------------------------------ text

_SENT_END = re.compile(r"(?<=[.!?])\s+")


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clip(text: str, limit: int) -> str:
    """At most ``limit`` characters, cut after the last full sentence that fits (never mid-word; '' if no sentence fits)."""
    text = norm_ws(text)
    if len(text) <= limit:
        return text
    out = ""
    for sent in _SENT_END.split(text):
        nxt = (out + " " + sent).strip()
        if len(nxt) > limit:
            break
        out = nxt
    return out


def drop_sentences(text: str, pattern: re.Pattern) -> str:
    """The text without the sentences that match ``pattern``."""
    return " ".join(s for s in _SENT_END.split(norm_ws(text)) if not pattern.search(s))


def scrub_pattern(words: Sequence[str]) -> re.Pattern:
    if not words:
        return re.compile(r"(?!x)x")          # an empty list never matches
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)


def scrub_hits(text: str, pattern: re.Pattern) -> list[str]:
    return sorted({m.group(0).lower() for m in pattern.finditer(text or "")})


# ------------------------------------------------------------------------------------------------------------ splits

def _h(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def split_of(domain: str, group_key: str, eval_frac: float) -> str:
    """test if the group's hash falls in [0, f), select in [f, 2f), train otherwise: fixed per group, whatever else is fetched."""
    u = _h("split", domain, group_key) / 2 ** 64
    return "test" if u < eval_frac else "select" if u < 2 * eval_frac else "train"


def hash_order(domain: str, key: str) -> int:
    return _h("order", domain, key)


def cap_classes(records: list[dict], label_of, domain: str) -> tuple[list[dict], dict[str, Any]]:
    """Records of the classes with >= MIN_CLASS records (counted over all splits), each class capped at 3x the median class
    count of its split, keeping the first records of a hash order of its own (salt "|cap"): with the order ``take`` uses,
    the kept records of a capped class would come first in ``take`` too and refill the class, undoing the cap.
    Returns (records, report)."""
    from collections import Counter, defaultdict
    total = Counter(label_of(r) for r in records)
    keep = {c for c, n in total.items() if n >= MIN_CLASS}
    dropped = {c: n for c, n in total.items() if c not in keep}
    out, report = [], {"classes_dropped_under_min": dropped, "caps": {}}
    for split in SPLITS:
        rs = [r for r in records if r["split"] == split and label_of(r) in keep]
        by = defaultdict(list)
        for r in sorted(rs, key=lambda r: hash_order(f"{domain}|cap", r["key"])):
            by[label_of(r)].append(r)
        counts = sorted(len(v) for v in by.values())
        if not counts:
            continue
        med = counts[len(counts) // 2] if len(counts) % 2 else (counts[len(counts) // 2 - 1] + counts[len(counts) // 2]) / 2
        cap = max(1, int(CLASS_CAP_X_MEDIAN * med))
        report["caps"][split] = {"median": med, "cap": cap}
        for c, v in by.items():
            out += v[:cap]
    return out, report


def take(records: list[dict], domain: str) -> list[dict]:
    """At most MAX_TRAIN train and MAX_EVAL select / test records, by hash order (a re-fetch only adds or removes, never moves)."""
    out = []
    for split, cap in (("train", MAX_TRAIN), ("select", MAX_EVAL), ("test", MAX_EVAL)):
        rs = sorted((r for r in records if r["split"] == split), key=lambda r: hash_order(domain, r["key"]))
        out += rs[:cap]
    return out


# ------------------------------------------------------------------------------------------------------------ rows

def codes(k: int) -> list[str]:
    from reax_subnet.spec import v5
    return v5.option_codes(k)


def mc_row(*, domain: str, task_type: str, area: str, split: str, index: int, instructions: str,
           options: Sequence[str], gold: str, source: str, source_id: str, snapshot: str, record_date: dt.date | None,
           shuffle_key: str, part: str = "N", gold_type: bool = False, half: str = "hf", component: str | None = None,
           idk: bool = False, shuffle: bool = True) -> dict:
    """One mirror row: options in an order shuffled per record (seeded by ``shuffle_key``; ``shuffle=False`` keeps the
    given order, e.g. ordered levels), keyed A, B, ... by position. N rows by default; T record sets pass part "T" and
    their task type's gold flag / half / component (as in the dev set)."""
    opts = list(options)
    if gold not in opts or len(set(opts)) != len(opts):
        raise ValueError(f"{source_id}: gold not among the options or duplicate options")
    if shuffle:
        random.Random(f"options|{domain}|{shuffle_key}").shuffle(opts)
    ks = codes(len(opts))
    row = {"id": f"rec-{task_type}-{split}-{index}", "tier": "mirror", "half": half, "area": area,
           "scope": "new_domain" if part == "N" else "same_skill", "part": part, "task_type": task_type, "gold": gold_type,
           "source": f"{source}_{snapshot}", "source_id": source_id, "collected": snapshot,
           "collected_utc": f"{snapshot}T00:00:00Z", "public": False,
           "fresh": bool(record_date and record_date >= FRESH_FROM), "idk": idk, "split": split,
           "questions": [{"instructions": instructions, "criteria": dict(zip(ks, opts)), "expected": ks[opts.index(gold)]}]}
    if component:
        row["component"] = component
    return row


def write_domain(domain: str, rows: Iterable[dict], manifest: dict, sort_keys: bool = True) -> dict:
    """data/generalist/rec/<domain>.<split>.jsonl and <domain>.manifest.json (counts, class priors, option counts, gold
    position balance, sha256 of every file). ``sort_keys=False`` (every T record set, and any domain with yes/no or more
    than 26 options) keeps each row's key order as built, so options stay in their served order."""
    from collections import Counter
    from reax_subnet.spec import v5
    os.makedirs(REC, exist_ok=True)
    rows = list(rows)
    files = {}
    stats: dict[str, Any] = {}
    for split in SPLITS:
        rs = [r for r in rows if r["split"] == split]
        for r in rs:
            v5.validate_mirror_row(r)
            for q in r["questions"]:       # with sort_keys only orders it cannot change are allowed
                if sort_keys and list(q["criteria"]) != sorted(q["criteria"]):
                    raise ValueError(f"{r['id']}: option order {list(q['criteria'])[:4]}... would change when written "
                                     "(yes/no or more than 26 options are not supported by write_domain)")
        path = os.path.join(REC, f"{domain}.{split}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in rs:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=sort_keys) + "\n")
        files[os.path.basename(path)] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        gold_text = Counter(r["questions"][0]["criteria"][r["questions"][0]["expected"]] for r in rs)
        pos = Counter(list(r["questions"][0]["criteria"]).index(r["questions"][0]["expected"]) for r in rs)
        nopt = Counter(len(r["questions"][0]["criteria"]) for r in rs)
        stats[split] = {"rows": len(rs), "fresh": sum(r["fresh"] for r in rs), "class_prior": dict(gold_text.most_common()),
                        "gold_position": {LETTERS[k] if k < 26 else str(k): v for k, v in sorted(pos.items())},
                        "options": dict(sorted(nopt.items()))}
    manifest = dict(manifest, splits=stats, files=files)
    with open(os.path.join(REC, f"{domain}.manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest
