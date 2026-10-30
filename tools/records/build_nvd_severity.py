"""#8 NVD CVE records -> CVSS v3 base severity: eval-v5.1 mirror rows (part N, task type ``nvd_cvss_severity``).

    python -I tools/records/build_nvd_severity.py --snapshot 2026-10-27

Records: the CVE records of the stored NVD API 2.0 pages (one-day publication windows 2024-01-01 to 2026-10-26), read as data.
* Label: the ``baseSeverity`` of the structured CVSS v3 metrics only. Preferred: the NVD primary metric (``type`` Primary) of
  cvssMetricV31, else of cvssMetricV30; without a primary v3 metric the CNA / ADP (Secondary) metrics of cvssMetricV31, else
  of cvssMetricV30, when they all agree. Dropped: records without a v3 metric, with primary metrics that disagree, with
  secondary metrics that disagree (when there is no primary), and severity NONE. "Primary" is NVD's designation: NVD's own
  score when it has scored the record, and (in records from 2026-08 on) the CNA's score when that is the only one.
* Not used: any metric, vector or score, the weaknesses (CWE), the references and their tags, configurations, vendor
  comments. Dropped as well: CVEs that are aliases of a GitHub-reviewed advisory in the GitHub Advisory Database snapshot of
  the ghsa_severity domain (the same CVE text would be in both domains; that domain keeps it), descriptions marked
  ``** DISPUTED **`` and the like, and CVEs whose item text (the description after scrubbing and cutting) is the same as
  another CVE's: one is kept when their severities agree, none when not (Oracle's advisories, for example, differ only in
  the sentences that state the CVSS vector and score).
* Record text: the published year and the English description, cut at a sentence boundary. Every sentence that contains a
  word of ``SCRUB`` (the severity words, CVSS / score / rating words, the VulDB "classified as critical / problematic"
  phrases), a CVSS vector or a credit line ("reported by ...") is removed; e-mail addresses and phone numbers are masked.
* Group key: the CVE id.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import random
import re
import sys
import tarfile
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "nvd_severity"
TASK = "nvd_cvss_severity"
AREA = "language"           # a severity / class domain, as the other severity domains
EVAL_FRAC = 0.05            # more than ~3,300 records are kept
TEXT_LIMIT = 1000
LABELS = {"LOW": "Low (CVSS v3 base score 0.1-3.9)",
          "MEDIUM": "Medium (CVSS v3 base score 4.0-6.9)",
          "HIGH": "High (CVSS v3 base score 7.0-8.9)",
          "CRITICAL": "Critical (CVSS v3 base score 9.0-10.0)"}
GHSA = ("ghsa_severity", "2026-10-27")      # the GitHub Advisory Database snapshot whose CVEs are left to that domain
SCRUB = ("low", "medium", "moderate", "high", "critical", "critically", "criticality", "important", "severity", "severities",
         "severe", "severely", "cvss", "cvssv3", "cvssv31", "cvss3", "cvss v3", "base score", "score", "scores", "scored",
         "scoring", "rated", "rating", "ratings", "classified as", "declared as", "problematic", "risk level")
SCRUB_RE = R.scrub_pattern(SCRUB)
VECTOR_RE = re.compile(r"\b(AV|AC|PR|UI|S|C|I|A):[NALPHRUC]\b|CVSS:\d", re.I)
CREDIT_RE = re.compile(r"\b(reported|discovered|found|identified|disclosed) by\b|\bthanks? to\b|\bcredit(s|ed)? (to|goes)\b|"
                       r"\backnowledg", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"\+\d{1,3}[\d ()./-]{6,}\d|\b(tel|phone|telephone|mobile|fax)\b\.?:?\s*[\d ()+./-]{7,}\d", re.I)
SENT_RE = re.compile(r"(?<=[.!?])\s+")      # the sentence split of common.clip
QUESTIONS = ("What is the CVSS v3 base severity of this vulnerability?",
             "Which CVSS v3 severity rating was assigned to this vulnerability?",
             "How severe is this vulnerability on the CVSS v3 scale?",
             "Which CVSS v3 base severity does this CVE record carry?",
             "Pick the CVSS v3 base severity of the vulnerability described above.")


def label_of(cve: dict) -> tuple[str | None, str]:
    """(severity, how it was chosen) from the structured v3 metrics; (None, reason) for a dropped record."""
    m = cve.get("metrics") or {}
    for key in ("cvssMetricV31", "cvssMetricV30"):
        sevs = {x.get("cvssData", {}).get("baseSeverity") for x in m.get(key, []) if x.get("type") == "Primary"}
        if len(sevs) > 1:
            return None, "conflicting primary metrics"
        if sevs:
            return sevs.pop(), f"{key} primary"
    for key in ("cvssMetricV31", "cvssMetricV30"):
        sevs = {x.get("cvssData", {}).get("baseSeverity") for x in m.get(key, [])}
        if len(sevs) > 1:
            return None, "conflicting secondary metrics, no primary"
        if sevs:
            return sevs.pop(), f"{key} secondary"
    return None, "no CVSS v3 metric"


def english(cve: dict) -> str:
    return R.norm_ws(" ".join(d.get("value", "") for d in cve.get("descriptions", []) if d.get("lang") == "en"))


def ghsa_cves() -> set[str]:
    """CVE aliases of the GitHub-reviewed advisories in the ghsa_severity raw tarball (read as data, sha256 checked)."""
    dom, snap = GHSA
    problems = R.verify_raw(dom, snap)
    if problems:
        raise SystemExit(f"{dom} raw files: {problems}")
    out: set[str] = set()
    for tp in sorted(glob.glob(os.path.join(R.RAW, dom, snap, "*.tar.gz"))):
        with tarfile.open(tp, "r:gz") as tf:
            for m in tf:
                if m.isfile() and "/advisories/github-reviewed/" in m.name and m.name.endswith(".json"):
                    try:
                        adv = json.loads(tf.extractfile(m).read())
                    except ValueError:
                        continue
                    out.update(a for a in adv.get("aliases", []) if isinstance(a, str) and a.startswith("CVE-"))
    return out


def records(raw: str) -> list[dict]:
    out = {}
    for p in sorted(glob.glob(os.path.join(raw, "cves", "*.json"))):
        for v in json.load(open(p, encoding="utf-8")).get("vulnerabilities", []):
            cve = v.get("cve") or {}
            cid = cve.get("id")
            if isinstance(cid, str) and re.fullmatch(r"CVE-\d{4}-\d{4,}", cid):
                out[cid] = cve
    return [out[k] for k in sorted(out)]


def clean(desc: str) -> str:
    keep = []
    for sent in SENT_RE.split(R.norm_ws(desc)):
        if SCRUB_RE.search(sent) or VECTOR_RE.search(sent) or CREDIT_RE.search(sent):
            continue
        keep.append(PHONE_RE.sub("[phone]", EMAIL_RE.sub("[email]", sent)))
    return " ".join(keep)


def description(cve: dict) -> str | None:
    """The English description as it goes into the item: scrubbed sentences removed, masked, cut; None if too little is left."""
    desc = R.clip(clean(english(cve)), TEXT_LIMIT)
    return desc if len(desc) >= 40 and not R.scrub_hits(desc, SCRUB_RE) else None


def render(cve: dict, desc: str, rng: random.Random) -> str | None:
    record = f"CVE record (published {cve['published'][:4]})\nDescription: {desc}"
    if R.scrub_hits(record, SCRUB_RE):
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def published(cve: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(cve.get("published", "")[:10])
    except ValueError:
        return None


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs = records(raw)
    gh = ghsa_cves()
    dropped: Counter = Counter()
    how: Counter = Counter()
    cand = []
    for cve in recs:
        sev, why = label_of(cve)
        desc = english(cve)
        if sev is None:
            dropped[why] += 1
        elif sev not in LABELS:
            dropped[f"severity {sev}"] += 1
        elif cve["id"] in gh:
            dropped["CVE of a GitHub-reviewed advisory (left to ghsa_severity)"] += 1
        elif not desc:
            dropped["no English description"] += 1
        elif desc.startswith("**"):
            dropped["description marked ** ... ** (disputed, unsupported, ...)"] += 1
        else:
            how[why] += 1
            cand.append({"cve": cve, "sev": sev, "key": cve["id"]})
    by_text: dict[str, list[dict]] = {}
    unrendered = 0
    for r in cand:
        r["desc"] = description(r["cve"])
        if r["desc"] is None:
            unrendered += 1
            continue
        by_text.setdefault(r["desc"].lower(), []).append(r)
    kept = []
    for _, group in sorted(by_text.items()):
        if len({r["sev"] for r in group}) > 1:
            dropped["same item text as a CVE of another severity"] += len(group)
            continue
        group.sort(key=lambda r: R.hash_order(DOMAIN, r["key"]))
        dropped["same item text as a CVE of the same severity (one kept)"] += len(group) - 1
        rec = group[0]
        text = render(rec["cve"], rec["desc"], random.Random(f"{DOMAIN}|{rec['key']}"))
        if text is None:
            unrendered += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    kept.sort(key=lambda r: r["key"])
    capped, class_report = R.cap_classes(kept, lambda r: r["sev"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["sev"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["sev"]], source="nvd",
                             source_id=rec["key"], snapshot=snapshot, record_date=published(rec["cve"]),
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {"api": "https://services.nvd.nist.gov/rest/json/cves/2.0", "pages": len(fetch["files"]),
                            "sampling": fetch.get("sampling"),
                            "files_sha256": {n: f["sha256"] for n, f in sorted(fetch["files"].items())},
                            "excluded_cves_from": f"data/generalist/raw/{GHSA[0]}/{GHSA[1]} (github-reviewed aliases)"},
                "label_field": "metrics.cvssMetricV31 / cvssMetricV30 [].cvssData.baseSeverity (primary preferred)",
                "labels": LABELS, "records_read": len(recs), "label_from": dict(sorted(how.items())),
                "dropped": dict(sorted(dropped.items())), "dropped_unrenderable_or_scrub": unrendered,
                "kept_before_caps": len(kept), **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://nvd.nist.gov/vuln/detail/{row['source_id']}"


_RAW: dict[str, dict[str, dict]] = {}


def _raw_records(snapshot: str) -> dict[str, dict]:
    """CVE id -> the record as stored, read once per process."""
    if snapshot not in _RAW:
        out = {}
        for p in sorted(glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "cves", "*.json"))):
            for v in json.load(open(p, encoding="utf-8")).get("vulnerabilities", []):
                out[v["cve"]["id"]] = v["cve"]
        _RAW[snapshot] = out
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The severity read again from the stored record by a simpler rule (the metric whose source is NVD itself,
    nvd@nist.gov, v3.1 before v3.0, else the single severity of all v3 metrics), and whether every sentence of the item's
    description is in the record's English description and the year is its publication year."""
    cve = _raw_records(snapshot).get(row["source_id"])
    if cve is None:
        return None, False
    m = cve.get("metrics", {})
    sev = None
    for key in ("cvssMetricV31", "cvssMetricV30"):
        nvd = [x["cvssData"]["baseSeverity"] for x in m.get(key, []) if x.get("source") == "nvd@nist.gov"]
        if nvd:
            sev = nvd[0] if len(set(nvd)) == 1 else None
            break
    if sev is None:
        allv = {x["cvssData"]["baseSeverity"] for key in ("cvssMetricV31", "cvssMetricV30") for x in m.get(key, [])}
        v31 = {x["cvssData"]["baseSeverity"] for x in m.get("cvssMetricV31", [])}
        sev = (v31 or allv).pop() if len(v31 or allv) == 1 else None
    text = row["questions"][0]["instructions"].split("\n\n")[0]
    year_ok = text.startswith(f"CVE record (published {cve.get('published', '')[:4]})")
    desc = text.split("Description: ", 1)[1] if "Description: " in text else ""
    raw_desc = " ".join(d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en")
    raw_desc = re.sub(r"\s+", " ", raw_desc)
    sents = [s for s in re.split(r"(?<=[.!?])\s+", desc) if s]
    text_ok = bool(sents) and year_ok and all(s in raw_desc or "[email]" in s or "[phone]" in s for s in sents)
    return LABELS.get(sev), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), classes {m['splits'][s]['class_prior']}, "
              f"gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']}, label from {m['label_from']}, kept before caps {m['kept_before_caps']}")
    print(f"dropped {m['dropped']}, unrenderable / scrub {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
