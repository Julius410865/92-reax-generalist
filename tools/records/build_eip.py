"""#1 Ethereum improvement proposals -> status: eval-v5.1 mirror rows (part N, task type ``eip_status``).

    python -I tools/records/build_eip.py --snapshot 2026-10-27

Records: the proposal files of ethereum/EIPs and ethereum/ERCs (front matter + body), read from the raw tarballs as data.
* Label: the ``status:`` front-matter field only. Kept: Final, Stagnant, Withdrawn (Stagnant is the "inactive, never
  finished" outcome, like the PEP domain's Deferred). Dropped: Draft, Review, Last Call (in progress), Moved (stubs of
  proposals that moved to the ERCs repository, which are read there), and classes under 20 records (Living).
* Record text: type, category and created date, title, description, and the abstract (else the simple summary, else the
  first paragraph), cut at a sentence boundary. Not used: status, last-call-deadline, withdrawal-reason, updated, authors.
  Every sentence that contains a word of ``SCRUB`` is removed; a record whose title or description contains one is dropped.
* Group key: the proposal number (a number appears once after the Moved stubs are dropped).
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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "eip"
TASK = "eip_status"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.10            # a small domain: about 10 % test and 10 % select
TEXT_LIMIT = 900
LABELS = {"Final": "Final (accepted and part of the standard)",
          "Stagnant": "Stagnant (inactive for six months or more, never finished)",
          "Withdrawn": "Withdrawn by its authors"}
DROP_STATUS = {"Draft", "Review", "Last Call", "Moved"}
SCRUB = ("final", "finalized", "finalised", "finalize", "finalise", "finalization", "withdrawn", "stagnant", "living",
         "superseded", "supersedes", "supersede", "deprecated", "obsolete", "obsoleted", "moved", "last call", "draft",
         "drafts", "in review", "under review", "accepted", "rejected", "abandoned", "inactive", "status", "deadline",
         "replaced by", "is replaced", "was replaced")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("What is the status of this proposal today?",
             "Which status does this proposal have now?",
             "What became of this proposal?",
             "Where does this proposal stand today?",
             "Which of these is the proposal's current status?")


def parse(txt: str) -> tuple[dict, str] | None:
    fm = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not fm:
        return None
    meta = {k: v.strip().strip('"') for k, v in re.findall(r"^([a-z-]+):\s*(.*)$", fm.group(1), re.M)}
    return meta, txt[fm.end():]


def section(body: str, *names: str) -> str:
    for name in names:
        m = re.search(r"^#{2,3}\s*" + re.escape(name) + r"\s*$(.*?)(?=^#{1,3}\s|\Z)", body, re.M | re.S | re.I)
        if m and m.group(1).strip():
            return m.group(1)
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip() and not p.lstrip().startswith(("#", "```", "|", "<"))]
    return paras[0] if paras else ""


def plain(md: str) -> str:
    """Markdown to plain text: links to their text, no code blocks, inline code / emphasis markers removed."""
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"<[^>]+>", " ", md)
    md = re.sub(r"[`*_]{1,3}", "", md)
    return R.norm_ws(md)


def records(raw: str) -> list[dict]:
    out = {}
    for tp in sorted(glob.glob(os.path.join(raw, "*.tar.gz"))):
        repo = os.path.basename(tp).split("-")[0]
        with tarfile.open(tp, "r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile() or not re.search(r"/(EIPS|ERCS)/(eip|erc)-\d+\.md$", m.name):
                    continue
                parsed = parse(tf.extractfile(m).read().decode("utf-8", "replace"))
                if not parsed:
                    continue
                meta, body = parsed
                status = meta.get("status", "")
                if status in DROP_STATUS or status not in LABELS and status != "Living":
                    continue
                num = meta.get("eip") or meta.get("erc")
                if not num or not num.isdigit():
                    continue
                if num in out:      # never expected once Moved stubs are gone; keep the ERCs copy deterministically
                    if repo != "ERCs":
                        continue
                out[num] = {"num": num, "repo": repo, "meta": meta, "body": body, "status": status, "key": f"eip-{num}"}
    return list(out.values())


def render(rec: dict, rng: random.Random) -> str | None:
    meta = rec["meta"]
    title, desc = plain(meta.get("title", "")), plain(meta.get("description", ""))
    if not title or R.scrub_hits(title, SCRUB_RE) or R.scrub_hits(desc, SCRUB_RE):
        return None
    abstract = R.drop_sentences(plain(section(rec["body"], "Abstract", "Simple Summary", "Summary", "Motivation")), SCRUB_RE)
    abstract = R.clip(abstract, TEXT_LIMIT)
    kind = meta.get("type") or "Standards Track"
    cat = meta.get("category")
    head = f"Ethereum improvement proposal ({kind}{', ' + cat if cat else ''}, created {meta.get('created', 'unknown')})"
    lines = [head, f"Title: {title}"]
    if desc:
        lines.append(f"Description: {desc}")
    if abstract:
        lines.append(f"Abstract: {abstract}")
    if meta.get("requires"):
        lines.append(f"Requires: {', '.join('EIP-' + x.strip() for x in meta['requires'].split(',') if x.strip())}")
    record = "\n".join(lines)
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours and names "status"
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def created(meta: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(meta.get("created", "")[:10])
    except ValueError:
        return None


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs = records(raw)
    n_read = len(recs)
    kept, unrendered = [], 0
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text = render(rec, rng)
        if text is None:
            unrendered += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    capped, class_report = R.cap_classes(kept, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        labels = [LABELS[s] for s in LABELS if s in {r["status"] for r in capped}]
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["status"]], source="eip",
                             source_id=f"{'ERC' if rec['repo'] == 'ERCs' else 'EIP'}-{rec['num']}", snapshot=snapshot,
                             record_date=created(rec["meta"]), shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "front matter 'status'", "labels": LABELS, "records_read": n_read,
                "dropped_unrenderable_or_scrub": unrendered, **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def _commit(snapshot: str, repo: str) -> str:
    return json.load(open(os.path.join(R.RAW, DOMAIN, snapshot, f"{repo}.head.json")))["sha"]


def source_url(row: dict, snapshot: str) -> str:
    kind, num = row["source_id"].split("-")
    repo, folder = ("ERCs", "ERCS") if kind == "ERC" else ("EIPs", "EIPS")
    return f"https://github.com/ethereum/{repo}/blob/{_commit(snapshot, repo)}/{folder}/{kind.lower()}-{num}.md"


_FILES: dict[tuple[str, str], dict[str, bytes]] = {}


def _proposal_files(snapshot: str, repo: str) -> dict[str, bytes]:
    """file name -> bytes of a raw tarball's proposal files, read once per process."""
    if (snapshot, repo) not in _FILES:
        tp = glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, f"{repo}-*.tar.gz"))[0]
        with tarfile.open(tp, "r:gz") as tf:
            _FILES[(snapshot, repo)] = {os.path.basename(m.name): tf.extractfile(m).read() for m in tf.getmembers()
                                        if m.isfile() and re.search(r"/(EIPS|ERCS)/(eip|erc)-\d+\.md$", m.name)}
    return _FILES[(snapshot, repo)]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The status read again from the raw tarball (a plain line scan, not the builder's parser), and whether the item's
    title line is the record's own title."""
    kind, num = row["source_id"].split("-")
    repo = "ERCs" if kind == "ERC" else "EIPs"
    raw = _proposal_files(snapshot, repo).get(f"{kind.lower()}-{num}.md")
    if raw is None:
        return None, False
    lines = raw.decode("utf-8", "replace").splitlines()
    status = next((ln.split(":", 1)[1].strip() for ln in lines[1:40] if ln.lower().startswith("status:")), None)
    title = next((ln.split(":", 1)[1].strip().strip('"') for ln in lines[1:40] if ln.lower().startswith("title:")), "")
    text_ok = f"Title: {plain(title)}" in row["questions"][0]["instructions"]
    return LABELS.get(status), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows, classes {m['splits'][s]['class_prior']}, gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']}, dropped (scrub / no text) {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
