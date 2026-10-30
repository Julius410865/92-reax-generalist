"""Audit of a record domain (DEV-GUIDELINES.md 4 and 7): 50 items checked against the source record, 150 if none is wrong;
plus 20 random items with source links for the owner's spot check.

    python -I tools/records/audit.py <domain> --snapshot 2026-10-27 [--n 50]

The builder module provides ``source_url(row, snapshot)`` (a link to the record at the pinned snapshot) and
``recheck(row, snapshot) -> (label, text_ok)``: the label read again from the raw file by an independent parse, and whether
the item text is the record's own wording. Writes data/generalist/reports/<domain>.audit.json and <domain>.spotcheck.md.
The programmatic re-check covers every audited item; items are also listed for reading.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

REPORTS = os.path.join(R.ROOT, "data", "generalist", "reports")


def rows_of(domain: str) -> list[dict]:
    out = []
    for s in R.SPLITS:
        p = os.path.join(R.REC, f"{domain}.{s}.jsonl")
        if os.path.exists(p):
            out += [json.loads(l) for l in open(p, encoding="utf-8")]
    return out


def gold_text(r: dict) -> str:
    q = r["questions"][0]
    return q["criteria"][q["expected"]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("domain")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args(argv)
    b = importlib.import_module(f"tools.records.build_{a.domain}")
    rows = rows_of(a.domain)
    rng = random.Random(f"audit|{a.domain}")
    sample = rng.sample(rows, min(a.n, len(rows)))
    items, errors = [], 0
    for r in sample:
        label, text_ok = b.recheck(r, a.snapshot)
        ok = label == gold_text(r) and text_ok
        errors += not ok
        items.append({"id": r["id"], "split": r["split"], "source_id": r["source_id"], "url": b.source_url(r, a.snapshot),
                      "gold": gold_text(r), "label_in_source": label, "text_is_record_wording": text_ok, "ok": ok,
                      "text": r["questions"][0]["instructions"]})
    if errors == 0 and len(rows) > a.n:          # 0 errors in 50: extend to 150 (DEV-GUIDELINES 7)
        rest = [r for r in rows if r not in sample]
        for r in rng.sample(rest, min(150 - len(sample), len(rest))):
            label, text_ok = b.recheck(r, a.snapshot)
            ok = label == gold_text(r) and text_ok
            errors += not ok
            items.append({"id": r["id"], "split": r["split"], "source_id": r["source_id"], "url": b.source_url(r, a.snapshot),
                          "gold": gold_text(r), "label_in_source": label, "text_is_record_wording": text_ok, "ok": ok,
                          "text": r["questions"][0]["instructions"]})
    rate = errors / len(items) if items else 1.0
    report = {"domain": a.domain, "audited": len(items), "errors": errors, "error_rate": round(rate, 4),
              "pass": rate <= 0.02, "method": "label re-read from the raw source file by an independent parse; item text "
              "compared with the record's own fields", "items": items}
    os.makedirs(REPORTS, exist_ok=True)
    json.dump(report, open(os.path.join(REPORTS, f"{a.domain}.audit.json"), "w"), indent=1, ensure_ascii=False)
    spot = random.Random(f"spot|{a.domain}").sample(rows, min(20, len(rows)))
    with open(os.path.join(REPORTS, f"{a.domain}.spotcheck.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {a.domain}: 20 random items for a spot check\n\nCheck the gold label against the linked source record.\n\n")
        for i, r in enumerate(spot, 1):
            fh.write(f"## {i}. {r['source_id']} ({r['split']}): gold = {gold_text(r)}\n\n{b.source_url(r, a.snapshot)}\n\n```\n"
                     f"{r['questions'][0]['instructions']}\n```\n\n")
    print(f"{a.domain}: audited {len(items)}, errors {errors} ({rate:.1%}) -> {'PASS' if report['pass'] else 'FAIL'}; "
          f"spot-check list: data/generalist/reports/{a.domain}.spotcheck.md")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
