"""#20 Federal Register documents -> issuing agency: eval-v5.1 mirror rows (part N, task type ``fedreg_agency``).

    python -I tools/records/build_fedreg_agency.py --snapshot 2026-10-27

Records: the documents of the federalregister.gov API v1 published 2025-01-01 to 2026-10-26 (rules, proposed rules,
notices; presidential documents have no abstract), read from the raw weekly pages as data.
* Label: the structured ``agencies`` field. A document is single-agency when its agencies with an id form one chain (one
  agency plus the departments above it, as the Federal Register lists a sub-agency with its parent: "Transportation
  Department; Federal Aviation Administration"); the label is the most specific agency of the chain. Documents of two or
  more agencies (joint rules) are dropped. Kept: the 26 most frequent agencies (by usable records) of the 34 candidates in
  ``AGENCIES``; documents of other agencies are dropped.
* Not used as input: documents on enforcement settlements / consent decrees, visa fees and transit fares (the held-out
  domains: EPA enforcement cases, visa fee-waiver rules, transit fares). NHTSA documents and recall documents were
  excluded too until 29 Oct, as the dev source; they may now be used (data/DEV-GUIDELINES.md section 5).
* Record text: document type and publication date and the abstract (the document's summary; GPO character codes decoded,
  footnotes cut), cut at a sentence boundary. Not used: title, action, agencies, docket ids, CFR references (they name the
  agency or its CFR title). Every sentence that contains a word of ``SCRUB`` (each candidate agency's name, acronym,
  parent department, sub-units and flagship programs and statutes, and "Commission") is removed; a record with less than
  ``MIN_SUMMARY`` characters left, or whose abstract is a table (meeting agendas), is dropped. E-mail addresses and phone
  numbers are masked; a record whose abstract names a person ("Mr. X", "Jane Q. Doe", "M.D.") or that is an order against
  one (debarment, denial of hearing, DEA decision and order, ...: the title says so) is dropped.
* Group key: the document number. A summary text that occurs more than once (boilerplate notices) is kept once, and not at
  all if its documents have different agencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "fedreg_agency"
TASK = "fedreg_agency"
AREA = "retrieval"          # one of many categories, as the dev set's nhtsa_recall_component
EVAL_FRAC = 0.05            # well over 3,300 kept records
TEXT_LIMIT = 900
MIN_SUMMARY = 100           # characters left after the scrub: less is a fragment ("(OTS).", "Eastern Time on ...")
N_CLASSES = 26
FIRST, LAST = "2025-01-01", "2026-10-26"
DOT = ("Department of Transportation", "Transportation Department", "DOT", "USDOT", "Secretary of Transportation",
       "Office of the Secretary of Transportation")
DOI = ("Department of the Interior", "Interior Department", "DOI", "Secretary of the Interior", "Interior")
DOC = ("Department of Commerce", "Commerce Department", "DOC", "Secretary of Commerce", "Commerce")
HHS = ("Department of Health and Human Services", "Health and Human Services Department", "Health and Human Services",
       "HHS", "Secretary of Health and Human Services")
DHS = ("Department of Homeland Security", "Homeland Security Department", "Homeland Security", "DHS",
       "Secretary of Homeland Security")
TREAS = ("Department of the Treasury", "Treasury Department", "Treasury", "Secretary of the Treasury")
DOJ = ("Department of Justice", "Justice Department", "DOJ", "Attorney General")
# Federal Register agency name -> (option text, words that name it, its parent department, sub-units or flagship programs)
AGENCIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Federal Aviation Administration": ("Federal Aviation Administration", (
        "Federal Aviation Administration", "FAA", "airworthiness", "airworthiness directive", "airworthiness directives",
        "AD", "ADs") + DOT),
    "National Park Service": ("National Park Service", (
        "National Park Service", "NPS", "Native American Graves Protection and Repatriation Act", "NAGPRA",
        "National Register of Historic Places", "National Register", "National Park", "National Parks",
        "National Park System", "National Historical Park", "National Historic Landmark", "National Historic Landmarks",
        "National Seashore", "National Lakeshore", "National Recreation Area", "National Battlefield") + DOI),
    "National Oceanic and Atmospheric Administration": ("National Oceanic and Atmospheric Administration", (
        "National Oceanic and Atmospheric Administration", "NOAA", "National Marine Fisheries Service", "NMFS",
        "NOAA Fisheries", "National Weather Service", "National Ocean Service", "Fishery Management Council",
        "Fishery Management Councils", "Magnuson-Stevens", "Magnuson-Stevens Act",
        "Magnuson-Stevens Fishery Conservation and Management Act", "Marine Mammal Protection Act", "MMPA",
        "National Marine Sanctuary", "National Marine Sanctuaries", "incidental harassment authorization", "IHA", "SEDAR",
        "Southeast Data, Assessment, and Review") + DOC),
    "International Trade Administration": ("International Trade Administration", (
        "International Trade Administration", "ITA", "Enforcement and Compliance") + DOC),
    "Environmental Protection Agency": ("Environmental Protection Agency", (
        "Environmental Protection Agency", "EPA", "Clean Air Act", "CAA", "state implementation plan",
        "state implementation plans", "SIP", "SIPs", "Toxic Substances Control Act", "TSCA",
        "Federal Insecticide, Fungicide, and Rodenticide Act", "FIFRA", "CERCLA", "Superfund",
        "Resource Conservation and Recovery Act", "RCRA", "Safe Drinking Water Act", "SDWA", "NESHAP", "NSPS",
        "National Ambient Air Quality Standards", "National Ambient Air Quality Standard", "NAAQS")),
    "Food and Drug Administration": ("Food and Drug Administration", (
        "Food and Drug Administration", "FDA", "Federal Food, Drug, and Cosmetic Act", "FD&C Act",
        "Commissioner of Food and Drugs", "Center for Drug Evaluation and Research", "CDER",
        "Center for Biologics Evaluation and Research", "CBER", "Center for Devices and Radiological Health", "CDRH",
        "Center for Food Safety and Applied Nutrition", "CFSAN", "abbreviated new drug application",
        "abbreviated new drug applications", "ANDA", "ANDAs", "new drug application", "new drug applications", "NDA", "NDAs",
        "biologics license application", "BLA", "premarket approval", "PMA", "ICH",
        "International Council for Harmonisation") + HHS),
    "Coast Guard": ("Coast Guard", ("Coast Guard", "USCG", "Captain of the Port", "COTP", "Coast Guard District", "special local regulation",
                                  "special local regulations", "SLR", "SLRs") + DHS),
    "Defense Department": ("Department of Defense", (
        "Department of Defense", "Defense Department", "DoD", "Department of War", "War Department", "DoW",
        "Secretary of Defense", "Secretary of War", "Pentagon", "Defense Federal Acquisition Regulation Supplement",
        "DFARS", "Defense Acquisition Regulations System", "DARS", "Defense Security Cooperation Agency", "DSCA",
        "TRICARE", "Defense Health Agency", "DHA", "Under Secretary of Defense", "OUSD",
        "Science and Technology Reinvention Laboratory", "STRL", "STRLs")),
    "Federal Communications Commission": ("Federal Communications Commission", (
        "Federal Communications Commission", "FCC", "Communications Act", "Media Bureau", "Wireline Competition Bureau",
        "Wireless Telecommunications Bureau", "Public Safety and Homeland Security Bureau",
        "Consumer and Governmental Affairs Bureau", "Office of Engineering and Technology", "Enforcement Bureau",
        "Space Bureau", "Universal Service Fund", "USF", "Open Commission Meeting", "Lifeline", "GN Docket", "WC Docket",
        "MB Docket", "ET Docket", "WT Docket", "PS Docket", "CG Docket", "IB Docket", "EB Docket", "OET Docket", "FNPRM", "Further Notice of Proposed Rulemaking")),
    "International Trade Commission": ("U.S. International Trade Commission", (
        "U.S. International Trade Commission", "International Trade Commission", "USITC", "ITC", "section 337")),
    "Postal Service": ("United States Postal Service", (
        "United States Postal Service", "U.S. Postal Service", "Postal Service", "USPS", "Mail Classification Schedule",
        "Negotiated Service Agreement", "Negotiated Service Agreements", "Priority Mail", "Postmaster General")),
    "Nuclear Regulatory Commission": ("Nuclear Regulatory Commission", (
        "U.S. Nuclear Regulatory Commission", "Nuclear Regulatory Commission", "NRC", "Atomic Safety and Licensing Board",
        "ASLB", "Advisory Committee on Reactor Safeguards", "ACRS", "Sensitive Unclassified Non-Safeguards Information",
        "SUNSI")),
    "Education Department": ("Department of Education", (
        "Department of Education", "Education Department", "ED", "Secretary of Education",
        "Office of Elementary and Secondary Education", "OESE", "Office of Postsecondary Education",
        "Office of Special Education and Rehabilitative Services", "OSERS", "Institute of Education Sciences",
        "Federal Student Aid", "National Assessment Governing Board", "Higher Education Act", "HEA", "notice inviting applications", "NIA",
        "National Advisory Committee on Institutional Quality and Integrity", "NACIQI")),
    "Small Business Administration": ("Small Business Administration", ("Small Business Administration", "SBA", "Economic Injury Disaster Loan",
        "Economic Injury Disaster Loans", "EIDL", "EIDLs")),
    "Internal Revenue Service": ("Internal Revenue Service", (
        "Internal Revenue Service", "IRS", "Internal Revenue Code") + TREAS),
    "Postal Regulatory Commission": ("Postal Regulatory Commission", ("Postal Regulatory Commission", "PRC")),
    "Energy Department": ("Department of Energy", (
        "Department of Energy", "Energy Department", "DOE", "Secretary of Energy",
        "Office of Energy Efficiency and Renewable Energy", "EERE", "Grid Deployment Office", "Loan Programs Office",
        "Office of Fossil Energy and Carbon Management", "Energy Policy and Conservation Act", "EPCA", "Natural Gas Act", "NGA",
        "Site-Specific Advisory Board", "SSAB")),
    "State Department": ("Department of State", (
        "Department of State", "State Department", "DOS", "Secretary of State", "Assistant Secretary of State",
        "Bureau of Educational and Cultural Affairs", "Directorate of Defense Trade Controls", "DDTC",
        "International Traffic in Arms Regulations", "ITAR", "Cultural Property Advisory Committee")),
    "Federal Emergency Management Agency": ("Federal Emergency Management Agency", (
        "Federal Emergency Management Agency", "FEMA", "National Flood Insurance Program", "NFIP",
        "Flood Insurance Rate Map", "Flood Insurance Rate Maps", "Flood Insurance Study", "Base Flood Elevation",
        "Base Flood Elevations", "BFE", "BFEs", "Special Flood Hazard Area", "Special Flood Hazard Areas", "SFHA",
        "flood hazard determination", "flood hazard determinations") + DHS),
    "Justice Department": ("Department of Justice", DOJ + (
        "U.S. Marshals Service", "USMS", "Office of Justice Programs", "OJP", "Bureau of Justice Assistance", "BJA",
        "Bureau of Justice Statistics", "BJS", "Office on Violence Against Women", "OVW", "Bureau of Prisons", "BOP",
        "Office of Juvenile Justice and Delinquency Prevention", "OJJDP", "National Institute of Justice", "NIJ",
        "Federal Bureau of Investigation", "FBI", "Antitrust Division")),
    "Centers for Medicare & Medicaid Services": ("Centers for Medicare & Medicaid Services", (
        "Centers for Medicare & Medicaid Services", "Centers for Medicare and Medicaid Services", "CMS", "Medicare",
        "Medicaid", "Children's Health Insurance Program", "CHIP", "prospective payment system", "prospective payment systems", "PPS", "IRF", "IRFs",
        "Quality Reporting Program", "QRP", "Clinical Laboratory Improvement Amendments", "CLIA") + HHS),
    "Veterans Affairs Department": ("Department of Veterans Affairs", (
        "Department of Veterans Affairs", "Veterans Affairs Department", "VA", "Secretary of Veterans Affairs",
        "Veterans Health Administration", "VHA", "Veterans Benefits Administration", "VBA",
        "National Cemetery Administration", "Dependency and Indemnity Compensation", "DIC")),
    "Drug Enforcement Administration": ("Drug Enforcement Administration", (
        "Drug Enforcement Administration", "DEA", "Controlled Substances Act", "CSA") + DOJ),
    "Federal Motor Carrier Safety Administration": ("Federal Motor Carrier Safety Administration", (
        "Federal Motor Carrier Safety Administration", "FMCSA", "Federal Motor Carrier Safety Regulations", "FMCSRs",
        "FMCSR") + DOT),
    "Maritime Administration": ("Maritime Administration", ("Maritime Administration", "MARAD") + DOT),
    "Housing and Urban Development Department": ("Department of Housing and Urban Development", (
        "Department of Housing and Urban Development", "Housing and Urban Development Department",
        "Housing and Urban Development", "HUD", "Secretary of Housing and Urban Development",
        "Federal Housing Administration", "FHA", "Office of Public and Indian Housing", "Ginnie Mae",
        "Government National Mortgage Association", "Community Development Block Grant", "CDBG", "Manufactured Housing Consensus Committee",
        "MHCC", "Housing Trust Fund", "HTF", "NSPIRE", "Housing Choice Voucher", "Housing Choice Vouchers", "HCV")),
    "Federal Railroad Administration": ("Federal Railroad Administration", ("Federal Railroad Administration", "FRA") + DOT),
    "U.S. Customs and Border Protection": ("U.S. Customs and Border Protection", (
        "U.S. Customs and Border Protection", "Customs and Border Protection", "CBP", "USCBP") + DHS),
    "Fish and Wildlife Service": ("Fish and Wildlife Service", (
        "U.S. Fish and Wildlife Service", "Fish and Wildlife Service", "FWS", "USFWS", "habitat conservation plan",
        "habitat conservation plans", "HCP", "HCPs", "National Wildlife Refuge", "National Wildlife Refuge System") + DOI),
    "Foreign Assets Control Office": ("Office of Foreign Assets Control", (
        "Office of Foreign Assets Control", "Foreign Assets Control Office", "OFAC", "Specially Designated Nationals",
        "SDN List", "SDN") + TREAS),
    "Pipeline and Hazardous Materials Safety Administration": ("Pipeline and Hazardous Materials Safety Administration", (
        "Pipeline and Hazardous Materials Safety Administration", "PHMSA", "Hazardous Materials Regulations", "HMR")
        + DOT),
    "Civil Rights Commission": ("U.S. Commission on Civil Rights", (
        "U.S. Commission on Civil Rights", "Commission on Civil Rights", "Civil Rights Commission", "USCCR")),
    "Labor Department": ("Department of Labor", (
        "Department of Labor", "Labor Department", "DOL", "Secretary of Labor")),
    "Land Management Bureau": ("Bureau of Land Management", (
        "Bureau of Land Management", "Land Management Bureau", "BLM", "Federal Land Policy and Management Act",
        "FLPMA", "Public Land Order", "Public Land Orders", "PLO", "PLOs") + DOI),
}
LABELS = {name: option for name, (option, _) in AGENCIES.items()}
SCRUB = tuple(sorted({w for _, (option, words) in AGENCIES.items() for w in (option,) + words} |
                     {"Commission", "Commissions", "Commissioner", "Commissioners"}))
SCRUB_RE = R.scrub_pattern(SCRUB)
EXCLUDED_AGENCIES: set[str] = set()     # NHTSA (the dev recall source) was excluded until 29 Oct; it may now be used
HELD_OUT_TITLE = re.compile(r"(?i)\b(consent decrees?|settlements?|settlement agreements?|consent agreements?|"
                            r"fares?)\b|\bvisas?\b.*\bfees?\b|\bfees?\b.*\bvisas?\b")
QUESTIONS = ("Which agency issued this Federal Register document?",
             "Which federal agency published this document?",
             "Which of these agencies is the source of this document?",
             "This document was issued by which agency?",
             "Which agency is responsible for this document?")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
_PHONE = re.compile(r"(\(\d{3}\)\s*|\b1-\d{3}-|\b\d{3}[-.])\d{3}[-.]\d{4}\b")
_PERSON_ORDER = re.compile(r"(?i)\b(debarment|debarring|debarred|denial of hearing|decision and order|order prohibiting|"
                           r"disqualification|disqualified|revocation of registration|order to show cause|immediate suspension)\b")
_PERSON = re.compile(r"\b(Mr|Mrs|Ms|Dr)\.\s+[A-Z][a-z]|\b[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+\b|"
                     r",\s*(M\.D|D\.O|D\.D\.S|D\.M\.D|D\.V\.M|N\.P|P\.A|R\.Ph|Pharm\.D|APRN|CRNA)\b")
# common.clip / common.drop_sentences split sentences after every ". "; abbreviations ("U.S.", "No.", "Jane Q.") would end a
# sentence there. The space after them is held as "\x00" (not whitespace) while those helpers run, then restored.
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


_GPO_ENTITY = re.compile(r"\[([a-z]{2,8})\]")         # GPO character codes: "T[uuml]rkiye"
_FOOTNOTE = re.compile(r"\\\d+\\")                     # GPO footnote markers: "\1\"
_RULE = re.compile(r"-{4,}|_{4,}")                       # a rule; in an abstract the text after it is footnotes
_TABLE = re.compile(r"\.{4,}|\b(Title|Summary):")        # dot leaders or an agenda table ("2....... Space ... Title: ...")


def _entity(m: re.Match) -> str:
    ch = html.unescape(f"&{m.group(1)};")
    return ch if len(ch) == 1 else m.group(0)


def normalize_abstract(text: str) -> str:
    """The abstract as plain text: GPO character codes decoded, footnote markers removed, footnotes after a rule cut off,
    e-mail addresses and phone numbers masked."""
    text = _FOOTNOTE.sub("", _GPO_ENTITY.sub(_entity, text or ""))
    return R.norm_ws(mask_contacts(_RULE.split(text, 1)[0]))


# ------------------------------------------------------------------------------------------------------------ parse

def issuing_agency(agencies: list) -> str | None:
    """The most specific agency when the agencies with an id form one chain (an agency and its parents), else None."""
    ag = [a for a in agencies if isinstance(a, dict) and a.get("id") is not None]
    if not ag:
        return None
    by = {a["id"]: a for a in ag}
    leaves = [a for a in ag if a["id"] not in {b.get("parent_id") for b in ag}]
    if len(leaves) != 1:
        return None
    chain, cur = set(), leaves[0]
    while cur is not None and cur["id"] not in chain:
        chain.add(cur["id"])
        cur = by.get(cur.get("parent_id"))
    return leaves[0].get("name") if chain == set(by) else None


def pages(raw: str) -> list[str]:
    return sorted(glob.glob(os.path.join(raw, "documents", "*.json")))


def records(raw: str) -> tuple[list[dict], int]:
    """(one record per document number, number of documents read)."""
    out: dict[str, dict] = {}
    n = 0
    for p in pages(raw):
        for d in json.load(open(p, encoding="utf-8")).get("results") or []:
            n += 1
            num = d.get("document_number")
            if not num or num in out:
                continue
            out[num] = {"key": num, "agency": issuing_agency(d.get("agencies") or []), "type": d.get("type") or "",
                        "date": d.get("publication_date") or "", "title": R.norm_ws(d.get("title") or ""),
                        "abstract": R.norm_ws(d.get("abstract") or "")}
    return [out[k] for k in sorted(out)], n


# ------------------------------------------------------------------------------------------------------------ render

def render(rec: dict, rng: random.Random) -> tuple[str | None, str]:
    """(item text, "") or (None, why the record cannot be used)."""
    if not rec["abstract"]:
        return None, "no_abstract"
    if rec["agency"] is None:
        return None, "no_single_issuing_agency"
    if rec["agency"] in EXCLUDED_AGENCIES or HELD_OUT_TITLE.search(rec["title"]):
        return None, "held_out_or_dev_topic"
    if not FIRST <= rec["date"] <= LAST:
        return None, "outside_date_range"
    if rec["agency"] not in AGENCIES:
        return None, "agency_not_a_candidate"
    if _PERSON.search(rec["abstract"]) or _PERSON_ORDER.search(rec["title"]):    # names a person / an order against one
        return None, "names_a_person"
    if _TABLE.search(rec["abstract"]):
        return None, "table_not_prose"
    summary = clip(drop_sentences(normalize_abstract(rec["abstract"]), SCRUB_RE), TEXT_LIMIT)
    if len(summary) < MIN_SUMMARY:
        return None, "too_little_left_after_scrub"
    record = f"Federal Register document ({rec['type'] or 'document'}, published {rec['date']})\nSummary: {summary}"
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours
        return None, "scrub_word_left"
    return record + "\n\n" + rng.choice(QUESTIONS), ""


def published(rec: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(rec["date"][:10])
    except ValueError:
        return None


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, n_docs = records(raw)
    from collections import Counter
    drops: Counter = Counter()
    kept = []
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text, why = render(rec, rng)
        if text is None:
            drops[why] += 1
            continue
        rec["text"] = text
        kept.append(rec)
    by_summary: dict[str, list[dict]] = {}
    for rec in kept:        # boilerplate notices: one record per summary text, none if the agencies differ
        by_summary.setdefault(R.norm_ws(rec["text"].rsplit("\n\n", 1)[0].split("\nSummary: ", 1)[1]).lower(), []).append(rec)
    unique = []
    for group in by_summary.values():
        agencies = {r["agency"] for r in group}
        if len(agencies) == 1:
            unique.append(min(group, key=lambda r: r["key"]))
        drops["duplicate_summary"] += len(group) - (len(agencies) == 1)
    counts = Counter(r["agency"] for r in unique)
    classes = sorted(counts, key=lambda a: (-counts[a], a))[:N_CLASSES]
    drops["agency_not_among_the_most_frequent"] += sum(counts[a] for a in counts if a not in classes)
    usable = [r for r in unique if r["agency"] in classes]
    for r in usable:
        r["split"] = R.split_of(DOMAIN, r["key"], EVAL_FRAC)
    capped, class_report = R.cap_classes(usable, lambda r: r["agency"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["agency"] for r in capped}
    labels = [LABELS[a] for a in AGENCIES if a in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["agency"]], source="fedreg",
                             source_id=rec["key"], snapshot=snapshot, record_date=published(rec), shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "agencies (single chain; the most specific agency)", "labels": LABELS,
                "classes_kept": [LABELS[a] for a in classes], "documents_read": n_docs, "records_read": len(recs),
                "usable_per_agency": {LABELS[a]: counts[a] for a in classes}, "dropped": dict(sorted(drops.items())),
                **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://www.federalregister.gov/d/{row['source_id']}"


_INDEX: dict[str, dict[str, str]] = {}
_PARENTS: dict[str, dict[int, int | None]] = {}


def _raw_doc_text(snapshot: str, num: str) -> str | None:
    """The raw JSON text of one document object, found by a text scan of the weekly pages (indexed once per process)."""
    if snapshot not in _INDEX:
        idx: dict[str, str] = {}
        for p in pages(os.path.join(R.RAW, DOMAIN, snapshot)):
            txt = open(p, encoding="utf-8").read()
            starts = [m.start() for m in re.finditer(r'\{"abstract":', txt)] + [len(txt)]
            for a, b in zip(starts, starts[1:]):
                m = re.search(r'"document_number":"([^"]+)"', txt[a:b])
                if m:
                    idx.setdefault(m.group(1), txt[a:b])
        _INDEX[snapshot] = idx
    return _INDEX[snapshot].get(num)


def _agency_parents(snapshot: str) -> dict[int, int | None]:
    """agency id -> parent id, from the separately fetched agencies.json (not from the document's own agency list)."""
    if snapshot not in _PARENTS:
        ag = json.load(open(os.path.join(R.RAW, DOMAIN, snapshot, "agencies.json"), encoding="utf-8"))
        _PARENTS[snapshot] = {a["id"]: a.get("parent_id") for a in ag}
    return _PARENTS[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The agency read again from the raw page text: the (id, name) pairs of the document's agencies field by a plain scan,
    the hierarchy from agencies.json; the label is the one agency that is not a parent of another listed agency, if every
    other listed agency is one of its ancestors. text_ok: the item's summary is whole sentences of the abstract, in order."""
    blob = _raw_doc_text(snapshot, row["source_id"])
    if blob is None:
        return None, False
    m = re.search(r'"agencies":\[(.*?)\],"document_number"', blob)
    pairs = re.findall(r'"name":"((?:[^"\\]|\\.)*)","id":(\d+)', m.group(1)) if m else []
    parents = _agency_parents(snapshot)
    ids = {int(i): json.loads(f'"{n}"') for n, i in pairs}
    label = None
    leaves = [i for i in ids if not any(parents.get(j) == i for j in ids)]
    if len(leaves) == 1:
        anc, cur = set(), leaves[0]
        while cur is not None and cur not in anc:
            anc.add(cur)
            cur = parents.get(cur)
        if set(ids) <= anc:
            label = LABELS.get(ids[leaves[0]])
    am = re.search(r'\{"abstract":("(?:[^"\\]|\\.)*")', blob)
    abstract = normalize_abstract(json.loads(am.group(1))) if am else ""
    summary = row["questions"][0]["instructions"].split("\nSummary: ", 1)[1].rsplit("\n\n", 1)[0]
    rest = summary
    for unit in re.split(r"(?<=[.!?])\s+", _hold(abstract)):     # the abstract's sentence units, as common splits them
        unit = unit.replace("\x00", " ")
        if rest == unit or rest.startswith(unit + " "):
            rest = rest[len(unit):].lstrip(" ")
    return label, bool(abstract) and rest == ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows, fresh {m['splits'][s]['fresh']}, {len(m['splits'][s]['class_prior'])} "
              f"classes {m['splits'][s]['class_prior']}")
    print(f"documents read {m['documents_read']}, records {m['records_read']}, dropped {m['dropped']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
