"""#17 EU public tenders -> CPV division: eval-v5.1 mirror rows (part N, task type ``ted_cpv_division``).

    python -I tools/records/build_ted_cpv.py --snapshot 2026-10-27

Records: the notices of the stored TED API v3 search pages (English an official language, published 2026-01-01 to
2026-10-26), read as data.
* Label: the CPV division (first two digits) of the structured ``classification-cpv`` field: the main (first) code's division,
  kept only when every code of the notice is in the same division and ``main-classification-proc`` (when present) agrees.
  ``CPV_DIVISIONS`` maps division -> official English name and is checked against the stored official list (the EU
  Publications Office's CPV 2008 labels) at every build. Kept: the MAX_CLASSES (26) most frequent divisions with >= 20 records.
* Record text: the publication date, the procedure title (``title-proc``) and the procedure description (``description-proc``)
  in English, cut at a sentence boundary. Not used: ``notice-title`` (TED composes it from the main CPV code's name), any CPV
  code, the notice type, the buyer. Every sentence that contains a word of ``SCRUB`` (the CPV division names, the phrases
  of them that name a division on their own, single name words that name one division, "CPV") or an 8-digit CPV-like code
  is removed; a record whose title contains one is dropped. E-mail addresses and phone numbers are masked. Dropped as well:
  items with fewer than two words, and items not in English (some "eng" fields hold another language: more function
  words of other EU languages than English ones).
* Group key: the notice's publication number. One notice per procedure is kept (the first published of those that qualify),
  and one notice per item text (none if their divisions differ), so that a contract notice and its award notice do not end
  up in two splits.
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
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ted_cpv"
TASK = "ted_cpv_division"
AREA = "retrieval"          # one of many categories
EVAL_FRAC = 0.05            # more than ~3,300 records are kept
TEXT_LIMIT = 900
MAX_CLASSES = 26
CPV_DIVISIONS = {
    "03": "Agricultural, farming, fishing, forestry and related products",
    "09": "Petroleum products, fuel, electricity and other sources of energy",
    "14": "Mining, basic metals and related products",
    "15": "Food, beverages, tobacco and related products",
    "16": "Agricultural machinery",
    "18": "Clothing, footwear, luggage articles and accessories",
    "19": "Leather and textile fabrics, plastic and rubber materials",
    "22": "Printed matter and related products",
    "24": "Chemical products",
    "30": "Office and computing machinery, equipment and supplies except furniture and software packages",
    "31": "Electrical machinery, apparatus, equipment and consumables; lighting",
    "32": "Radio, television, communication, telecommunication and related equipment",
    "33": "Medical equipments, pharmaceuticals and personal care products",
    "34": "Transport equipment and auxiliary products to transportation",
    "35": "Security, fire-fighting, police and defence equipment",
    "37": "Musical instruments, sport goods, games, toys, handicraft, art materials and accessories",
    "38": "Laboratory, optical and precision equipments (excl. glasses)",
    "39": "Furniture (incl. office furniture), furnishings, domestic appliances (excl. lighting) and cleaning products",
    "41": "Collected and purified water",
    "42": "Industrial machinery",
    "43": "Machinery for mining, quarrying, construction equipment",
    "44": "Construction structures and materials; auxiliary products to construction (except electric apparatus)",
    "45": "Construction work",
    "48": "Software package and information systems",
    "50": "Repair and maintenance services",
    "51": "Installation services (except software)",
    "55": "Hotel, restaurant and retail trade services",
    "60": "Transport services (excl. Waste transport)",
    "63": "Supporting and auxiliary transport services; travel agencies services",
    "64": "Postal and telecommunications services",
    "65": "Public utilities",
    "66": "Financial and insurance services",
    "70": "Real estate services",
    "71": "Architectural, construction, engineering and inspection services",
    "72": "IT services: consulting, software development, Internet and support",
    "73": "Research and development services and related consultancy services",
    "75": "Administration, defence and social security services",
    "76": "Services related to the oil and gas industry",
    "77": "Agricultural, forestry, horticultural, aquacultural and apicultural services",
    "79": "Business services: law, marketing, consulting, recruitment, printing and security",
    "80": "Education and training services",
    "85": "Health and social work services",
    "90": "Sewage, refuse, cleaning and environmental services",
    "92": "Recreational, cultural and sporting services",
    "98": "Other community, social and personal services"}
LABELS = CPV_DIVISIONS
# The phrases of the division names that name a division on their own (as a notice would write them).
NAME_PARTS = (
    "agricultural products", "farming products", "fishing products", "forestry products", "petroleum products",
    "sources of energy", "basic metals", "food products", "beverages", "tobacco", "agricultural machinery", "clothing",
    "footwear", "luggage", "textile fabrics", "plastic materials", "rubber materials", "printed matter", "chemical products",
    "office machinery", "computing machinery", "office equipment", "office supplies", "computing equipment",
    "electrical machinery", "electrical apparatus", "electrical equipment", "electrical consumables",
    "telecommunication equipment", "telecommunications equipment", "communication equipment", "radio equipment",
    "television equipment", "medical equipment", "medical equipments", "pharmaceuticals", "pharmaceutical products",
    "personal care products", "transport equipment", "security equipment", "fire-fighting equipment", "firefighting equipment",
    "police equipment", "defence equipment", "defense equipment", "musical instruments", "sport goods", "sports goods",
    "toys", "handicraft", "art materials", "laboratory equipment", "laboratory equipments", "optical equipment",
    "precision equipment", "furniture", "furnishings", "domestic appliances", "cleaning products", "purified water",
    "collected water", "industrial machinery", "mining machinery", "quarrying machinery", "construction equipment",
    "construction structures", "construction materials", "construction products", "construction work", "construction works",
    "software package", "software packages", "information systems", "information system", "repair and maintenance",
    "maintenance services", "repair services", "installation services", "hotel services", "restaurant services",
    "retail trade services", "transport services", "auxiliary transport services", "travel agency", "travel agencies",
    "postal services", "telecommunications services", "telecommunication services", "public utilities",
    "financial services", "insurance services", "financial and insurance", "real estate services",
    "architectural services", "engineering services", "inspection services", "construction services", "it services",
    "software development", "internet services", "research and development", "consultancy services", "consulting services",
    "administration services", "social security services", "oil and gas industry", "agricultural services",
    "forestry services", "horticultural services", "business services", "legal services", "marketing services",
    "recruitment services", "printing services", "security services", "education services", "training services",
    "education and training", "health services", "social work", "health and social work", "sewage", "refuse",
    "cleaning services", "environmental services", "recreational services", "cultural services", "sporting services",
    "community services", "social services", "personal services")
# Single words of the names that name one division on their own (and their plain word forms). Generic words of the names
# (services, equipment, products, construction, transport, software, health, ...) stay: most notices of many divisions use them.
KEYWORDS = ("fuel", "fuels", "electricity", "petroleum", "insurance", "insurer", "insurers", "pharmaceutical", "architectural",
            "architect", "architects", "recruitment", "marketing", "horticultural", "forestry", "postal", "hotel", "hotels",
            "restaurant", "restaurants", "laboratory", "laboratories", "telecommunication", "telecommunications", "television",
            "quarrying", "recreational", "real estate", "reinsurance",
            # label words and synonyms found among the leak check's telling words (education and training, retail trade,
            # computing machinery, lighting, hotel and restaurant services, television)
            "trainings", "training course", "training courses", "training programme", "training programmes",
            "training program", "training programs", "retail", "computing", "computers", "lighting", "lights", "hospitality",
            "tv")
SCRUB = (("cpv", "common procurement vocabulary") + tuple(sorted({v.lower() for v in CPV_DIVISIONS.values()})) + NAME_PARTS
         + KEYWORDS)
SCRUB_RE = R.scrub_pattern(SCRUB)
CODE_RE = re.compile(r"\b\d{8}(-\d)?\b")
# Some "eng" fields hold another language: an item is dropped when it has more function words of other EU languages than
# English ones (and at least two of them).
EN_WORDS = frozenset("the and of to for in an is are will be with on by as this that from or at which shall all its their it "
                     "has have under within including into".split())
FOREIGN_WORDS = frozenset((
    "und der die das für von mit zur zum den dem des ein eine im auf bei "      # de
    "le la les et pour du une sur aux est dans par "                            # fr
    "el los las del y para con una por al se "                                  # es
    "il gli di della delle dei degli e per nel alla "                           # it
    "o os um não com pelo pela "                                                # pt
    "het een en van voor met op bij "                                           # nl
    "och för av med till på om att är "                                         # sv
    "og til af ved fra er "                                                     # da, no
    "fyrir við á í um að "                                                      # is
    "și pentru cu în ale din prin privind "                                     # ro
    "w z na dla oraz ir su za u je ja ning").split())                           # pl, lt, hr, sl, cs, et
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"\+\d{1,3}[\d ()./-]{6,}\d|\b(tel|phone|telephone|mobile|fax)\b\.?:?\s*[\d ()+./-]{7,}\d", re.I)
SENT_RE = re.compile(r"(?<=[.!?])\s+")      # the sentence split of common.clip
QUESTIONS = ("Which CPV division covers the main purchase of this notice?",
             "Under which CPV division does this procurement fall?",
             "Which division of the Common Procurement Vocabulary does this tender belong to?",
             "What is the CPV division of this notice's main subject?",
             "Pick the CPV division that matches what the buyer is procuring.")


def check_divisions(raw: str) -> None:
    """CPV_DIVISIONS must equal the official English division names stored with the snapshot."""
    res = json.load(open(os.path.join(raw, "cpv_divisions.sparql.json"), encoding="utf-8"))
    official = {b["c"]["value"].rsplit("/", 1)[1][:2]: b["label"]["value"] for b in res["results"]["bindings"]}
    if official != CPV_DIVISIONS:
        diff = sorted(set(official.items()) ^ set(CPV_DIVISIONS.items()))
        raise SystemExit(f"CPV_DIVISIONS differs from the official list: {diff}")


def notices(raw: str) -> list[dict]:
    out = {}
    for p in sorted(glob.glob(os.path.join(raw, "notices", "*.json"))):
        for n in json.load(open(p, encoding="utf-8")).get("notices", []):
            num = n.get("publication-number")
            if isinstance(num, str) and re.fullmatch(r"\d+-\d{4}", num):
                out.setdefault(num, n)
    return [out[k] for k in sorted(out, key=lambda k: (k.split("-")[1], int(k.split("-")[0])))]


def eng(field) -> str:
    v = field.get("eng") if isinstance(field, dict) else None
    if isinstance(v, list):
        v = v[0] if v else None
    return R.norm_ws(v) if isinstance(v, str) else ""


def division_of(n: dict) -> tuple[str | None, str]:
    codes = [c for c in n.get("classification-cpv") or [] if isinstance(c, str) and re.fullmatch(r"\d{8}", c)]
    if not codes:
        return None, "no CPV code"
    divs = {c[:2] for c in codes}
    if len(divs) > 1:
        return None, "codes in several divisions"
    main = {c[:2] for c in n.get("main-classification-proc") or [] if isinstance(c, str)}
    if main and main != divs:
        return None, "main code of the procedure in another division"
    div = codes[0][:2]
    return (div, "") if div in CPV_DIVISIONS else (None, "division not in the CPV list")


def pub_date(n: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(n.get("publication-date", ""))[:10])
    except ValueError:
        return None


def clean(text: str) -> str:
    keep = []
    for sent in SENT_RE.split(R.norm_ws(text)):
        if SCRUB_RE.search(sent) or CODE_RE.search(sent):
            continue
        keep.append(PHONE_RE.sub("[phone]", EMAIL_RE.sub("[email]", sent)))
    return " ".join(keep)


def words_of(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text.lower())


def not_english(text: str) -> bool:
    ws = words_of(text)
    foreign = sum(w in FOREIGN_WORDS for w in ws)
    return foreign >= 2 and foreign > sum(w in EN_WORDS for w in ws)


def body(rec: dict) -> tuple[str | None, str]:
    """Title and description lines of the item, or (None, why) if the title names a division or the text is too thin or
    not in English."""
    title = rec["title"]
    if len(title) < 10 or R.scrub_hits(title, SCRUB_RE) or CODE_RE.search(title):
        return None, "title names a division, has a CPV-like code or is under 10 characters"
    desc = R.clip(clean(rec["desc"]), TEXT_LIMIT)
    lines = [f"Title: {PHONE_RE.sub('[phone]', EMAIL_RE.sub('[email]', title))}"]
    if desc and re.sub(r"\W+", "", desc.lower()) != re.sub(r"\W+", "", title.lower()):
        lines.append(f"Description: {desc}")
    text = "\n".join(lines)
    plain = title + " " + (desc if len(lines) > 1 else "")
    if R.scrub_hits(text, SCRUB_RE):
        return None, "title names a division, has a CPV-like code or is under 10 characters"
    if not_english(plain):
        return None, "text not in English (more function words of other languages)"
    if sum(len(w) >= 3 for w in words_of(plain)) < 2:
        return None, "fewer than two words"
    return text, ""


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    check_divisions(raw)
    ns = notices(raw)
    dropped: Counter = Counter()
    by_proc: dict[str, dict] = {}
    for n in ns:
        title, desc, date = eng(n.get("title-proc")), eng(n.get("description-proc")), pub_date(n)
        div, why = division_of(n)
        if not title or not desc:
            dropped["no English title or description"] += 1
        elif div is None:
            dropped[why] += 1
        elif date is None:
            dropped["no publication date"] += 1
        else:
            proc = n.get("procedure-identifier") or n["publication-number"]
            rec = {"n": n, "div": div, "title": title, "desc": desc, "date": date, "key": f"ted-{n['publication-number']}"}
            if proc in by_proc:     # notices are read in publication order: the first one of a procedure is kept
                dropped["later notice of a procedure already kept"] += 1
                continue
            by_proc[proc] = rec
    by_text: dict[str, list[dict]] = {}
    unrendered, unrendered_why = 0, Counter()
    for rec in by_proc.values():
        rec["body"], why = body(rec)
        if rec["body"] is None:
            unrendered += 1
            unrendered_why[why] += 1
            continue
        by_text.setdefault(rec["body"].lower(), []).append(rec)
    kept = []
    for _, group in sorted(by_text.items()):
        if len({r["div"] for r in group}) > 1:
            dropped["same item text as a notice of another division"] += len(group)
            continue
        group.sort(key=lambda r: R.hash_order(DOMAIN, r["key"]))
        dropped["same item text as a notice of the same division (one kept)"] += len(group) - 1
        kept.append(group[0])
    count = Counter(r["div"] for r in kept)
    top = {d for d, _ in sorted(count.items(), key=lambda t: (-t[1], t[0]))[:MAX_CLASSES] if count[d] >= R.MIN_CLASS}
    dropped["division outside the 26 most frequent"] = sum(n for d, n in count.items() if d not in top)
    kept = [r for r in kept if r["div"] in top]
    for rec in kept:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        rec["text"] = f"EU public procurement notice (TED, published {rec['date'].isoformat()})\n{rec['body']}\n\n" + \
            rng.choice(QUESTIONS)
        rec["split"] = R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
    kept.sort(key=lambda r: r["key"])
    capped, class_report = R.cap_classes(kept, lambda r: r["div"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["div"] for r in capped}
    labels = [CPV_DIVISIONS[d] for d in CPV_DIVISIONS if d in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=CPV_DIVISIONS[rec["div"]], source="ted",
                             source_id=rec["n"]["publication-number"], snapshot=snapshot, record_date=rec["date"],
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {"api": "https://api.ted.europa.eu/v3/notices/search", "query": fetch.get("query"),
                            "pages": len(fetch["files"]),
                            "files_sha256": {n: f["sha256"] for n, f in sorted(fetch["files"].items())},
                            "cpv_division_names": "cpv_divisions.sparql.json (EU Publications Office SPARQL, CPV 2008)"},
                "label_field": "classification-cpv (main / first code; all codes in one division)",
                "labels": {d: CPV_DIVISIONS[d] for d in CPV_DIVISIONS if d in present},
                "records_read": len(ns), "dropped": dict(sorted(dropped.items())),
                "dropped_unrenderable_or_scrub": unrendered, "unrenderable_reasons": dict(sorted(unrendered_why.items())),
                "kept_before_caps": len(kept), **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://ted.europa.eu/en/notice/-/detail/{row['source_id']}"


_RAW: dict[str, dict[str, dict]] = {}


def _raw_notices(snapshot: str) -> dict[str, dict]:
    """publication number -> the notice as stored, read once per process."""
    if snapshot not in _RAW:
        out: dict[str, dict] = {}
        for p in sorted(glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "notices", "*.json"))):
            for n in json.load(open(p, encoding="utf-8")).get("notices", []):
                out.setdefault(n.get("publication-number"), n)
        _RAW[snapshot] = out
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The division read again from the stored notice by a simpler rule (the procedure's own main code,
    ``main-classification-proc``, else the most common division of all its codes), and whether the item's title line is
    the notice's English procedure title."""
    n = _raw_notices(snapshot).get(row["source_id"])
    if n is None:
        return None, False
    main = n.get("main-classification-proc") or []
    if main:
        div = str(main[0])[:2]
    else:
        divs = Counter(str(c)[:2] for c in n.get("classification-cpv") or [])
        div = divs.most_common(1)[0][0] if divs else None
    title = (n.get("title-proc") or {}).get("eng", "")
    title = re.sub(r"\s+", " ", title if isinstance(title, str) else "").strip()
    text_ok = bool(title) and f"\nTitle: {title}" in row["questions"][0]["instructions"]
    return CPV_DIVISIONS.get(div), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), {len(m['splits'][s]['class_prior'])} "
              f"classes, options {m['splits'][s]['options']}")
    print(f"records read {m['records_read']}, kept before caps {m['kept_before_caps']}, caps {m['caps']}")
    print(f"dropped {m['dropped']}, unrenderable / scrub {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
