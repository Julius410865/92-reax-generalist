"""#9 Package security advisories -> severity: eval-v5.1 mirror rows (part N, task type ``ghsa_severity``).

    python -I tools/records/build_ghsa_severity.py --snapshot 2026-10-27

Records: the reviewed advisories of the GitHub Advisory Database (advisories/github-reviewed/**/GHSA-*.json in the raw
tarball, OSV format), read as data. The unreviewed tree in the same tarball is not used.
* Label: the structured ``database_specific.severity`` field only (LOW / MODERATE / HIGH / CRITICAL). Second source: the
  record's CVSS v3 vector (``severity[type=CVSS_V3]``), whose base score is computed here and mapped to the CVSS rating
  bands (0.1-3.9 low, 4.0-6.9 moderate, 7.0-8.9 high, 9.0-10.0 critical). Kept only where both agree; advisories without a
  CVSS v3 vector (CVSS v4 only, or none) have no second source and are dropped. Also dropped: withdrawn advisories, a
  missing or unknown severity, records without a summary or with under MIN_DETAIL_WORDS words of details left. Near-copies
  (the same summary and details; the same packages and summary, as in batches of advisories filed from one template; the
  same record text once rendered) keep one advisory, the lowest id, and are all dropped when their severities differ
  (the text cannot tell them apart), so a near-copy never sits in a second split.
* Record text: published date, the affected packages (ecosystem and name), the summary and the details, as plain text:
  no code blocks, URLs, tables or headings; the sections that grade or credit (severity, CVSS, score, credits,
  acknowledgements, references, timeline, proof of concept) removed; emails, @handles and phone numbers masked; sentences
  crediting people removed; every sentence with a SCRUB word, a CVSS vector or an "x.x/10" score removed; cut at a sentence
  boundary. A record whose summary contains a SCRUB word is dropped. Not used: severity / CVSS fields, CWE ids, aliases
  (CVE ids), references, credits, modified / reviewed dates.
* Group key: the GHSA id.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import random
import re
import sys
import tarfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ghsa_severity"
TASK = "ghsa_severity"
AREA = "language"           # severity tasks: area "language"
EVAL_FRAC = 0.05            # more than ~3,300 records: about 5 % test and 5 % select
SUMMARY_LIMIT = 300
TEXT_LIMIT = 1000
MIN_DETAIL_WORDS = 8
MAX_PACKAGES = 4
LABELS = {"LOW": "Low severity", "MODERATE": "Moderate severity", "HIGH": "High severity", "CRITICAL": "Critical severity"}
SCRUB = ("critical", "critically", "criticality", "high", "moderate", "moderately", "medium", "low", "severe", "severely",
         "severity", "severities", "serious", "seriously", "cvss", "cvssv3", "cvssv4", "cvss3", "cvss4", "base score",
         "score", "scores", "scored", "scoring", "rating", "ratings", "rated", "classified as", "declared as",
         "problematic", "important", "p0", "p1", "p2", "p3", "p4", "sev", "sev1", "sev2", "sev3")
SCRUB_RE = R.scrub_pattern(SCRUB)
CVSS_VECTOR_RE = re.compile(r"\b(?:CVSS:\d\.\d/)?(?:AV|AC|AT|PR|UI|S|C|I|A|VC|VI|VA|SC|SI|SA):[A-Z]"
                            r"(?:/[A-Z]{1,3}:[A-Z]{1,2})+", re.I)
SCORE_RE = re.compile(r"\b(?:10(?:\.0)?|\d\.\d)\s*/\s*10\b")
DROP_SECTIONS = re.compile(r"severity|cvss|score|rating|risk|credit|acknowledg|thanks|attribution|reference|for more "
                           r"information|resources|timeline|disclosure|proof of concept|\bpoc\b|reproduc|exploit|"
                           r"fix commit|contact|reporter|researcher|discover", re.I)
CREDIT_RE = re.compile(r"\b(thanks?|thank you|thanking|kudos|credits?|credited|acknowledg\w*|co-?authored|written by|"
                       r"authored by|reported by|discovered by|found by|identified by|courtesy of|researcher|in "
                       r"collaboration with|with (the )?help (of|from)|helped)\b", re.I)
QUESTIONS = ("How severe is the vulnerability described in this advisory?",
             "Which severity level does this security advisory have?",
             "What severity was assigned to this advisory?",
             "Which of these is the severity of the vulnerability in this advisory?",
             "How was this advisory's vulnerability graded?")


# ------------------------------------------------------------------------------------------------------------ CVSS v3

_W = {"AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}, "AC": {"L": 0.77, "H": 0.44}, "UI": {"N": 0.85, "R": 0.62},
      "CIA": {"H": 0.56, "L": 0.22, "N": 0.0}}


def _roundup(x: float) -> float:
    """CVSS v3.1 Roundup: the smallest number with one decimal that is >= x (with the specification's float guard)."""
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_score(vector: str) -> float | None:
    """Base score of a CVSS v3.0 / v3.1 vector (specification section 7.1), None if the vector is malformed."""
    try:
        m = dict(p.split(":", 1) for p in vector.strip().split("/")[1:])
        scope = m["S"]
        pr = {"N": 0.85, "L": 0.68 if scope == "C" else 0.62, "H": 0.5 if scope == "C" else 0.27}[m["PR"]]
        iss = 1 - (1 - _W["CIA"][m["C"]]) * (1 - _W["CIA"][m["I"]]) * (1 - _W["CIA"][m["A"]])
        impact = 6.42 * iss if scope == "U" else 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
        expl = 8.22 * _W["AV"][m["AV"]] * _W["AC"][m["AC"]] * pr * _W["UI"][m["UI"]]
    except (KeyError, ValueError):
        return None
    if scope not in ("U", "C") or not vector.startswith("CVSS:3"):
        return None
    if impact <= 0:
        return 0.0
    return _roundup(min(impact + expl, 10)) if scope == "U" else _roundup(min(1.08 * (impact + expl), 10))


def cvss_band(score: float) -> str:
    return "NONE" if score == 0 else "LOW" if score < 4 else "MODERATE" if score < 7 else "HIGH" if score < 9 else "CRITICAL"


# ------------------------------------------------------------------------------------------------------------ text

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w+])(\+\d{1,3}[\s.-]?\(?\d{1,4}\)?([\s.-]?\d{2,4}){2,4}|\(\d{3}\)\s?\d{3}[\s.-]\d{4})(?!\w)")
HANDLE_RE = re.compile(r"(?<![\w@./-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(/[A-Za-z0-9_.-]+)?(?![\w@])")


def mask_private(text: str) -> str:
    """Emails and phone numbers masked everywhere; @handles of people masked outside inline code (`@decorator` stays);
    team mentions (@org/team) keep the team name without the @."""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    def handles(p: str) -> str:
        return HANDLE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}" if m.group(2) else "[user]", p)
    return "".join(p if p.startswith("`") else handles(p) for p in re.split(r"(`[^`\n]+`)", text))


def _inline(u: str) -> str:
    u = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", u)
    u = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", u)
    u = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", u)
    u = re.sub(r"<[^>\n]+>", " ", u)
    u = re.sub(r"\b(https?://|www\.)\S+", " ", u)
    u = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", u)
    u = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", u)
    u = re.sub(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])", r"\1", u)
    return R.norm_ws(u)


def plain(md: str) -> str:
    """Advisory markdown as plain text: no comments, code blocks, tables, link definitions or headings, and none of the
    sections whose heading matches DROP_SECTIONS; list items and paragraphs end in sentence punctuation."""
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    md = re.sub(r"<!--.*?(-->|\Z)", "\n", md, flags=re.S)
    md = re.sub(r"(?ms)^\s*(```|~~~).*?(^\s*\1[^\n]*$|\Z)", "\n\n", md)
    md = re.sub(r"(?is)<(details|pre|code|table)\b.*?</\1>", "\n\n", md)
    units: list[str] = []
    skip_level = 0
    for block in re.split(r"\n\s*\n", md):
        cur: list[str] = []
        for line in block.split("\n"):
            raw = line.rstrip()
            s = raw.strip()
            if not s:
                continue
            head = re.match(r"^(#{1,6})\s*(.*?)\s*#*\s*$", s)
            bold_head = re.match(r"^(\*\*|__)([^*_]{2,60})\1:?$", s)
            if head or bold_head:
                if cur:
                    units.append(" ".join(cur))
                    cur = []
                level = len(head.group(1)) if head else 7
                title = head.group(2) if head else bold_head.group(2)
                if skip_level and level <= skip_level:
                    skip_level = 0
                if not skip_level and DROP_SECTIONS.search(title):
                    skip_level = level
                continue
            if skip_level:
                continue
            if s.startswith("|") or re.match(r"^([-*_=]\s*){3,}$", s) or re.match(r"^\[[^\]]+\]:\s*\S+", s) \
                    or re.match(r"^(\s{4,}|\t)", raw) and not cur:
                continue
            s = re.sub(r"^>+\s?", "", s)
            item = re.match(r"^(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?(.*)$", s)
            if item:
                if cur:
                    units.append(" ".join(cur))
                cur, s = [], item.group(1)
            cur.append(s)
        if cur and not skip_level:
            units.append(" ".join(cur))
    out = []
    for u in units:
        u = _inline(u)
        if not re.search(r"[A-Za-z]{2,}", u):
            continue
        if u.endswith((",", ";")):
            u = u[:-1].rstrip() + "."
        elif not re.search(r"[.!?:]$", u):
            u += "."
        out.append(u)
    return " ".join(out)


def scrubbed(text: str) -> str:
    text = mask_private(text)
    for pat in (CREDIT_RE, CVSS_VECTOR_RE, SCORE_RE, SCRUB_RE):
        text = R.drop_sentences(text, pat)
    return text


def clean_summary(summary: str) -> str:
    return mask_private(_inline(summary or ""))


# ------------------------------------------------------------------------------------------------------------ records

def advisories(raw: str) -> list[dict]:
    """Every advisories/github-reviewed/**/GHSA-*.json of the raw tarball, parsed as JSON data (one streaming pass)."""
    tp = sorted(glob.glob(os.path.join(raw, "advisory-database-*.tar.gz")))[0]
    out = []
    with tarfile.open(tp, "r|gz") as tf:
        for m in tf:
            if m.isfile() and re.search(r"^[^/]+/advisories/github-reviewed/.+/GHSA-[\w-]+\.json$", m.name):
                out.append(json.loads(tf.extractfile(m).read().decode("utf-8")))
    return sorted(out, key=lambda a: a.get("id", ""))


def packages(adv: dict) -> list[str]:
    seen = []
    for aff in adv.get("affected") or []:
        pkg = aff.get("package") or {}
        p = f"{pkg.get('ecosystem', '').strip()} {pkg.get('name', '').strip()}".strip()
        if p and p not in seen:
            seen.append(p)
    return seen


def records(raw: str) -> tuple[list[dict], dict]:
    advs = advisories(raw)
    stats = {"reviewed_advisories": len(advs), "withdrawn": 0, "no_label": 0, "no_cvss3": 0, "cvss3_disagrees": 0,
             "duplicate_text": 0, "duplicate_text_conflicting": 0, "same_package_summary": 0,
             "same_package_summary_conflicting": 0, "same_record_text": 0, "same_record_text_conflicting": 0}
    cand = []
    for a in advs:
        ds = a.get("database_specific") or {}
        sev = str(ds.get("severity") or "").upper()
        if a.get("withdrawn"):
            stats["withdrawn"] += 1
            continue
        if sev not in LABELS or ds.get("github_reviewed") is not True:
            stats["no_label"] += 1
            continue
        v3 = [s.get("score", "") for s in a.get("severity") or [] if s.get("type") == "CVSS_V3"]
        score = cvss3_score(v3[0]) if len(v3) == 1 else None
        if score is None:
            stats["no_cvss3"] += 1
            continue
        if cvss_band(score) != sev:
            stats["cvss3_disagrees"] += 1
            continue
        cand.append({"id": a["id"], "adv": a, "label": sev, "key": a["id"]})
    def collapse(recs: list[dict], key, name: str) -> list[dict]:
        """One record per group of near-copies (the lowest id); every record of a group whose severities differ dropped."""
        groups: dict[str, list[dict]] = {}
        for rec in recs:
            groups.setdefault(key(rec["adv"]), []).append(rec)
        out = []
        for k in sorted(groups):
            g = groups[k]
            if len(g) > 1 and len({r["label"] for r in g}) > 1:
                stats[f"{name}_conflicting"] += len(g)
                continue
            stats[name] += len(g) - 1
            out.append(min(g, key=lambda r: r["id"]))
        return out
    def same_text(a: dict) -> str:
        return R.norm_ws(f"{a.get('summary') or ''} | {a.get('details') or ''}").lower()

    def same_package_summary(a: dict) -> str:
        return f"{sorted(packages(a))} | {R.norm_ws(a.get('summary') or '').lower()}"
    out = collapse(cand, same_text, "duplicate_text")
    out = collapse(out, same_package_summary, "same_package_summary")
    return sorted(out, key=lambda r: r["id"]), stats


def published(adv: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat((adv.get("published") or "")[:10])
    except ValueError:
        return None


def render(rec: dict, rng: random.Random) -> str | None:
    a = rec["adv"]
    summary = clean_summary(a.get("summary"))
    if not summary or R.scrub_hits(summary, SCRUB_RE) or CVSS_VECTOR_RE.search(summary) or SCORE_RE.search(summary):
        return None
    summary = R.clip(summary, SUMMARY_LIMIT) or summary[:SUMMARY_LIMIT].rsplit(" ", 1)[0]
    details = R.clip(scrubbed(plain(a.get("details") or "")), TEXT_LIMIT)
    if len(re.findall(r"[A-Za-z]{2,}", details)) < MIN_DETAIL_WORDS:
        return None
    pk = packages(a)
    if not pk:
        return None
    pk_text = "; ".join(pk[:MAX_PACKAGES]) + (f"; and {len(pk) - MAX_PACKAGES} more" if len(pk) > MAX_PACKAGES else "")
    d = published(a)
    record = "\n".join([f"Package security advisory (published {d.isoformat() if d else 'unknown'})",
                        f"Packages: {mask_private(pk_text)}", f"Summary: {summary}", f"Details: {details}"])
    if R.scrub_hits(record, SCRUB_RE) or CVSS_VECTOR_RE.search(record):      # the record text only: the question is ours
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, stats = records(raw)
    n_read = stats["reviewed_advisories"]
    rendered, unrendered = [], 0
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text = render(rec, rng)
        if text is None:
            unrendered += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        rendered.append(rec)
    by_text: dict[str, list[dict]] = {}
    for rec in rendered:                    # records that differ only in scrubbed sentences: identical once rendered
        by_text.setdefault(R.norm_ws(rec["text"].rsplit("\n\n", 1)[0]).lower(), []).append(rec)
    kept = []
    for g in by_text.values():
        if len(g) > 1 and len({r["label"] for r in g}) > 1:
            stats["same_record_text_conflicting"] += len(g)
            continue
        stats["same_record_text"] += len(g) - 1
        kept.append(min(g, key=lambda r: r["id"]))
    kept.sort(key=lambda r: r["id"])
    capped, class_report = R.cap_classes(kept, lambda r: r["label"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["label"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["label"]], source="ghsa",
                             source_id=rec["id"], snapshot=snapshot, record_date=published(rec["adv"]),
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    from collections import Counter
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "database_specific.severity, kept where the CVSS v3 base rating agrees",
                "labels": LABELS, "records_read": n_read, "selection": stats,
                "kept_before_caps": dict(sorted(Counter(r["label"] for r in kept).items())),
                "dropped_unrenderable_or_scrub": unrendered, **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def _commit(snapshot: str) -> str:
    return json.load(open(os.path.join(R.RAW, DOMAIN, snapshot, "advisory-database.head.json")))["sha"]


_FILES: dict[str, dict[str, tuple[str, bytes]]] = {}


def _reviewed(snapshot: str) -> dict[str, tuple[str, bytes]]:
    """GHSA id -> (path in the repository, raw bytes) of every reviewed advisory file, read once per process."""
    if snapshot not in _FILES:
        tp = glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "advisory-database-*.tar.gz"))[0]
        files = {}
        with tarfile.open(tp, "r|gz") as tf:
            for m in tf:
                if m.isfile() and "/advisories/github-reviewed/" in m.name and m.name.endswith(".json"):
                    files[os.path.basename(m.name)[:-5]] = (m.name.split("/", 1)[1], tf.extractfile(m).read())
        _FILES[snapshot] = files
    return _FILES[snapshot]


def source_url(row: dict, snapshot: str) -> str:
    path = _reviewed(snapshot).get(row["source_id"], ("advisories/github-reviewed", b""))[0]
    return f"https://github.com/github/advisory-database/blob/{_commit(snapshot)}/{path}"


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The severity read again from the raw file by a plain text search of its database_specific block (not the JSON
    parser), None for a withdrawn advisory; and whether the item's summary line is the advisory's own summary."""
    hit = _reviewed(snapshot).get(row["source_id"])
    if hit is None:
        return None, False
    text = hit[1].decode("utf-8", "replace")
    m = re.search(r'"database_specific"\s*:\s*\{[^{}]*?"severity"\s*:\s*"([A-Z]+)"', text, re.S)
    sev = None if re.search(r'"withdrawn"\s*:\s*"', text) or not m else m.group(1)
    s = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    summary = json.loads(f'"{s.group(1)}"') if s else ""
    line = next((ln for ln in row["questions"][0]["instructions"].split("\n") if ln.startswith("Summary: ")), "")
    own = clean_summary(summary)
    text_ok = bool(own) and (line == f"Summary: {own}" or line.startswith("Summary: ") and own.startswith(line[9:]))
    return LABELS.get(sev or ""), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        sp = m["splits"][s]
        print(f"{s}: {sp['rows']} rows, classes {sp['class_prior']}, gold position {sp['gold_position']}, "
              f"fresh {sp['fresh']}")
    print(f"records read {m['records_read']}, selection {m['selection']}, kept before caps {m['kept_before_caps']}, "
          f"dropped (scrub / no text) {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
