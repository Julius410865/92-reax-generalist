"""arxiv_category in the eval's format, from the arXiv API (CC0 1.0 descriptive metadata).

    python -I tools/records/build_arxiv_category.py --fetch      # download (1 request / 3 s), then build
    python -I tools/records/build_arxiv_category.py              # build from the saved pages only

* Label set: the 41 categories of the dev items (eval-v5/devset-v1), every item offers all 41, keys A.. shuffled.
* Records: for each category the newest submissions (arXiv API ``cat:<c>``, sorted by submission date); a paper is kept
  only when its ``arxiv:primary_category`` is that category (cross-lists dropped), so the gold is the paper's primary
  subject class as recorded by arXiv. Papers whose abstract is one of the dev items' abstracts are dropped.
* Record text: the abstract (whitespace normalised), nothing else (no title, authors, ids or comments).
* Splits by sha256 of the arXiv id: 150 test, 150 select, the rest train (at most 2,500).
* Raw API pages: data/generalist/raw/arxiv_api/<date>/<category>.xml (dataset/data/generalist/raw/ mirrors them).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
DEV = os.path.join(ROOT, "eval-v5", "devset-v1", "dev.jsonl")
SNAPSHOT = "2026-10-29"
RAW = os.path.join(ROOT, "dataset", "data", "generalist", "raw", "arxiv_api", SNAPSHOT)
API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
PER_CATEGORY = 150
QUESTION = "In which arXiv category (primary subject class) was this paper filed?"


def labels() -> list[str]:
    dev = [r for r in map(json.loads, open(DEV, encoding="utf-8")) if r["task_type"] == "arxiv_category"]
    return sorted({v for r in dev for q in r["questions"] for v in q["criteria"].values()})


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def fetch(cats: list[str]) -> None:
    os.makedirs(RAW, exist_ok=True)
    for c in cats:
        path = os.path.join(RAW, f"{c}.xml")
        if os.path.exists(path):
            continue
        q = urllib.parse.urlencode({"search_query": f"cat:{c}", "sortBy": "submittedDate", "sortOrder": "descending",
                                    "start": 0, "max_results": PER_CATEGORY})
        with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
            data = r.read()
        open(path, "wb").write(data)
        print(f"{c}: {len(data)} bytes", flush=True)
        time.sleep(3.1)                                   # arXiv API terms: at most one request every three seconds


def build(cats: dict[str, str]) -> dict:
    from reax_subnet.spec import v5
    dev_abs = {norm(q["instructions"].split("\n", 1)[1].rsplit("\n\n", 1)[0]).lower()
               for r in map(json.loads, open(DEV, encoding="utf-8")) if r["task_type"] == "arxiv_category" for q in r["questions"]}
    recs, dropped = {}, {"cross_list": 0, "dev_abstract": 0, "short": 0}
    for code in cats:
        root = ET.parse(os.path.join(RAW, f"{code}.xml")).getroot()
        for e in root.findall("a:entry", NS):
            aid = e.find("a:id", NS).text.rsplit("/abs/", 1)[-1].split("v")[0]
            prim = e.find("arxiv:primary_category", NS).attrib["term"]
            abstract = norm(e.find("a:summary", NS).text or "")
            if prim != code:
                dropped["cross_list"] += 1
                continue
            if abstract.lower() in dev_abs:
                dropped["dev_abstract"] += 1
                continue
            if len(abstract) < 200:
                dropped["short"] += 1
                continue
            recs[aid] = {"id": aid, "label": cats[code], "abstract": abstract,
                         "published": e.find("a:published", NS).text[:10]}
    order = sorted(recs, key=lambda a: hashlib.sha256(f"arxiv_category|{a}".encode()).hexdigest())
    splits = {"test": order[:150], "select": order[150:300], "train": order[300:2800]}
    all_labels = sorted(cats.values())
    out = {}
    for split, ids in splits.items():
        rows = []
        for i, aid in enumerate(sorted(ids)):
            rec = recs[aid]
            rng = random.Random(f"arxiv_category|{aid}")
            opts = list(all_labels)
            rng.shuffle(opts)
            keys = v5.option_codes(len(opts))
            row = {"id": f"rec-arxiv_category_api-{split}-{i}", "tier": "mirror", "half": "hf", "area": "retrieval", "scope": "same_skill",
                   "part": "T", "task_type": "arxiv_category", "gold": True, "source": "arxiv_api_metadata_cc0", "source_id": aid,
                   "collected": SNAPSHOT, "collected_utc": f"{SNAPSHOT}T00:00:00Z", "public": False,
                   "fresh": rec["published"] >= "2026-08-01", "idk": False, "split": split,
                   "questions": [{"instructions": f"Abstract of a paper posted to arXiv:\n{rec['abstract']}\n\n{QUESTION}",
                                  "criteria": dict(zip(keys, opts)), "expected": keys[opts.index(rec["label"])]}]}
            v5.validate_mirror_row(row)
            rows.append(row)
        path = os.path.join(ROOT, "dataset", "t2", f"arxiv_category_api.{split}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        out[split] = len(rows)
    return {"records": len(recs), "dropped": dropped, "splits": out,
            "per_label_train": dict(sorted(__import__("collections").Counter(recs[a]["label"] for a in splits["train"]).items()))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args(argv)
    labs = labels()
    cats = {lab.split(" ", 1)[0]: lab for lab in labs}
    if len(cats) != 41:
        raise SystemExit(f"expected the 41 dev labels, got {len(cats)}")
    if a.fetch:
        fetch(sorted(cats))
    print(json.dumps(build(cats), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
