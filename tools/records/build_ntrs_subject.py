"""#21 NASA technical reports -> subject category: eval-v5.1 mirror rows (part N, task type ``ntrs_subject_category``).

    python -I tools/records/build_ntrs_subject.py --snapshot 2026-10-27

Records: the STI-submission records of the stored NTRS API pages (publication months 2000-01 to 2026-10), read as data.
* Licence filter (the owner's condition), applied first: only records whose ``distribution`` is PUBLIC and whose
  ``copyright.determinationType`` is GOV_PUBLIC_USE_PERMITTED ("work of the US government, public use permitted") or
  PUBLIC_USE_PERMITTED, with no other licence named in ``copyright.licenseType`` (absent or NO). Every other record is
  dropped and counted in the manifest (``dropped_licence``).
* Label: the structured ``subjectCategories`` field, records with exactly one category only, matched case-insensitively to
  the 76 NASA STI subject categories (``CATEGORIES``; NTRS spells "and" both ways), and of those the MAX_CLASSES (26) most
  frequent categories with >= 20 records, so that a question has at most 26 options as served (and as
  ``common.write_domain`` can store: it writes JSON with sorted keys, which would put AA..AZ before B). Dropped: no
  category, several categories, a name outside the list, and the other categories.
* Record text: the publication year, the title and the abstract (HTML tags removed, e-mail addresses and phone numbers
  masked), cut at a sentence boundary. Not used: authors, affiliations, keywords, report numbers, publication venue,
  meetings, funding numbers. Every sentence that contains a word of ``SCRUB`` (words naming the classification itself,
  every category name, the parts of the names that name a category on their own, the word forms of the one-word names)
  is removed; a record whose title contains one is dropped.
* Group key: the NTRS id. Records with the same title, or the same text, are kept once (none if their categories differ),
  so that a presentation and the paper of one work do not end up in two splits.
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
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ntrs_subject"
TASK = "ntrs_subject_category"
AREA = "retrieval"          # one of many categories
EVAL_FRAC = 0.05            # more than ~3,300 records are kept
TEXT_LIMIT = 1200
MAX_CLASSES = 26
PUBLIC_USE = ("GOV_PUBLIC_USE_PERMITTED", "PUBLIC_USE_PERMITTED")
NO_OTHER_LICENCE = (None, "NO")
# The NASA STI subject categories (NASA Scope and Subject Category Guide), number -> name.
CATEGORIES = {
    "01": "Aeronautics (General)", "02": "Aerodynamics", "03": "Air Transportation and Safety",
    "04": "Aircraft Communications and Navigation", "05": "Aircraft Design, Testing and Performance",
    "06": "Avionics and Aircraft Instrumentation", "07": "Aircraft Propulsion and Power", "08": "Aircraft Stability and Control",
    "09": "Research and Support Facilities (Air)", "12": "Astronautics (General)", "13": "Astrodynamics",
    "14": "Ground Support Systems and Facilities (Space)", "15": "Launch Vehicles and Launch Operations",
    "16": "Space Transportation and Safety", "17": "Space Communications, Spacecraft Communications, Command and Tracking",
    "18": "Spacecraft Design, Testing and Performance", "19": "Spacecraft Instrumentation and Astrionics",
    "20": "Spacecraft Propulsion and Power", "23": "Chemistry and Materials (General)", "24": "Composite Materials",
    "25": "Inorganic, Organic and Physical Chemistry", "26": "Metals and Metallic Materials", "27": "Nonmetallic Materials",
    "28": "Propellants and Fuels", "29": "Space Processing", "31": "Engineering (General)", "32": "Communications and Radar",
    "33": "Electronics and Electrical Engineering", "34": "Fluid Mechanics and Thermodynamics",
    "35": "Instrumentation and Photography", "36": "Lasers and Masers", "37": "Mechanical Engineering",
    "38": "Quality Assurance and Reliability", "39": "Structural Mechanics", "42": "Geosciences (General)",
    "43": "Earth Resources and Remote Sensing", "44": "Energy Production and Conversion", "45": "Environment Pollution",
    "46": "Geophysics", "47": "Meteorology and Climatology", "48": "Oceanography", "51": "Life Sciences (General)",
    "52": "Aerospace Medicine", "53": "Behavioral Sciences", "54": "Man/System Technology and Life Support",
    "55": "Exobiology", "59": "Mathematical and Computer Sciences (General)", "60": "Computer Operations and Hardware",
    "61": "Computer Programming and Software", "62": "Computer Systems", "63": "Cybernetics, Artificial Intelligence and Robotics",
    "64": "Numerical Analysis", "65": "Statistics and Probability", "66": "Systems Analysis and Operations Research",
    "67": "Theoretical Mathematics", "70": "Physics (General)", "71": "Acoustics", "72": "Atomic and Molecular Physics",
    "73": "Nuclear Physics", "74": "Optics", "75": "Plasma Physics", "76": "Solid-State Physics",
    "77": "Physics of Elementary Particles and Fields", "80": "Social and Information Sciences (General)",
    "81": "Administration and Management", "82": "Documentation and Information Science", "83": "Economics and Cost Analysis",
    "84": "Law, Political Science and Space Policy", "85": "Technology Utilization and Surface Transportation",
    "88": "Space Sciences (General)", "89": "Astronomy", "90": "Astrophysics", "91": "Lunar and Planetary Science and Exploration",
    "92": "Solar Physics", "93": "Space Radiation", "99": "General"}
BY_LOWER = {v.lower(): v for v in CATEGORIES.values()}
LABELS = {v: v for v in CATEGORIES.values()}        # the options are the category names themselves
# Words that state the label: the classification itself, every category name (but "General"), the parts of the names that
# name a category on their own, and the word forms of the one-word names. Generic words of the names (space, aircraft,
# spacecraft, design, system, power, software, ...) stay: they are the vocabulary of most records of every category.
NAME_PARTS = ("remote sensing", "earth resources", "life support", "man/system", "fluid mechanics", "thermodynamics",
              "thermodynamic", "electrical engineering", "electronics", "metallic materials", "lunar", "planetary",
              "space sciences", "space science", "meteorology", "climatology", "aerospace medicine", "computer programming",
              "space transportation", "air transportation", "spacecraft propulsion", "aircraft propulsion", "spacecraft design",
              "aircraft design", "mechanical engineering", "composite materials", "instrumentation and photography",
              "communications and radar", "design, testing and performance", "propulsion and power",
              "transportation and safety")
WORD_FORMS = ("astronomical", "astronomer", "astronomers", "astrophysical", "geophysical", "aerodynamic", "aerodynamically",
              "acoustic", "acoustical", "aeroacoustic", "aeroacoustics", "psychoacoustic", "psychoacoustics", "aeronautical",
              "meteorological", "climatological", "metals", "metallic", "composite", "composites",
              # telling words of "Man/System Technology and Life Support" that name it: (portable / environmental control
              # and) life support system, human-systems (the current name of man/system technology)
              "plss", "eclss", "human-systems", "human systems")
SCRUB = (("subject category", "subject categories", "sti category", "nasa sti", "category", "categories", "categorized",
          "categorised") + tuple(sorted({v.lower() for v in CATEGORIES.values() if v != "General"})) + NAME_PARTS
         + WORD_FORMS)
SCRUB_RE = R.scrub_pattern(SCRUB)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"\+\d{1,3}[\d ()./-]{6,}\d|\b(tel|phone|telephone|mobile|fax)\b\.?:?\s*[\d ()+./-]{7,}\d", re.I)
SENT_RE = re.compile(r"(?<=[.!?])\s+")      # the sentence split of common.clip
QUESTIONS = ("Which NASA subject category does this report belong to?",
             "Under which NASA STI subject category is this report catalogued?",
             "What is the NASA subject category of this report?",
             "Which subject category did the NASA Technical Reports Server assign to this report?",
             "Pick the NASA subject category that covers this report.")


def plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return R.norm_ws(html.unescape(text))


def records(raw: str) -> list[dict]:
    out = {}
    for p in sorted(glob.glob(os.path.join(raw, "pages", "*.json"))):
        for r in json.load(open(p, encoding="utf-8")).get("results") or []:
            rid = str(r.get("id", ""))
            if rid.isdigit():
                out.setdefault(rid, r)
    return [out[k] for k in sorted(out)]


def licence_ok(r: dict) -> bool:
    cr = r.get("copyright") or {}
    return (r.get("distribution") == "PUBLIC" and cr.get("determinationType") in PUBLIC_USE
            and cr.get("licenseType") in NO_OTHER_LICENCE)


def pub_date(r: dict) -> dt.date | None:
    dates = sorted(p.get("publicationDate", "")[:10] for p in r.get("publications") or [] if p.get("publicationDate"))
    try:
        return dt.date.fromisoformat(dates[0]) if dates else None
    except ValueError:
        return None


def clean(text: str) -> str:
    keep = []
    for sent in SENT_RE.split(plain(text)):
        if SCRUB_RE.search(sent):
            continue
        keep.append(PHONE_RE.sub("[phone]", EMAIL_RE.sub("[email]", sent)))
    return " ".join(keep)


def render(rec: dict, rng: random.Random) -> str | None:
    title = plain(rec["r"].get("title", ""))
    if not title or R.scrub_hits(title, SCRUB_RE):
        return None
    abstract = R.clip(clean(rec["r"].get("abstract", "")), TEXT_LIMIT)
    if len(abstract) < 80:
        return None
    record = f"NASA technical report (published {rec['date'].year})\nTitle: {title}\nAbstract: {abstract}"
    if R.scrub_hits(record, SCRUB_RE):
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs = records(raw)
    dropped_licence: Counter = Counter()
    dropped: Counter = Counter()
    cand = []
    for r in recs:
        cr = r.get("copyright") or {}
        if not licence_ok(r):
            dropped_licence[f"distribution {r.get('distribution')}, determination {cr.get('determinationType')}, "
                            f"licence {cr.get('licenseType')}"] += 1
            continue
        cats = r.get("subjectCategories") or []
        date = pub_date(r)
        if len(cats) != 1:
            dropped["no subject category" if not cats else "several subject categories"] += 1
        elif cats[0].lower() not in BY_LOWER:
            dropped["category not in the NASA STI list"] += 1
        elif not r.get("abstract") or not r.get("title"):
            dropped["no abstract or title"] += 1
        elif date is None:
            dropped["no publication date"] += 1
        else:
            cand.append({"r": r, "cat": BY_LOWER[cats[0].lower()], "key": f"ntrs-{r['id']}", "date": date})
    rendered, unrendered = [], 0
    for rec in cand:
        rec["text"] = render(rec, random.Random(f"{DOMAIN}|{rec['key']}"))
        if rec["text"] is None:
            unrendered += 1
        else:
            rendered.append(rec)
    # one record per normalised title and per normalised text (a work's presentation, abstract and paper share them)
    groups: dict[str, list[dict]] = {}
    for rec in rendered:
        groups.setdefault("t|" + re.sub(r"\W+", " ", plain(rec["r"]["title"]).lower()).strip(), []).append(rec)
    kept = []
    for _, group in sorted(groups.items()):
        if len({r["cat"] for r in group}) > 1:
            dropped["same title as a record of another category"] += len(group)
            continue
        group.sort(key=lambda r: R.hash_order(DOMAIN, r["key"]))
        dropped["same title as a record of the same category (one kept)"] += len(group) - 1
        kept.append(group[0])
    by_text: dict[str, list[dict]] = {}
    for rec in kept:
        by_text.setdefault(R.norm_ws(rec["text"].rsplit("\n\n", 1)[0].split("\nAbstract: ", 1)[1]).lower(), []).append(rec)
    kept = []
    for _, group in sorted(by_text.items()):
        if len({r["cat"] for r in group}) > 1:
            dropped["same abstract as a record of another category"] += len(group)
            continue
        group.sort(key=lambda r: R.hash_order(DOMAIN, r["key"]))
        dropped["same abstract as a record of the same category (one kept)"] += len(group) - 1
        kept.append(group[0])
    count = Counter(r["cat"] for r in kept)
    top = {c for c, _ in sorted(count.items(), key=lambda t: (-t[1], t[0]))[:MAX_CLASSES] if count[c] >= R.MIN_CLASS}
    dropped["category outside the 26 most frequent"] = sum(n for c, n in count.items() if c not in top)
    kept = [r for r in kept if r["cat"] in top]
    for rec in kept:
        rec["split"] = R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
    kept.sort(key=lambda r: r["key"])
    capped, class_report = R.cap_classes(kept, lambda r: r["cat"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["cat"] for r in capped}
    labels = [v for v in CATEGORIES.values() if v in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=rec["cat"], source="ntrs",
                             source_id=str(rec["r"]["id"]), snapshot=snapshot, record_date=rec["date"],
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "licence_filter": {"distribution": "PUBLIC", "copyright.determinationType": list(PUBLIC_USE),
                                   "copyright.licenseType": "absent or NO"},
                "sources": {"api": "https://ntrs.nasa.gov/api/citations/search", "pages": len(fetch["files"]),
                            "sampling": fetch.get("sampling"),
                            "files_sha256": {n: f["sha256"] for n, f in sorted(fetch["files"].items())}},
                "label_field": "subjectCategories (exactly one)", "labels": {v: v for v in labels},
                "records_read": len(recs), "dropped_licence_total": sum(dropped_licence.values()),
                "dropped_licence": dict(sorted(dropped_licence.items(), key=lambda t: -t[1])),
                "dropped": dict(sorted(dropped.items())), "dropped_unrenderable_or_scrub": unrendered,
                "kept_before_caps": len(kept), **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://ntrs.nasa.gov/citations/{row['source_id']}"


_RAW: dict[str, dict[str, dict]] = {}


def _raw_records(snapshot: str) -> dict[str, dict]:
    """NTRS id -> the record as stored, read once per process."""
    if snapshot not in _RAW:
        out: dict[str, dict] = {}
        for p in sorted(glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "pages", "*.json"))):
            for r in json.load(open(p, encoding="utf-8")).get("results") or []:
                out.setdefault(str(r.get("id")), r)
        _RAW[snapshot] = out
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The category read again from the stored record (its subjectCategories list must hold exactly one name, compared with
    the option texts ignoring case and the and/And spelling), the licence fields checked again, and whether the item's
    title line is the record's own title."""
    r = _raw_records(snapshot).get(row["source_id"])
    if r is None:
        return None, False
    cats = r.get("subjectCategories") or []
    cr = r.get("copyright") or {}
    if len(cats) != 1 or r.get("distribution") != "PUBLIC" or "PUBLIC_USE_PERMITTED" not in str(cr.get("determinationType")):
        return None, False
    opts = {v.lower().replace(" and ", " & "): v for v in row["questions"][0]["criteria"].values()}
    label = opts.get(cats[0].lower().replace(" and ", " & "))
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(r.get("title", "")))).strip()
    text_ok = f"\nTitle: {title}\n" in row["questions"][0]["instructions"]
    return label, text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), {len(m['splits'][s]['class_prior'])} "
              f"classes, options {m['splits'][s]['options']}")
    print(f"records read {m['records_read']}, dropped for licence {m['dropped_licence_total']}, kept before caps "
          f"{m['kept_before_caps']}, caps {m['caps']}")
    print(f"dropped {m['dropped']}, unrenderable / scrub {m['dropped_unrenderable_or_scrub']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
