"""#5 US Congress bills -> furthest status: eval-v5.1 mirror rows (part N, task type ``congress_bill_status``).

    python -I tools/records/build_congress_bill.py --snapshot 2026-10-27

Records: the BILLSTATUS XML files of the 117th and 118th Congresses (completed, so every outcome is final), bill types
H.R. and S., read from the raw GovInfo bulk zips as data (xml.etree; a file that declares entities is skipped).
* Label: the furthest status, from structured fields only: the ``laws`` element and the Library of Congress action codes
  (actions whose sourceSystem is "Library of Congress": 5000 / 14000 reported by a House / Senate committee, 8000 / 17000
  passed or agreed to in the House / Senate, 31000 vetoed, 36000 / 41000 / E40000 became public / private law, 9000 / 18000
  failed of passage). Became law needs both the ``laws`` element and a became-law action (the two agree on every bill of the
  snapshot); a law without passage in both chambers is a conflict and dropped. Vetoed (1 bill) and "passed both chambers
  without becoming law" (7 bills) fall under the 20-record minimum. Dropped as well: bills whose only floor result is a
  failed passage vote (their furthest stage is neither "introduced only" nor "reported"), private relief bills ("For the
  relief of ...": they are about private individuals) and bills without a CRS summary of the introduced version.
* Record text: chamber, congress and date of introduction, the sponsor's party and state, the official title as introduced,
  the short title and the CRS summary of the introduced version (summary version code 00), cut at a sentence boundary. Not
  used: actions, latest action, later summaries and titles, laws, committees, cosponsors, related bills, member names.
  Every summary sentence that contains a word of ``SCRUB`` is removed; a record whose official or short title contains one
  is dropped; e-mail addresses and phone numbers are masked.
* Group key: congress + bill type + number (``117-hr-5``). A record text that occurs twice is kept once (dropped if the two
  labels differ).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import random
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "congress_bill"
TASK = "congress_bill_status"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.05            # well over 3,300 kept records
TEXT_LIMIT = 1200           # characters of the summary
CONGRESSES = (117, 118)
BILL_TYPES = ("hr", "s")
LABELS = {"introduced": "Introduced only: never reported by a committee or passed by either chamber",
          "reported": "Reported by a committee, but never passed by either chamber",
          "one_chamber": "Passed one chamber (the House or the Senate) only",
          "both_chambers": "Passed both chambers, but did not become law",
          "vetoed": "Vetoed by the President",
          "law": "Became law"}
CODE_REPORTED = {"5000", "14000"}
CODE_PASSED_HOUSE, CODE_PASSED_SENATE = "8000", "17000"
CODE_FAILED = {"9000", "18000"}
CODE_VETO = "31000"
CODE_LAW = {"36000", "41000", "E40000"}
SCRUB = ("became law", "become law", "becomes law", "becoming law", "signed into law", "public law", "public laws",
         "private law", "private laws", "p.l", "pub. l", "enacted", "signed", "signs", "signing", "vetoed", "veto", "vetoes",
         "pocket veto", "override", "overridden", "passed", "passes", "passage", "agreed to", "cleared", "clears",
         "presented to the president", "sent to the president", "reported", "ordered reported", "discharged",
         "placed on the calendar", "calendar no", "legislative calendar", "engrossed", "enrolled", "conference report",
         "cloture", "roll call", "roll no", "yeas and nays", "voice vote", "unanimous consent", "failed of passage",
         "not agreed to", "died in committee")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("What is the furthest stage this bill reached before its Congress ended?",
             "How far did this bill get by the end of its Congress?",
             "Which of these describes the final outcome of this bill?",
             "What became of this bill in its Congress?",
             "Which of these was the furthest step this bill made?")
PARTY = {"D": "Democratic", "R": "Republican", "I": "Independent", "ID": "Independent Democratic", "L": "Libertarian"}
CHAMBER = {"hr": ("House bill", "Representative"), "s": ("Senate bill", "Senator")}
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
_PHONE = re.compile(r"(\(\d{3}\)\s*|\b\d{3}[-.\s])\d{3}[-.\s]\d{4}\b")


# ------------------------------------------------------------------------------------------------------------ parse

def zip_path(raw: str, congress: int, bt: str) -> str:
    return os.path.join(raw, f"BILLSTATUS-{congress}-{bt}.zip")


def safe_xml(data: bytes) -> ET.Element | None:
    """The parsed document, or None if it declares entities (xml.etree never fetches external entities or DTDs)."""
    if b"<!ENTITY" in data:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def html_paragraphs(fragment: str) -> list[str]:
    """CRS summary HTML -> plain-text paragraphs (tags removed, entities decoded); a bold-only paragraph (the short title,
    a section heading) is marked with a leading "**". List items stay in their paragraph."""
    parts = re.split(r"(?i)</p>|<br\s*/?>|</ul>|</ol>|</h\d>", fragment or "")
    out = []
    for p in parts:
        bold = re.fullmatch(r"(?is)\s*<p[^>]*>\s*<(b|strong)>(.*?)</\1>\s*", p)
        p = re.sub(r"(?i)</?(b|strong|i|em|u|span|a|sup|sub|font)\b[^>]*>", "", p)    # inline: no space ("20<b>2</b>3")
        txt = R.norm_ws(html.unescape(re.sub(r"<[^>]+>", " ", p)))
        if txt:
            out.append(("**" if bold else "") + txt)
    return out


_ENDS = re.compile(r"[.!?:;,][\"'\u201d\u2019)\]]*$")


def join_paragraphs(paras: list[str]) -> str:
    """One text: a paragraph without end punctuation gets a period when the next one starts a sentence (a heading before
    its section), and none when the text runs on into a list ("... for" + "the Army; the Navy ...")."""
    out = []
    for i, p in enumerate(paras):
        p = p[2:] if p.startswith("**") else p
        nxt = paras[i + 1].lstrip("*") if i + 1 < len(paras) else ""
        if not _ENDS.search(p) and (not nxt or nxt[:1].isupper() or nxt[:1].isdigit()):
            p += "."
        out.append(p)
    return " ".join(out)


# common.clip / common.drop_sentences split sentences after every ". "; abbreviations ("U.S.", "No.", "v.", "John H.") would
# end a sentence there. The space after them is held as "\x00" (not whitespace) while those helpers run, then restored.
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


def status_of(bill: ET.Element) -> str | None:
    """Furthest status from the laws element and the Library of Congress action codes; None if they conflict."""
    loc = {(it.findtext("actionCode") or "").strip() for it in bill.findall("actions/item")
           if (it.findtext("sourceSystem/name") or "").strip() == "Library of Congress"}
    law_field = any((x.findtext("type") or "").strip() in ("Public Law", "Private Law") for x in bill.findall("laws/item"))
    law_action = bool(loc & CODE_LAW)
    house, senate = CODE_PASSED_HOUSE in loc, CODE_PASSED_SENATE in loc
    if law_field != law_action:
        return None
    if law_field:
        return "law" if house and senate else None
    if CODE_VETO in loc:
        return "vetoed" if house and senate else None
    if house and senate:
        return "both_chambers"
    if house or senate:
        return "one_chamber"
    if loc & CODE_FAILED:
        return None
    return "reported" if loc & CODE_REPORTED else "introduced"


def summary_00(bill: ET.Element) -> str:
    for s in bill.findall("summaries/summary"):
        if (s.findtext("versionCode") or "").strip() == "00" and (s.findtext("actionDesc") or "").startswith("Introduced"):
            return (s.findtext("text") or s.findtext("cdata/text") or "").strip()   # 117th: CDATA text; 118th: cdata/text
    return ""


def official_title(bill: ET.Element) -> str:
    for t in bill.findall("titles/item"):
        if (t.findtext("titleType") or "").strip() == "Official Title as Introduced":
            return R.norm_ws(t.findtext("title") or "")
    return ""


def records(raw: str) -> tuple[list[dict], int]:
    """(bill records, number of zip members that are not a readable bill of the folder's congress and type: the format-1.0.0
    placeholders "Reserved for the Speaker." of the 117th)."""
    out, skipped = [], 0
    for congress in CONGRESSES:
        for bt in BILL_TYPES:
            with zipfile.ZipFile(zip_path(raw, congress, bt)) as zf:
                for name in sorted(zf.namelist()):
                    m = re.fullmatch(rf"BILLSTATUS-{congress}{bt}(\d+)\.xml", name)
                    root = safe_xml(zf.read(name)) if m else None
                    bill = root.find("bill") if root is not None else None
                    if bill is None or (bill.findtext("type") or "").lower() != bt or bill.findtext("congress") != str(congress) \
                            or (bill.findtext("number") or "").strip() != m.group(1):
                        skipped += 1
                        continue
                    num = m.group(1)
                    sp = bill.find("sponsors/item")
                    out.append({"key": f"{congress}-{bt}-{num}", "congress": congress, "type": bt, "num": num,
                                "status": status_of(bill), "title": official_title(bill), "summary": summary_00(bill),
                                "introduced": (bill.findtext("introducedDate") or "").strip(),
                                "party": (sp.findtext("party") or "").strip() if sp is not None else "",
                                "state": (sp.findtext("state") or "").strip() if sp is not None else ""})
    return out, skipped


# ------------------------------------------------------------------------------------------------------------ render

def render(rec: dict, rng: random.Random) -> tuple[str | None, str]:
    """(item text, "") or (None, why the record cannot be used)."""
    title = rec["title"]
    if not title:
        return None, "no_official_title"
    if re.match(r"(?i)(a bill )?for the relief of\b", title):
        return None, "private_relief_bill"
    if R.scrub_hits(title, SCRUB_RE):
        return None, "title_has_scrub_word"
    paras = html_paragraphs(rec["summary"])
    if not paras:
        return None, "no_introduced_summary"
    short = paras.pop(0)[2:] if paras[0].startswith("**") else ""
    if short and R.scrub_hits(short, SCRUB_RE):
        return None, "title_has_scrub_word"
    summary = clip(drop_sentences(mask_contacts(join_paragraphs(paras)), SCRUB_RE), TEXT_LIMIT)
    if not summary:
        return None, "no_summary_left_after_scrub"
    kind, member = CHAMBER[rec["type"]]
    head = f"US Congress bill ({kind}, {rec['congress']}th Congress, introduced {rec['introduced'] or 'on an unknown date'})"
    lines = [head]
    if rec["party"] in PARTY and rec["state"]:
        lines.append(f"Sponsor: {PARTY[rec['party']]} {member.lower()} from {rec['state']}")
    lines.append(f"Official title: {title}")
    if short:
        lines.append(f"Short title: {short}")
    lines.append(f"Summary of the bill as introduced (Congressional Research Service): {summary}")
    record = "\n".join(lines)
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours
        return None, "scrub_word_left"
    return record + "\n\n" + rng.choice(QUESTIONS), ""


def introduced(rec: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(rec["introduced"][:10])
    except ValueError:
        return None


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, skipped = records(raw)
    n_read = len(recs)
    from collections import Counter
    drops: Counter = Counter()
    kept = []
    for rec in recs:
        if rec["status"] is None:
            drops["label_conflict_or_failed_vote"] += 1
            continue
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text, why = render(rec, rng)
        if text is None:
            drops[why] += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    by_text: dict[str, list[dict]] = {}
    for rec in kept:
        by_text.setdefault(R.norm_ws(rec["text"].rsplit("\n\n", 1)[0]).lower(), []).append(rec)
    unique = []
    for group in by_text.values():
        group.sort(key=lambda r: r["key"])
        if len({r["status"] for r in group}) == 1:
            unique.append(group[0])
        drops["duplicate_text"] += len(group) - (len({r["status"] for r in group}) == 1)
    capped, class_report = R.cap_classes(unique, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["status"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["status"]], source="congress_bill",
                             source_id=rec["key"], snapshot=snapshot, record_date=introduced(rec), shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "BILLSTATUS laws element + Library of Congress action codes (furthest status)",
                "labels": LABELS, "records_read": n_read, "zip_members_not_a_bill_record": skipped,
                "status_read": dict(sorted(Counter(str(r["status"]) for r in recs).items())),
                "dropped": dict(sorted(drops.items())), "kept_before_caps": len(unique), **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def _parts(source_id: str) -> tuple[int, str, str]:
    congress, bt, num = source_id.split("-")
    return int(congress), bt, num


def source_url(row: dict, snapshot: str) -> str:
    congress, bt, num = _parts(row["source_id"])
    return f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{congress}/{bt}/BILLSTATUS-{congress}{bt}{num}.xml"


_ZIPS: dict[tuple[str, int, str], zipfile.ZipFile] = {}


def _raw_xml(snapshot: str, congress: int, bt: str, num: str) -> str | None:
    """The raw XML text of one bill, read from the snapshot's zip (each zip opened once per process)."""
    k = (snapshot, congress, bt)
    if k not in _ZIPS:
        _ZIPS[k] = zipfile.ZipFile(zip_path(os.path.join(R.RAW, DOMAIN, snapshot), congress, bt))
    try:
        return _ZIPS[k].read(f"BILLSTATUS-{congress}{bt}{num}.xml").decode("utf-8", "replace")
    except KeyError:
        return None


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The status read again from the raw XML by a plain text scan (not the builder's tree walk): the law number element,
    the Library of Congress action codes 31000 / 8000 / 17000 / 5000 / 14000, and whether the item's title line is the
    record's official title as introduced."""
    congress, bt, num = _parts(row["source_id"])
    xml = _raw_xml(snapshot, congress, bt, num)
    if xml is None:
        return None, False
    codes = set(re.findall(r"<actionCode>([0-9]+)</actionCode>\s*<sourceSystem>\s*<code>9</code>", xml))
    if re.search(r"<laws>\s*<item>\s*<type>(Public|Private) Law</type>", xml):
        label = "law"
    elif "31000" in codes:
        label = "vetoed"
    elif {"8000", "17000"} <= codes:
        label = "both_chambers"
    elif codes & {"8000", "17000"}:
        label = "one_chamber"
    elif codes & {"5000", "14000"}:
        label = "reported"
    else:
        label = "introduced"
    m = re.search(r"<titleType>Official Title as Introduced</titleType>\s*(?:<titleTypeCode>\d+</titleTypeCode>\s*)?"
                  r"<title>(.*?)</title>", xml, re.S)
    title = R.norm_ws(html.unescape(m.group(1))) if m else ""
    text_ok = bool(title) and f"\nOfficial title: {title}\n" in row["questions"][0]["instructions"]
    return LABELS[label], text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows, classes {m['splits'][s]['class_prior']}, gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']} (status {m['status_read']}), dropped {m['dropped']}, kept before caps "
          f"{m['kept_before_caps']}, classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
