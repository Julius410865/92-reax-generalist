"""#3 Kubernetes enhancement proposals (KEPs) -> final status: eval-v5.1 mirror rows (part N, task type ``kep_status``).

    python -I tools/records/build_kep.py --snapshot 2026-10-27

Records: the KEP directories of kubernetes/enhancements (keps/<sig>/<NNNN-name>/kep.yaml + README.md), read from the raw
tarball as data (kep.yaml with YAML's BaseLoader: strings, lists and maps only).
* Label: the kep.yaml ``status`` field only, final states only, values of the KEP process documented in the template:
  ``implemented`` -> Implemented; ``withdrawn`` / ``rejected`` / ``replaced`` / ``deferred`` -> did not go ahead as proposed
  (``FINAL``). These four are one class because none of them has MIN_CLASS records on its own (withdrawn 11, replaced 6,
  rejected 3, deferred 1 in the 2026-10-27 snapshot). Dropped: provisional and implementable (in progress), undocumented
  values (superseded, removed, misspelt or annotated values, template placeholders), KEP numbers with two kep.yaml files
  of different status (conflicting), and the template directory.
* Record text: owning SIG and creation date, the kep.yaml title and the README's Summary section (else its Motivation
  section), plain text, cut at a sentence boundary. Not used: status, stage, latest-milestone, milestone, last-updated,
  superseded-by / replaces, feature gates, authors, the KEP number. Note boxes (NOTE / IMPORTANT / UPDATE paragraphs,
  NOTE ... END NOTE spans) and every paragraph (with the list it introduces) that contains a word of SCRUB are removed,
  as post-hoc notes tell the outcome; a record whose title contains a SCRUB word is dropped. @handles, emails and phone
  numbers are masked; sentences crediting people are removed.
* Group key: the KEP number.
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

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "kep"
TASK = "kep_status"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.10            # fewer than ~3,300 records: about 10 % test and 10 % select
TEXT_LIMIT = 900
MIN_SUMMARY_WORDS = 8
FINAL = {"implemented": "implemented", "withdrawn": "ended", "rejected": "ended", "replaced": "ended", "deferred": "ended"}
LABELS = {"implemented": "Implemented: the enhancement was completed",
          "ended": "Did not go ahead as proposed: withdrawn, rejected, replaced by another KEP, or deferred"}
IN_PROGRESS = {"provisional", "implementable"}
SCRUB = ("implemented", "implementable", "provisional", "withdrawn", "withdraw", "withdrew", "withdrawing", "rejected",
         "reject", "rejection", "replaced", "replaced by", "superseded", "supersedes", "supersede", "deferred", "defer",
         "deferral", "postponed", "postpone", "abandoned", "graduated", "graduate", "graduates", "graduating", "graduation",
         "ga", "generally available", "general availability", "stable", "beta", "alpha", "milestone", "milestones",
         "promoted", "promote", "promotion", "kep status", "status of this kep", "completed", "no longer", "removed",
         "obsolete", "declined", "on hold", "decided", "decision", "objections", "pursue", "pursued", "originally")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("What is the final status of this Kubernetes enhancement proposal?",
             "How did this Kubernetes enhancement proposal end?",
             "What became of this enhancement proposal?",
             "Which of these describes the outcome of this KEP?",
             "Where did this Kubernetes enhancement proposal end up?")


# ------------------------------------------------------------------------------------------------------------ text

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w+])(\+\d{1,3}[\s.-]?\(?\d{1,4}\)?([\s.-]?\d{2,4}){2,4}|\(\d{3}\)\s?\d{3}[\s.-]\d{4})(?!\w)")
CREDIT_RE = re.compile(r"\b(thanks?|thank you|thanking|kudos|credits?|co-?authored|written by|authored by|in collaboration "
                       r"with|with (the )?help (of|from)|helped)\b", re.I)     # no 'acknowledg-': TLS / TCP acknowledgements
HANDLE_RE = re.compile(r"(?<![\w@./-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(/[A-Za-z0-9_.-]+)?(?![\w@])")


def mask_private(text: str) -> str:
    """Emails and phone numbers masked everywhere; @handles of people masked outside inline code (`@decorator` stays);
    team mentions (@org/team) keep the team name without the @."""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    def handles(p: str) -> str:
        return HANDLE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}" if m.group(2) else "[user]", p)
    return "".join(p if p.startswith("`") else handles(p) for p in re.split(r"(`[^`\n]+`)", text))


NOTE_START = re.compile(r"^(NOTE|IMPORTANT|UPDATE|UPDATED|STATUS|EDIT|WARNING|CAUTION|DEPRECATED|Note|Important|Update|"
                        r"Updated|Status|Edit|Warning|Caution)\b\s*[:!.]?|^\[!\w+\]")
NOTE_END = re.compile(r"^END\s+NOTE\b", re.I)


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


def blocks(md: str) -> list[str]:
    """Markdown as plain-text blocks (a paragraph with the list it introduces): no comments, code blocks, images, tables or
    headings; links to their text; list items and lines ending a unit get sentence punctuation; emphasis markers removed
    (identifiers keep their underscores). Note boxes (NOTE / IMPORTANT / UPDATE ... paragraphs, NOTE ... END NOTE spans)
    are dropped: they are added after the fact and tell what became of the proposal."""
    md = (md or "").replace("\r\n", "\n")
    md = re.sub(r"<!--.*?(-->|\Z)", "\n", md, flags=re.S)
    md = re.sub(r"(?ms)^\s*(```|~~~).*?(^\s*\1[^\n]*$|\Z)", "\n\n", md)
    out, in_note = [], False
    for block in re.split(r"\n\s*\n", md):
        units: list[str] = []
        cur: list[str] = []
        for line in block.split("\n"):
            s = line.strip()
            if not s or s.startswith(("#", "|")) or re.match(r"^([-*_=]\s*){3,}$", s) or re.match(r"^\[[^\]]+\]:\s*\S+", s):
                continue
            s = re.sub(r"^>+\s?", "", s)
            item = re.match(r"^(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?(.*)$", s)
            if item:
                if cur:
                    units.append(" ".join(cur))
                cur, s = [], item.group(1)
            cur.append(s)
        if cur:
            units.append(" ".join(cur))
        units = [u for u in (_inline(u) for u in units) if u]
        if not units:
            continue
        head = units[0]
        if NOTE_END.match(head):
            in_note = False
            continue
        if in_note:
            continue
        if NOTE_START.match(head):
            in_note = not re.search(r"[A-Za-z]{2,}.*[A-Za-z]{2,}", NOTE_START.sub("", head, count=1))   # a lone NOTE marker
            continue
        text = []
        for u in units:
            if u.endswith((",", ";")):
                u = u[:-1].rstrip() + "."
            elif not re.search(r"[.!?:]$", u):
                u += "."
            text.append(u)
        out.append(" ".join(text))
    return out


def section(md: str, name: str) -> str:
    m = re.search(r"^#{2,3}\s*" + re.escape(name) + r"\s*$(.*?)(?=^#{1,3}\s|\Z)", md, re.M | re.S | re.I)
    return m.group(1) if m else ""


def summary_text(readme: str) -> str:
    """The Summary section (else the Motivation section) without the blocks that contain a SCRUB word, masked and cut."""
    for name in ("Summary", "Motivation"):
        kept = [b for b in blocks(section(readme, name)) if not R.scrub_hits(b, SCRUB_RE)]
        text = R.drop_sentences(R.drop_sentences(mask_private(" ".join(kept)), CREDIT_RE), SCRUB_RE)
        if len(re.findall(r"[A-Za-z]{2,}", text)) >= MIN_SUMMARY_WORDS:
            return R.clip(text, TEXT_LIMIT)
    return ""


# ------------------------------------------------------------------------------------------------------------ records

KEP_DIR = re.compile(r"^[^/]+/keps/(sig-[^/]+|provider-[^/]+)/(?:[^/]+/)?(\d+)-[^/]+/(kep\.yaml|README\.md)$")


def kep_files(raw: str) -> dict[str, dict[str, str]]:
    """KEP directory -> {'kep.yaml': text, 'README.md': text} from the raw tarball."""
    tp = sorted(glob.glob(os.path.join(raw, "enhancements-*.tar.gz")))[0]
    out: dict[str, dict[str, str]] = {}
    with tarfile.open(tp, "r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile() and KEP_DIR.match(m.name):
                d, f = m.name.rsplit("/", 1)
                out.setdefault(d.split("/", 1)[1], {})[f] = tf.extractfile(m).read().decode("utf-8", "replace")
    return out


def records(raw: str) -> tuple[list[dict], dict]:
    stats = {"kep_dirs": 0, "no_kep_yaml": 0, "in_progress": 0, "undocumented_status": {}, "conflicting_number": 0}
    by_num: dict[str, list[dict]] = {}
    files = kep_files(raw)
    for d in sorted(files):
        stats["kep_dirs"] += 1
        f = files[d]
        if "kep.yaml" not in f:
            stats["no_kep_yaml"] += 1
            continue
        try:
            meta = yaml.load(f["kep.yaml"], Loader=yaml.BaseLoader)
        except yaml.YAMLError:
            meta = None
        if not isinstance(meta, dict):
            stats["no_kep_yaml"] += 1
            continue
        status = str(meta.get("status", "")).strip()
        num = str(meta.get("kep-number", "")).strip()
        if status in IN_PROGRESS:
            stats["in_progress"] += 1
            continue
        if status not in FINAL or not num.isdigit() or num != d.split("/")[-1].split("-")[0]:
            bad = stats["undocumented_status"]
            bad[status or "(missing)"] = bad.get(status or "(missing)", 0) + 1
            continue
        by_num.setdefault(num, []).append({"num": num, "dir": d, "meta": meta, "readme": f.get("README.md", ""),
                                           "status": status, "label": FINAL[status], "key": f"kep-{num}"})
    out = []
    for num in sorted(by_num, key=int):
        recs = by_num[num]
        if len({r["status"] for r in recs}) > 1:
            stats["conflicting_number"] += len(recs)
            continue
        out.append(sorted(recs, key=lambda r: r["dir"])[0])
    return out, stats


def created(meta: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(meta.get("creation-date", ""))[:10])
    except ValueError:
        return None


def clean_title(title: str) -> str:
    return mask_private(R.norm_ws(re.sub(r"[`*]", "", title or "")))


def render(rec: dict, rng: random.Random) -> str | None:
    meta = rec["meta"]
    title = clean_title(str(meta.get("title", "")))
    if not title or R.scrub_hits(title, SCRUB_RE):
        return None
    summary = summary_text(rec["readme"])
    if not summary:
        return None
    sig = str(meta.get("owning-sig", "")).strip() or rec["dir"].split("/")[1]
    d = created(meta)
    record = "\n".join([f"Kubernetes enhancement proposal (owning SIG: {sig}, created {d.isoformat() if d else 'unknown'})",
                        f"Title: {title}", f"Summary: {summary}"])
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, stats = records(raw)
    n_read = stats["kep_dirs"]
    kept, unrendered = [], 0
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text = render(rec, rng)
        if text is None:
            unrendered += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    capped, class_report = R.cap_classes(kept, lambda r: r["label"], DOMAIN)
    present = {r["label"] for r in capped}
    if len(present) < 2:
        raise SystemExit(f"kep: only {sorted(present)} has >= {R.MIN_CLASS} records "
                         f"({class_report['classes_dropped_under_min']} dropped); no multiple-choice domain")
    final = R.take(capped, DOMAIN)
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["label"]], source="kep",
                             source_id=f"KEP-{rec['num']}", snapshot=snapshot, record_date=created(rec["meta"]),
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    from collections import Counter
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "kep.yaml 'status'", "label_map": FINAL, "labels": LABELS, "records_read": n_read,
                "selection": stats, "final_status_kept": dict(sorted(Counter(r["status"] for r in kept).items())),
                "dropped_unrenderable_or_scrub": unrendered, **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def _commit(snapshot: str) -> str:
    return json.load(open(os.path.join(R.RAW, DOMAIN, snapshot, "enhancements.head.json")))["sha"]


_FILES: dict[str, dict[str, bytes]] = {}


def _kep_yamls(snapshot: str) -> dict[str, bytes]:
    """path inside the repository -> bytes of every kep.yaml in the raw tarball, read once per process."""
    if snapshot not in _FILES:
        tp = glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "enhancements-*.tar.gz"))[0]
        with tarfile.open(tp, "r:gz") as tf:
            _FILES[snapshot] = {m.name.split("/", 1)[1]: tf.extractfile(m).read() for m in tf.getmembers()
                                if m.isfile() and m.name.endswith("/kep.yaml") and "/keps/" in m.name}
    return _FILES[snapshot]


def _path_of(row: dict, snapshot: str) -> str | None:
    num = row["source_id"].split("-", 1)[1]
    hits = sorted(p for p in _kep_yamls(snapshot) if re.search(rf"/{num}-[^/]+/kep\.yaml$", p))
    return hits[0] if hits else None


def source_url(row: dict, snapshot: str) -> str:
    p = _path_of(row, snapshot)
    folder = p.rsplit("/", 1)[0] if p else "keps"
    return f"https://github.com/kubernetes/enhancements/blob/{_commit(snapshot)}/{folder}/README.md"


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The status read again from the raw kep.yaml (a plain line scan for 'status:', not the YAML parser), mapped as the
    builder maps it, and whether the item's title line is the kep.yaml title."""
    p = _path_of(row, snapshot)
    if p is None:
        return None, False
    lines = _kep_yamls(snapshot)[p].decode("utf-8", "replace").splitlines()
    status = next((ln.split(":", 1)[1].split("#")[0].strip().strip("\"'") for ln in lines if ln.startswith("status:")), None)
    title = next((ln.split(":", 1)[1].strip().strip("\"'") for ln in lines if ln.startswith("title:")), "")
    text_ok = f"Title: {clean_title(title)}\n" in row["questions"][0]["instructions"]
    return LABELS.get(FINAL.get(status or "")), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        sp = m["splits"][s]
        print(f"{s}: {sp['rows']} rows, classes {sp['class_prior']}, gold position {sp['gold_position']}, "
              f"fresh {sp['fresh']}")
    print(f"records read {m['records_read']}, selection {m['selection']}, final status kept {m['final_status_kept']}, "
          f"dropped (scrub / no text) {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
