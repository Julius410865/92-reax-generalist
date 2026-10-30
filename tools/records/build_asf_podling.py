"""#4 Apache Software Foundation podlings -> incubation outcome: eval-v5.1 mirror rows (part N, task type
``asf_podling_outcome``).

    python -I tools/records/build_asf_podling.py --snapshot 2026-10-27

Records: the podlings that left the Apache Incubator, from projects.apache.org's podlings-history.json, read as data.
* Label: the ``status`` field of podlings-history.json, kept only where the Incubator's podlings.xml (its upstream, a
  second file: the ``status`` attribute of the podling element, parsed with xml.etree, no entities) says the same.
  Kept: graduated, retired. Dropped: podlings still incubating (podlings.json; "current" in podlings.xml: in progress) and
  any podling whose two statuses differ or that is missing from podlings.xml.
* Record text: the podling's name (as a podling, "Apache X (Incubating)"), the month it entered the Incubator and its
  description, cut at a sentence boundary. Not used: ended, homepage, the resolution element, sponsor, mentors, champion
  (mentor and champion names are private individuals) and the project files of top-level projects (only graduated
  podlings have one, so their text would differ by class). Every description sentence that contains a word of ``SCRUB``
  is removed; a record whose name contains one is dropped; e-mail addresses and phone numbers are masked.
* Group key: the podling id (``abdera``).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "asf_podling"
TASK = "asf_podling_outcome"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.10            # a small domain: about 10 % test and 10 % select
TEXT_LIMIT = 700
LABELS = {"graduated": "Graduated (accepted as an Apache project, or as part of one)",
          "retired": "Retired without graduating"}
SCRUB = ("graduated", "graduate", "graduates", "graduating", "graduation", "retired", "retire", "retires", "retiring",
         "retirement", "top-level project", "top level project", "top-level projects", "tlp", "tlps", "attic", "dormant",
         "inactive", "inactivity", "terminated", "termination", "discontinued", "abandoned", "defunct", "re-entered",
         "reentered", "reboot", "rebooted", "voted", "merged", "became part of", "become part of",
         "subproject of", "sub-project of", "moved to", "lack of community", "community interest", "failed", "failing",
         "traction", "no longer", "ceased", "pmc", "project management committee", "successor", "exited",
         "left the incubator", "status")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("What was the outcome of this podling's incubation?",
             "How did this podling's time in the Apache Incubator end?",
             "Which of these happened to this podling?",
             "What became of this podling?",
             "Which of these describes how this podling left the Incubator?")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
_PHONE = re.compile(r"(\(\d{3}\)\s*|\b\d{3}[-.\s])\d{3}[-.\s]\d{4}\b")
# common.clip / common.drop_sentences split sentences after every ". "; abbreviations ("e.g.", "Inc.", "John H.") would end
# a sentence there. The space after them is held as "\x00" (not whitespace) while those helpers run, then restored.
_ABBREV_SPACE = re.compile(r"\b((?:U\.S\.C|U\.S|U\.N|D\.C|e\.g|i\.e|N\.B|a\.m|p\.m|v|vs|Inc|Co|Corp|Ltd|Nos?|Docs?|Consol|Ct|Cir|Exp|Imp|"
                           r"Fed|Reg|Supp|Cong|Sess|Admin|Assn|Mfg|Bros|Dist|Div|Natl?|Intl?|Pts?|Ch|Cl|Paras?|Secs?|Subpt|"
                           r"approx|Est|Dr|Mrs?|Ms|St|Jr|Sr|Gen|Lt|Col|Sgt|Capt|Maj|Adm|Rep|Sen|Gov|Dept|Fig|Vol|Mt|Ft|Ave|"
                           r"Blvd|Pub|Stat|Art|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec|[A-Z])\.) ")
_RUN_ON = re.compile(r"([.!?]) (?=[a-z0-9&\u00a7])")       # "... No. 22-00152", "... v. & ...": no sentence starts there


def _hold(text: str) -> str:
    return _RUN_ON.sub("\\1\x00", _ABBREV_SPACE.sub(lambda m: m.group(1) + "\x00", R.norm_ws(text)))


def drop_sentences(text: str, pattern: re.Pattern) -> str:
    return R.drop_sentences(_hold(text), pattern).replace("\x00", " ")


def clip(text: str, limit: int) -> str:
    return R.clip(_hold(text), limit).replace("\x00", " ")


def mask_contacts(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[e-mail]", text))


# ------------------------------------------------------------------------------------------------------------ parse

def safe_xml(data: bytes) -> ET.Element | None:
    """The parsed document, or None if it declares entities (xml.etree never fetches external entities or DTDs)."""
    if b"<!ENTITY" in data:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def xml_status(raw: str) -> dict[str, str]:
    """podling id (``resource``) -> status attribute of podlings.xml."""
    root = safe_xml(open(os.path.join(raw, "podlings.xml"), "rb").read())
    if root is None:
        raise SystemExit("podlings.xml: not parseable or declares entities")
    out: dict[str, str] = {}
    for p in root.findall("podling"):
        rid = (p.get("resource") or "").strip()
        if rid:
            out[rid] = "conflict" if rid in out else (p.get("status") or "").strip()
    return out


def records(raw: str) -> tuple[list[dict], dict[str, int]]:
    """(records with an agreed final status, counts of the podlings left out)."""
    hist = json.load(open(os.path.join(raw, "podlings-history.json"), encoding="utf-8"))
    current = json.load(open(os.path.join(raw, "podlings.json"), encoding="utf-8"))
    xs = xml_status(raw)
    out, left = [], {"incubating": len(current), "status_missing_or_not_final": 0, "sources_disagree": 0,
                     "also_listed_as_incubating": 0}
    for pid in sorted(hist):
        v = hist[pid]
        status = (v.get("status") or "").strip() if isinstance(v, dict) else ""
        if status not in LABELS:
            left["status_missing_or_not_final"] += 1
        elif xs.get(pid) != status:
            left["sources_disagree"] += 1
        elif pid in current:
            left["also_listed_as_incubating"] += 1
        else:
            out.append({"key": pid, "status": status, "name": R.norm_ws(v.get("name", "")),
                        "description": R.norm_ws(v.get("description", "")), "started": (v.get("started") or "").strip()})
    return out, left


# ------------------------------------------------------------------------------------------------------------ render

def render(rec: dict, rng: random.Random) -> tuple[str | None, str]:
    """(item text, "") or (None, why the record cannot be used)."""
    name = rec["name"]
    if not name:
        return None, "no_name"
    if R.scrub_hits(name, SCRUB_RE):
        return None, "name_has_scrub_word"
    desc = clip(drop_sentences(mask_contacts(rec["description"]), SCRUB_RE), TEXT_LIMIT)
    if not desc:
        return None, "no_description_left_after_scrub"
    started = rec["started"] if re.fullmatch(r"\d{4}-\d{2}", rec["started"]) else "an unknown month"
    record = "\n".join([f"Apache Software Foundation Incubator podling (entered the Incubator in {started})",
                        f"Name: {name}", f"Description: {desc}"])
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours
        return None, "scrub_word_left"
    return record + "\n\n" + rng.choice(QUESTIONS), ""


def started(rec: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(rec["started"][:7] + "-01")
    except ValueError:
        return None


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, left = records(raw)
    n_read = len(recs) + sum(v for k, v in left.items() if k != "incubating")
    from collections import Counter
    drops: Counter = Counter()
    kept = []
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text, why = render(rec, rng)
        if text is None:
            drops[why] += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    seen: dict[str, dict] = {}
    for rec in sorted(kept, key=lambda r: r["key"]):        # a record text twice: keep one, or none if the labels differ
        k = R.norm_ws(rec["text"].rsplit("\n\n", 1)[0]).lower()
        if k in seen:
            drops["duplicate_text"] += 1
            if seen[k] is not None and seen[k]["status"] != rec["status"]:
                drops["duplicate_text"] += 1
                seen[k] = None
            continue
        seen[k] = rec
    unique = [r for r in seen.values() if r is not None]
    capped, class_report = R.cap_classes(unique, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)          # no class is capped and no split reaches its size cap here
    present = {r["status"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["status"]], source="asf_podling",
                             source_id=rec["key"], snapshot=snapshot, record_date=started(rec), shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "podlings-history.json 'status', agreeing with the podlings.xml status attribute",
                "labels": LABELS, "records_read": n_read, "not_used": left, "dropped": dict(sorted(drops.items())),
                "fresh_date": "the month the podling entered the Incubator", **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://incubator.apache.org/projects/{row['source_id']}.html"


_RAW: dict[str, tuple[str, str]] = {}


def _raw_texts(snapshot: str) -> tuple[str, str]:
    """(podlings-history.json text, podlings.xml text), read once per process."""
    if snapshot not in _RAW:
        d = os.path.join(R.RAW, DOMAIN, snapshot)
        _RAW[snapshot] = (open(os.path.join(d, "podlings-history.json"), encoding="utf-8").read(),
                          open(os.path.join(d, "podlings.xml"), encoding="utf-8").read())
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The status read again by plain text scans (not the builder's json / xml parsers): the podling's block in
    podlings-history.json and the start tag of its podling element in podlings.xml must both give it; and whether the
    item's name line is the podling's name."""
    hist, xml = _raw_texts(snapshot)
    pid = row["source_id"]
    block = re.search(r'\n"' + re.escape(pid) + r'":\s*\{([^{}]*)\}', hist)
    tag = next((t for t in re.findall(r"<podling\s[^>]*>", xml) if re.search(r'\sresource="' + re.escape(pid) + '"', t)), "")
    if not block or not tag:
        return None, False
    js = re.search(r'"status":\s*"([a-z]+)"', block.group(1))
    xs = re.search(r'\sstatus="([a-z]+)"', tag)
    label = js.group(1) if js and xs and js.group(1) == xs.group(1) else None
    nm = re.search(r'"name":\s*("(?:[^"\\]|\\.)*")', block.group(1))
    text_ok = bool(nm) and f"\nName: {R.norm_ws(json.loads(nm.group(1)))}\n" in row["questions"][0]["instructions"]
    return LABELS.get(label), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows, classes {m['splits'][s]['class_prior']}, gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']}, not used {m['not_used']}, dropped {m['dropped']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
