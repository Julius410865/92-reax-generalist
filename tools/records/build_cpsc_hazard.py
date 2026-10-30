"""#13 Consumer-product recalls -> hazard type: eval-v5.1 mirror rows (part N, task type ``cpsc_hazard_type``).

    python -I tools/records/build_cpsc_hazard.py --snapshot 2026-10-27

Records: the CPSC recall list of the SaferProducts.gov Recalls Retrieval Web Services (one unfiltered JSON response), read
from the raw file as data.
* Label. The API's structured hazard-type fields ``Hazards[].HazardType`` / ``HazardTypeID`` are empty in every hazard
  object (9,931 of them on 2026-10-27; the programmer's guide v1.3 shows them empty too), so they cannot be used.
  ``Hazards[].Name`` holds, for the recalls of 1973-1999 (and three later ones), a term of CPSC's hazard-type code list
  ("Choking", "Fire & Fire-Related Burn", "Electrocution/Electric Shock", ... 20 terms, ``HAZARD_TYPES``); for the other
  recalls it holds the hazard paragraph of the notice (prose, 7,700 distinct values). The label is taken only when a
  recall has exactly one hazard entry whose ``Name`` is exactly a code-list term; prose is never parsed for a label, so
  those recalls are not used, and recalls with several hazard entries (40) or none are dropped. Classes under 20
  records are dropped (Carbon Monoxide, Internal Injury, Drowning, Entanglement, Amputation, Aspiration).
* Record text: title, product names, product types (CPSC's product category), model, country of manufacture, and the
  recall notice (``Description``, the press release) without its header (everything up to the "WASHINGTON, D.C." dateline:
  release number, media contact, headline), cut at a sentence boundary. The notice states the hazard; every sentence that
  contains a word of ``SCRUB`` is removed: the code-list terms with their word forms and synonyms (fire, flame, ignite,
  overheat, smoke, shock, electrocution, cut, sharp, fall, tip over, poison, toxic, child-resistant, entrap, strangle,
  drawstring, lead, collapse, explode, burst, suffocate, smother, accident, crash, swallow, small parts, ...) and the
  generic hazard and outcome words (hazard, risk, danger, injury, death, harm, fracture ...). What remains is the
  product description, where and when it was sold and the remedy. A record whose title or product name contains a SCRUB
  word is dropped (a product type or model line with one is left out). Privacy: the header with the media contact is cut,
  phone numbers, e-mail addresses and names after a title (Dr. / Mr. / Mrs. / Ms.) are masked, and the sentences that
  give a phone number or e-mail address (where company contacts are named) are removed; companies and public officials
  acting in office (CPSC's chairman) stay.
* Group key: the recall number without its letter suffix (97177, 99120a / 99120b), so the parts of one recall release
  stay in one split.
* No fresh rows: every labelled recall is from 1973-2010.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "cpsc_hazard"
TASK = "cpsc_hazard_type"
AREA = "retrieval"          # one of many categories, as the dev set's nhtsa_recall_component
EVAL_FRAC = 0.10            # a small domain (about 1,200 kept records): about 10 % test and 10 % select
TEXT_LIMIT = 1100
# The class cap draws its records in a hash order of its own (with the take's order a capped class keeps the front of
# the take order and the take of at most 3,000 / 150 refills it, undoing the cap).
CAP_ORDER = f"{DOMAIN}|cap"
# CPSC's hazard-type code list as it appears in Hazards[].Name -> option text (the code-list wording, readable).
HAZARD_TYPES = {"Choking": "Choking",
                "Fire & Fire-Related Burn": "Fire & fire-related burn",
                "Electrocution/Electric Shock": "Electrocution / electric shock",
                "Laceration": "Laceration",
                "Fall": "Fall",
                "Poisoning": "Poisoning",
                "Entrapment": "Entrapment",
                "Strangulation": "Strangulation",
                "Lead": "Lead (lead poisoning)",
                "Collapse": "Collapse",
                "Burn - Not Fire-Related": "Burn, not fire-related",
                "Explosion/Projectiles": "Explosion / projectiles",
                "Suffocation": "Suffocation",
                "Vehicle Accident": "Vehicle accident",
                "Carbon Monoxide (CO)": "Carbon monoxide (CO) poisoning",
                "Internal Injury": "Internal injury",
                "Drowning": "Drowning",
                "Entanglement": "Entanglement",
                "Amputation": "Amputation",
                "Aspiration": "Aspiration"}
SCRUB = (
    # the code-list terms and their word forms
    "choking", "choke", "chokes", "choked", "fire", "fires", "fire-related", "burn", "burns", "burned", "burnt",
    "burning", "electrocution", "electrocutions", "electrocute", "electrocuted", "electrocuting", "shock", "shocks",
    "shocked", "electric shock", "laceration", "lacerations", "lacerate", "lacerated", "cut", "cuts", "fall", "falls",
    "fell", "fallen", "falling", "poisoning", "poisonings", "poison", "poisons", "poisoned", "poisonous", "entrapment",
    "entrap", "entraps", "entrapped", "trap", "traps", "trapped", "trapping", "strangulation", "strangle", "strangles",
    "strangled", "strangling", "strangulate", "strangulated", "lead", "leaded", "collapse", "collapses", "collapsed",
    "collapsing", "explosion", "explosions", "explode", "explodes", "exploded", "exploding", "explosive",
    "explosives", "projectile", "projectiles", "suffocation", "suffocate", "suffocates", "suffocated", "suffocating",
    "accident", "accidents", "accidental", "accidentally", "carbon monoxide", "drowning", "drown", "drowns",
    "drowned", "entanglement", "entangle", "entangled", "amputation", "amputations", "amputate", "amputated",
    "aspiration", "aspirate", "aspirated", "internal injury", "internal injuries",
    # synonyms and the direct mechanism words of the terms
    "flame", "flames", "flaming", "flammable", "flammability", "inflammable", "nonflammable", "ignite", "ignites",
    "ignited", "igniting", "ignition", "combustion", "combustible", "smoke", "smoking", "smoldering", "smolder",
    "scald", "scalds", "scalded", "scalding", "overheat", "overheats", "overheated", "overheating", "melt", "melts",
    "melted", "spark", "sparks", "sparking", "short circuit", "short-circuit", "short circuits", "shorting",
    "electrical shock", "sharp", "puncture", "punctures", "punctured", "tip over", "tips over", "tipped over",
    "tip-over", "tipping", "topple", "topples", "toppled", "toxic", "toxicity", "child-resistant", "child resistant",
    "swallow", "swallows", "swallowed", "swallowing", "ingest", "ingests", "ingested", "ingestion", "inhale",
    "inhaled", "inhalation", "small parts", "small part", "airway", "airways", "breathe", "breathing", "asphyxia",
    "asphyxiation", "asphyxiate", "asphyxiated", "smother", "smothering", "smothered", "burst", "bursts", "bursting",
    "rupture", "ruptures", "ruptured", "shatter", "shatters", "shattered", "drawstring", "drawstrings", "caught",
    "wedged", "loss of control", "lose control", "crash", "crashes", "crashed",
    # generic hazard and outcome words
    "hazard", "hazards", "hazardous", "risk", "risks", "danger", "dangers", "dangerous", "injury", "injuries",
    "injured", "injure", "injuring", "death", "deaths", "died", "dies", "killed", "fatal", "fatality", "fatalities",
    "harm", "harmful", "unsafe", "fracture", "fractures", "fractured", "bruise", "bruises", "bruising", "wound",
    "wounds", "stitches", "concussion")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("Which hazard type did CPSC record for this recall?",
             "What hazard led to this recall?",
             "Which hazard is this recall about?",
             "Which of these hazards prompted the recall?",
             "Under which hazard type is this recall listed?")

# The dateline that opens the body of a CPSC press release ("WASHINGTON, D.C. -", "WASHINGTON, D.C. (July 13) --",
# "WASHINGTON --", "WASHINGTON, D.C. In cooperation ...", "Washington, D.C. -"): upper case or followed by a dash, unlike
# the "Washington, DC 20207" address of the header.
DATELINE_RE = re.compile(r"(?:\bWASHINGTON\b\s*,?\s*(?:D\.?\s*C\.?)?\s*(?:\([^)]{0,40}\))?\s*(?:-+|–|—)?"
                         r"|\bWashington\s*,?\s*D\.?\s*C\.?\s*(?:\([^)]{0,40}\))?\s*(?:-+|–|—))\s*")
# Without a dateline: the header runs to "Release # nn-nnn", then a few labelled fields may follow.
RELEASE_RE = re.compile(r"^.{0,800}?Release\s*#\s*[\w-]+\s*", re.S)
HEADER_FIELD_RE = re.compile(r"^(?:Company Phone Numbers?:\s*[^A-Z]*|CPSC Consumer Hotline:\s*[^A-Z]*|"
                             r"CPSC Media Contacts?:\s*[^,(]+,?\s*[^A-Z]*|Note:[^.]*\.\s*|Originally issued[^A-Z]*|"
                             r"(?:Last\s+)?Revised [A-Z][a-z]+\.? \d{1,2}, \d{4}\s*)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\(\d{3}\)\s?\d{3}[-. ]\d{4}(?!\d)"                                   # (301) 504-7052
                      r"|(?<![\w-])(?:\+?1[-. ]?|[l1]-)?\d{3}[-. /]\d{3}[-. ]\d{4}(?!\d)")    # 1-800-638-2772, 800/638-2772
TITLED_NAME_RE = re.compile(r"\b(Dr|Mr|Mrs|Ms|Miss)(\.?\s+)"
                            r"([A-Z][A-Za-z'-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z][A-Za-z'-]*){0,2})")
CONTACT_RE = re.compile(r"\[(?:phone|email)\]|\b\d{3}-[A-Z]{4}\b")      # masked numbers, "800-638-CPSC"


def mask(text: str, brands: tuple[str, ...] = ()) -> str:
    """E-mail addresses and phone numbers -> [email] / [phone]; a name after Dr. / Mr. / Mrs. / Ms. -> [name] (not when
    "Dr" is a street suffix, i.e. a house number comes shortly before it, nor a brand of the record's title or product
    names: "Mr. Coffee", "Little Miss ...")."""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)

    def name(m: re.Match) -> str:
        before = text[max(0, m.start() - 40):m.start()].split()[-3:]
        if m.group(1) == "Dr" and any(re.search(r"\d", w) for w in before):
            return m.group(0)
        first = re.match(r"[A-Za-z-]+", m.group(3)).group(0)        # "Mr. Coffee's" -> "Mr. Coffee"
        if any(f"{m.group(1)}{m.group(2)}{first}" in b for b in brands):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}[name]"
    return TITLED_NAME_RE.sub(name, text)


def notice(desc: str) -> str:
    """The press release without its header (release number, date, media contact with name and phone, headline): the
    text after the "WASHINGTON, D.C." dateline if one opens the body (within the first 1,500 characters), else the text
    after "Release # nn-nnn" and the labelled fields that follow it (company phone, CPSC hotline, media contact, note)."""
    desc = R.norm_ws(desc)
    for m in DATELINE_RE.finditer(desc[:1500]):
        if not desc[m.end():m.end() + 1].isdigit():         # not an address: "WASHINGTON, DC 20207"
            return desc[m.end():]
    m = RELEASE_RE.match(desc)
    if not m:
        return desc
    desc = desc[m.end():]
    while True:
        f = HEADER_FIELD_RE.match(desc)
        if not f or not f.group(0):
            return desc
        desc = desc[f.end():]


def no_contacts(text: str) -> str:
    """The text without the sentences that give a phone number or an e-mail address: the "for more information call
    <firm or person> at ..." sentences, where the names of company contacts and spokespeople stand."""
    return R.drop_sentences(text, CONTACT_RE)


def label_of(rec: dict) -> str | None:
    hz = rec.get("Hazards") or []
    if len(hz) != 1:
        return None
    return (hz[0].get("Name") or "").strip() if (hz[0].get("Name") or "").strip() in HAZARD_TYPES else None


def uniq(xs) -> list[str]:
    out = []
    for x in xs:
        x = R.norm_ws(x)
        if x and x not in out:
            out.append(x)
    return out


def render_record(rec: dict) -> str | None:
    title = R.norm_ws(rec.get("Title"))
    prods = rec.get("Products") or []
    names = uniq(p.get("Name") for p in prods)
    types = uniq(p.get("Type") for p in prods)
    models = uniq(p.get("Model") for p in prods)
    countries = uniq(c.get("Country") for c in rec.get("ManufacturerCountries") or [])
    if not title or not names or R.scrub_hits(title, SCRUB_RE) or any(R.scrub_hits(n, SCRUB_RE) for n in names):
        return None
    brands = (title, *names)
    body = R.clip(no_contacts(mask(R.drop_sentences(notice(rec.get("Description") or ""), SCRUB_RE), brands)),
                  TEXT_LIMIT)
    if not body:
        return None
    day = (rec.get("RecallDate") or "")[:10]
    lines = [f"Consumer product recall (CPSC{', announced ' + day if re.fullmatch(r'\d{4}-\d\d-\d\d', day) else ''})",
             f"Title: {title}",
             f"Product{'s' if len(names) > 1 else ''}: {'; '.join(names)}"]
    for label, vals in (("Product type", types), ("Model", models), ("Manufactured in", countries)):
        vals = [mask(v, brands) for v in vals if not R.scrub_hits(v, SCRUB_RE)]
        if vals:
            lines.append(f"{label}: {'; '.join(vals)}")
    lines.append(f"Recall notice: {body}")
    record = "\n".join(lines)
    if R.scrub_hits(record, SCRUB_RE):
        return None
    return record


def group_of(number: str) -> str:
    return re.sub(r"[A-Za-z]+$", "", number) or number


def records(raw: str) -> tuple[list[dict], dict]:
    data = json.load(open(os.path.join(raw, "recalls.json"), encoding="utf-8"))
    stats = {"records_read": len(data), "with_code_list_hazard": 0, "dropped_several_hazards": 0,
             "dropped_unrenderable_or_scrub": 0}
    out = []
    for rec in sorted(data, key=lambda r: str(r.get("RecallNumber"))):
        hz = rec.get("Hazards") or []
        terms = [(h.get("Name") or "").strip() for h in hz if (h.get("Name") or "").strip() in HAZARD_TYPES]
        if not terms:
            continue
        stats["with_code_list_hazard"] += 1
        label = label_of(rec)
        if label is None:
            stats["dropped_several_hazards"] += 1
            continue
        record = render_record(rec)
        if record is None:
            stats["dropped_unrenderable_or_scrub"] += 1
            continue
        num = str(rec["RecallNumber"])
        try:
            day = dt.date.fromisoformat((rec.get("RecallDate") or "")[:10])
        except ValueError:
            day = None
        out.append({"num": num, "group": group_of(num), "status": label, "date": day, "record": record,
                    "key": f"recall-{num}"})
    return out, stats


def dedupe(recs: list[dict]) -> tuple[list[dict], int, int]:
    """One record per distinct text: kept once if all copies agree on the hazard, dropped if they conflict."""
    by: dict[str, list[dict]] = {}
    for r in sorted(recs, key=lambda r: r["key"]):
        by.setdefault(R.norm_ws(r["record"]).lower(), []).append(r)
    out, dup, conflict = [], 0, 0
    for group in by.values():
        if len({r["status"] for r in group}) > 1:
            conflict += len(group)
            continue
        out.append(group[0])
        dup += len(group) - 1
    return sorted(out, key=lambda r: r["key"]), dup, conflict


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, stats = records(raw)
    kept, dup, conflict = dedupe(recs)
    for rec in kept:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        rec["text"] = rec["record"] + "\n\n" + rng.choice(QUESTIONS)
        rec["split"] = R.split_of(DOMAIN, rec["group"], EVAL_FRAC)
    capped, class_report = R.cap_classes(kept, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["status"] for r in capped}
    labels = [HAZARD_TYPES[s] for s in HAZARD_TYPES if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=HAZARD_TYPES[rec["status"]], source=DOMAIN,
                             source_id=rec["num"], snapshot=snapshot, record_date=rec["date"], shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "Hazards[].Name when it is exactly a term of CPSC's hazard-type code list "
                               "(Hazards[].HazardType / HazardTypeID are empty in every record)",
                "labels": {k: HAZARD_TYPES[k] for k in HAZARD_TYPES if k in present},
                "group_key": "RecallNumber without its letter suffix", "eval_frac": EVAL_FRAC, **stats,
                "dropped_duplicate_text": dup, "dropped_conflicting_text": conflict, "records_kept": len(kept),
                **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

_RAW: dict[str, str] = {}


def _raw_text(snapshot: str) -> str:
    """The raw response as text, read once per process."""
    if snapshot not in _RAW:
        _RAW[snapshot] = open(os.path.join(R.RAW, DOMAIN, snapshot, "recalls.json"), encoding="utf-8").read()
    return _RAW[snapshot]


def _raw_object(snapshot: str, number: str) -> str | None:
    """The raw JSON text of the recall with this number: from its "RecallNumber" to the next recall's "RecallID"."""
    txt = _raw_text(snapshot)
    m = re.search(r'"RecallNumber"\s*:\s*"' + re.escape(number) + '"', txt)
    if not m:
        return None
    nxt = txt.find('"RecallID"', m.end())
    return txt[m.end():nxt if nxt > 0 else len(txt)]


def _field(obj: str, name: str) -> str | None:
    m = re.search(r'"' + name + r'"\s*:\s*"((?:\\.|[^"\\])*)"', obj)
    return json.loads(f'"{m.group(1)}"') if m else None


def source_url(row: dict, snapshot: str) -> str:
    """The recall's page on cpsc.gov (the record's own URL field)."""
    obj = _raw_object(snapshot, row["source_id"])
    return (_field(obj, "URL") if obj else None) or "https://www.saferproducts.gov/RestWebServices/Recall?format=json" \
        f"&RecallNumber={row['source_id']}"


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The hazard read again from the raw response by a text scan (the recall's "Hazards" array, not the builder's JSON
    walk): the code-list term if the array has exactly one "Name"; and whether the item's title line is the record's
    own title."""
    obj = _raw_object(snapshot, row["source_id"])
    if obj is None:
        return None, False
    m = re.search(r'"Hazards"\s*:\s*\[(.*?)\]', obj, re.S)
    names = [json.loads(f'"{n}"').strip() for n in re.findall(r'"Name"\s*:\s*"((?:\\.|[^"\\])*)"', m.group(1))] if m else []
    title = _field(obj, "Title") or ""
    text_ok = f"\nTitle: {R.norm_ws(title)}\n" in row["questions"][0]["instructions"]
    return (HAZARD_TYPES.get(names[0]) if len(names) == 1 else None), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), classes {m['splits'][s]['class_prior']}, "
              f"gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']}, with a code-list hazard {m['with_code_list_hazard']}, dropped: several "
          f"hazards {m['dropped_several_hazards']}, scrub / no text {m['dropped_unrenderable_or_scrub']}, duplicate text "
          f"{m['dropped_duplicate_text']}, conflicting text {m['dropped_conflicting_text']}; kept {m['records_kept']}; "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
