"""#11 NTSB aviation accidents -> highest injury severity: eval-v5.1 mirror rows (part N, task type ``ntsb_injury_severity``).

    python -I tools/records/build_ntsb_injury.py --snapshot 2026-10-27

Records: the NTSB aviation database (avall.zip, 2008 to present, plus the weekly update files created after it, applied in
order: for every table, an event's rows in an update replace its earlier rows). The Access files are read as data only:
each .mdb is copied out of its verified zip into a temporary directory and its tables are exported to CSV with mdbtools'
``mdb-export``; nothing in them is executed.
* Kept: accidents (``ev_type`` ACC) investigated by the NTSB (``invest_agy`` N) with one aircraft and one narrative row,
  whose final report is out (``NTSB_Admin.rec_stat`` B and a probable-cause statement present; preliminary and factual-only
  records are still in progress and their injury level can still change).
* Label: ``events.ev_highest_injury`` (FATL / SERS / MINR / NONE), kept only when it agrees with the event's injury totals
  (``inj_tot_f`` / ``_s`` / ``_m``) and with the per-person ``injury`` table (the conflicts are almost all injuries on the
  ground, counted in the highest-injury field but not in the totals). Missing (UNK, blank) or conflicting labels are dropped.
* Record text: date, place, aircraft category and make / model (category only when the make may be a person's name, see
  Privacy), operating rule and type of flight, the defining event's phase of flight, basic weather and
  light, and the factual narrative (``narr_accp``; reports without one have a single ``narr_accf`` narrative), cut to its
  history-of-flight part (the later sections of long field reports, such as personnel, medical and pathological
  information, are left out with their headers) and at a sentence boundary. Not used: the injury and damage fields, the
  probable cause, the NTSB number (its investigation-class letters, e.g. FA, track severity), owner and operator fields.
  Every sentence with a word of ``SCRUB`` is removed; a record left with too little narrative is dropped.
* Privacy: personal names after a title (Mr., Ms., Dr. ...), the words of a "make" that may be a private owner-builder's
  name (amateur-built aircraft, and makes seen on fewer than 5 aircraft with no company word; such makes are also left out
  of the record's aircraft line), registration marks, e-mail addresses and phone numbers are masked in the narrative.
* Group key: the event id (one record per event).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ntsb_injury"
TASK = "ntsb_injury_severity"
AREA = "language"           # a severity domain
EVAL_FRAC = 0.05            # over 20,000 kept records
TEXT_LIMIT = 1000           # narrative characters
MIN_NARRATIVE = 150
TABLES = ("events", "aircraft", "NTSB_Admin", "narratives", "injury", "Events_Sequence", "states")
FILE_URL = "https://data.ntsb.gov/avdata/FileDirectory/DownloadFile?fileID={}"
LEVELS = ("FATL", "SERS", "MINR", "NONE")
LABELS = {"FATL": "Fatal: at least one person died",
          "SERS": "Serious: the worst injury was serious (such as a fracture or over 48 hours in hospital), nobody died",
          "MINR": "Minor: the worst injury was minor",
          "NONE": "None: nobody was injured"}
SCRUB = (
    # death
    "fatal", "fatally", "fatalities", "fatality", "killed", "killing", "died", "die", "dies", "dying", "death", "deaths",
    "dead", "deceased", "decedent", "decedents", "perished", "drowned", "drowning", "drown", "lost his life",
    "lost her life", "lost their lives", "lifeless", "alive", "survive", "survived", "survives", "surviving", "survivor",
    "survivors", "survivable", "nonsurvivable", "non-survivable", "unsurvivable",
    # injury
    "injure", "injured", "injures", "injuries", "injury", "injuring", "uninjured", "noninjured", "non-injured", "hurt",
    "unhurt", "unharmed", "harmed", "wounded", "wound", "wounds", "serious", "seriously", "minor", "bruise", "bruises",
    "bruised", "bruising", "laceration", "lacerations", "lacerated", "contusion", "contusions", "abrasion", "abrasions",
    "concussion", "concussions", "sprain", "sprains", "sprained", "fractured his", "fractured her", "fractured their",
    "fracturing his", "fracturing her", "broke his", "broke her", "broken bone", "broken bones", "broken leg",
    "broken legs", "broken arm", "broken arms", "broken back", "broken neck", "broken ribs", "broken hip", "broken nose",
    "broken foot", "ankle", "ankles", "wrist", "wrists", "pelvis", "pelvic", "spine", "spinal", "vertebra", "vertebrae",
    "vertebral", "femur", "tibia", "fibula", "clavicle", "collarbone", "sternum", "skull", "jaw", "pain", "painful",
    "burns", "paralyzed", "paralysis", "amputated", "amputation", "coma", "unconscious", "unconsciousness",
    "unresponsive", "consciousness", "diagnosed", "stitches", "sutures",
    # medical care
    "hospital", "hospitals", "hospitalized", "hospitalised", "hospitalization", "medical center", "medical facility",
    "medical attention", "medical care", "medical assistance", "medical treatment", "treated", "trauma", "traumatic",
    "emergency room", "intensive care", "icu", "surgery", "surgeries", "surgical", "critical condition",
    "stable condition", "life-threatening", "life threatening", "ambulance", "ambulances", "paramedic", "paramedics",
    "emt", "emts", "airlifted", "life flight", "lifeflight", "medevac", "medivac", "cpr", "resuscitate", "resuscitated",
    "resuscitation", "first aid",
    # death investigation and aftermath
    "medical examiner", "coroner", "autopsy", "autopsies", "toxicology", "toxicological", "postmortem", "post-mortem",
    "pathology", "pathological", "pathologist", "forensic", "cause of death", "blunt force", "victim", "victims", "body",
    "bodies", "remains", "next of kin", "widow", "widower", "funeral", "obituary", "condolences", "rescue", "rescued",
    "rescuers", "extricate", "extricated", "extrication")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("What was the highest level of injury in this accident?",
             "How severe was the worst injury that anyone suffered in this accident?",
             "Which injury severity did this accident reach at its worst?",
             "Considering everyone involved, what was the worst injury outcome of this accident?",
             "What was the most severe injury recorded for this accident?")

CATEGORY = {"AIR": "Airplane", "HELI": "Helicopter", "GLI": "Glider", "BALL": "Balloon", "GYRO": "Gyroplane",
            "WSFT": "Weight-shift-control aircraft", "PPAR": "Powered parachute", "ULTR": "Ultralight",
            "PLFT": "Powered-lift aircraft", "BLIM": "Blimp", "RCKT": "Rocket"}
FAR_PART = {"091": "Part 91 (general aviation)", "091K": "Part 91 subpart K (fractional ownership)",
            "091F": "Part 91 special flight operations", "103": "Part 103 (ultralight vehicle)",
            "107": "Part 107 (small unmanned aircraft)", "121": "Part 121 (air carrier)",
            "125": "Part 125 (large aircraft, 20 or more seats)", "129": "Part 129 (foreign air carrier)",
            "133": "Part 133 (rotorcraft external load)", "135": "Part 135 (commuter and on-demand)",
            "137": "Part 137 (agricultural aircraft)", "PUBU": "public aircraft operation",
            "PUBF": "public aircraft operation (federal)", "PUBS": "public aircraft operation (state)",
            "PUBL": "public aircraft operation (local)", "ARMF": "armed forces"}
TYPE_FLY = {"PERS": "personal", "INST": "instructional", "AAPL": "aerial application", "BUS": "business",
            "POSI": "positioning", "OWRK": "other work use", "AOBV": "aerial observation", "FLTS": "flight test",
            "FERY": "ferry", "ASHO": "air race or air show", "SKYD": "skydiving", "EXEC": "executive / corporate",
            "EXLD": "external load", "PUBF": "public use (federal)", "PUBL": "public use (local)",
            "PUBS": "public use (state)", "PUBU": "public use", "BANT": "banner tow", "GLDT": "glider tow",
            "FIRF": "fire fighting", "ADRP": "air drop", "AIRM": "air medical", "INDS": "industrial / special",
            "OTH": "other"}
PHASE = {"100": "Prior to flight", "150": "Standing", "151": "Standing, engine(s) not operating",
         "152": "Standing, engine(s) start-up", "153": "Standing, engine(s) operating", "154": "Standing, engine(s) shutdown",
         "200": "Pushback / towing", "201": "Pushback / towing, engine not operating",
         "202": "Pushback / towing, engine start-up", "203": "Pushback / towing, engine operating", "250": "Taxi",
         "251": "Taxi to runway", "252": "Taxi into takeoff position", "253": "Taxi from runway", "300": "Takeoff",
         "301": "Takeoff, rejected takeoff", "350": "Initial climb", "400": "Enroute", "401": "Enroute, climb to cruise",
         "402": "Enroute, cruise", "403": "Enroute, change of cruise level", "404": "Enroute, descent",
         "405": "Enroute, holding (IFR)", "450": "Maneuvering", "451": "Maneuvering, aerobatics",
         "452": "Maneuvering, low-altitude flying", "453": "Maneuvering, hover", "500": "Approach",
         "501": "Approach, IFR initial approach", "502": "Approach, IFR final approach", "503": "Approach, circling (IFR)",
         "504": "Approach, IFR missed approach", "505": "Approach, VFR pattern crosswind",
         "506": "Approach, VFR pattern downwind", "507": "Approach, VFR pattern base", "508": "Approach, VFR pattern final",
         "509": "Approach, VFR go-around", "550": "Landing", "551": "Landing, flare / touchdown",
         "552": "Landing, landing roll", "553": "Landing, aborted after touchdown", "600": "Emergency descent",
         "601": "Autorotation", "650": "Uncontrolled descent", "700": "Post-impact", "750": "After landing", "800": "Other"}
WEATHER = {"VMC": "visual meteorological conditions", "IMC": "instrument meteorological conditions"}
LIGHT = {"DAYL": "daylight", "DAWN": "dawn", "DUSK": "dusk", "NITE": "night", "NDRK": "night (dark)",
         "NBRT": "night (bright)"}
# makers of amateur-built kits and designs: the only "make" words of an amateur-built aircraft that are not masked
KIT_MAKERS = {"vans", "van's", "zenith", "zenair", "rans", "lancair", "quicksilver", "kitfox", "quad", "city", "rotorway",
              "glasair", "pitts", "kolb", "titan", "pietenpol", "cub", "crafters", "rutan", "avid", "just", "bearhawk",
              "fisher", "cassutt", "thorp", "progressive", "aerodyne", "denney", "sonex", "steen", "christen", "velocity",
              "murphy", "searey", "aerocomp", "europa", "cozy", "varieze", "long-ez", "skystar", "hatz", "bushby",
              "wag-aero", "stoddard-hamilton", "aviat", "belite", "challenger", "kitplanes", "comp", "evektor", "jabiru",
              "pulsar", "rotax", "breezy", "mustang", "midget", "sportsman", "harmon", "rocket", "tango", "seawind"}
MAKER_MIN = 5               # a "make" seen on fewer aircraft, with no company word, may be a private owner-builder's name
TERRITORIES = {"PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands", "AS": "American Samoa",
               "MP": "Northern Mariana Islands", "AO": "Atlantic Ocean", "PO": "Pacific Ocean", "GM": "Gulf of Mexico"}
COMPANY_WORDS = {"aircraft", "aircrafts", "inc", "llc", "corp", "corporation", "co", "company", "aviation", "air", "aero",
                 "experimental", "homebuilt", "kit", "kits", "built", "sport", "ltd", "gmbh", "industries", "international",
                 "design", "designs", "works", "the", "and", "of", "manufacturing", "mfg", "systems", "planes",
                 "aerospace", "helicopter", "helicopters", "gyroplane", "balloon", "balloons", "custom", "amateur"}

HEADER = re.compile(r"(?:(?<=\n)|(?<=^)|(?<=[.:)\]\"”’]))\s*([A-Z][A-Z&/(),' -]{5,}[A-Z)])(?=\s*\n|[A-Z][a-z]|\s+[A-Z][a-z])")
TITLE_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mister|Dr)\.?\s+(?:[A-Z]\.\s*)?[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?")
REGISTRATION = re.compile(r"\bN[1-9][0-9]{1,4}[A-Z]{0,2}\b|\b[A-Z]{1,2}-[A-Z]{3,4}\b")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CAPTION = re.compile(r"^(?:Figure|Photo|Image|Source)\b|Courtesy of", re.I)
# periods that do not end a sentence: a zero-width space after them keeps common.drop_sentences / clip from splitting there
ABBREV = re.compile(r"\b(?:St|Ste|Mt|Ft|Pt|Rd|Ave|Blvd|Hwy|Co|Twp|Jct|Dr|Mr|Mrs|Ms|Jr|Sr|No|Nos|Lt|Sgt|Capt|Gen|Col|Gov|"
                    r"Dept|Inc|Corp|Ltd|Univ|approx|Approx|est|vs|Lat|Long|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|"
                    r"Dec|ft|mi|nm|hr|hrs|min|sec|lbs|deg|Fig|U\.S|a\.m|p\.m|A\.M|P\.M|e\.g|i\.e)\.(?=\s)")
KEEP = "\u200b"


def protect(text: str) -> str:
    return re.sub(r"(?<=[.!?])(?=\s+[a-z])", KEEP, ABBREV.sub(lambda m: m.group(0) + KEEP, text))


# ------------------------------------------------------------------------------------------------------------ raw

def _mdb_files(raw: str, tmp: str) -> list[str]:
    """The .mdb of each zip in apply order (avall.zip, then the weekly updates), copied out of the verified zips."""
    order = json.load(open(os.path.join(raw, "fetch.json")))["apply_order"]
    out = []
    for name in order:
        with zipfile.ZipFile(os.path.join(raw, name)) as zf:
            members = [i for i in zf.infolist() if i.filename.lower().endswith(".mdb") and "/" not in i.filename
                       and "\\" not in i.filename and ".." not in i.filename]
            if len(members) != 1:
                raise SystemExit(f"{name}: expected one .mdb, found {[i.filename for i in zf.infolist()]}")
            path = os.path.join(tmp, name[:-4] + ".mdb")
            with zf.open(members[0]) as src, open(path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(path)
    return out


def _export(mdb: str, table: str) -> list[dict]:
    """One table as CSV rows (mdbtools' mdb-export; dates as yyyy-mm-dd)."""
    run = subprocess.run(["mdb-export", "-T", "%Y-%m-%d", mdb, table], capture_output=True, check=True)
    csv.field_size_limit(1 << 30)
    return list(csv.DictReader(io.StringIO(run.stdout.decode("utf-8", "replace"), newline="")))


def tables(raw: str) -> dict[str, dict[str, list[dict]]]:
    """table -> ev_id -> rows, the updates applied in order (an event's rows in a later file replace its earlier rows)."""
    out: dict[str, dict[str, list[dict]]] = {t: {} for t in TABLES if t != "states"}
    with tempfile.TemporaryDirectory(prefix="ntsb-") as tmp:
        mdbs = _mdb_files(raw, tmp)
        for mdb in mdbs:
            for t in out:
                by: dict[str, list[dict]] = {}
                for row in _export(mdb, t):
                    by.setdefault(row["ev_id"], []).append(row)
                out[t].update(by)
        out["states"] = {r["state"]: [r] for r in _export(mdbs[0], "states")}
    return out


# ------------------------------------------------------------------------------------------------------------ records

def _int(x: str) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def level_from_totals(ev: dict) -> str:
    f, s, m = (_int(ev.get(k)) for k in ("inj_tot_f", "inj_tot_s", "inj_tot_m"))
    return "FATL" if f else "SERS" if s else "MINR" if m else "NONE"


def level_from_injury_table(rows: list[dict]) -> str | None:
    if not rows:
        return None
    n = {lv: sum(_int(r["inj_person_count"]) for r in rows if r["injury_level"] == lv) for lv in LEVELS}
    return next((lv for lv in LEVELS[:3] if n[lv] > 0), "NONE")


def _norm_make(make: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", make.lower()).strip()


def records(t: dict[str, dict[str, list[dict]]]) -> tuple[list[dict], dict[str, int]]:
    out, why = [], {}
    makes: dict[str, int] = {}
    for rows in t["aircraft"].values():
        for a in rows:
            makes[_norm_make(a["acft_make"])] = makes.get(_norm_make(a["acft_make"]), 0) + 1

    def drop(reason: str) -> None:
        why[reason] = why.get(reason, 0) + 1
    for ev_id, evs in t["events"].items():
        ev = evs[0]
        if ev["ev_type"] != "ACC" or ev["invest_agy"] != "N":
            drop("not an NTSB-investigated accident")
            continue
        acft = t["aircraft"].get(ev_id, [])
        nar = t["narratives"].get(ev_id, [])
        if len(acft) != 1 or len(nar) > 1:
            drop("not exactly one aircraft / narrative")
            continue
        adm = t["NTSB_Admin"].get(ev_id, [{}])[0]
        if adm.get("rec_stat") != "B" or not nar or not nar[0]["narr_cause"].strip():
            drop("no final report (preliminary or factual only)")
            continue
        level = ev["ev_highest_injury"].strip()
        if level not in LEVELS:
            drop("highest injury missing or unknown")
            continue
        if level_from_totals(ev) != level or level_from_injury_table(t["injury"].get(ev_id, [])) != level:
            drop("highest injury conflicts with the injury totals / injury table")
            continue
        narrative = nar[0]["narr_accp"].strip() or nar[0]["narr_accf"].strip()
        defining = sorted((r for r in t["Events_Sequence"].get(ev_id, []) if r["Defining_ev"] == "1"),
                          key=lambda r: _int(r["Occurrence_No"]))
        make = _norm_make(acft[0]["acft_make"])
        known = acft[0]["homebuilt"] != "Y" and bool(make) and (
            makes.get(make, 0) >= MAKER_MIN or any(w in COMPANY_WORDS for w in make.split()))
        out.append({"ev_id": ev_id, "ntsb_no": ev["ntsb_no"], "level": level, "ev": ev, "acft": acft[0], "make_known": known,
                    "narrative": narrative, "phase": defining[0]["phase_no"] if defining else "",
                    "key": f"ntsb-{ev_id}"})
    return out, why


def history(text: str) -> str:
    """The narrative up to its first section header after "HISTORY OF FLIGHT" (long field reports only have headers)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    heads = [m for m in HEADER.finditer(text) if len(m.group(1).split()) >= 2 or m.group(1) == "COMMUNICATIONS"]
    start = 0
    if heads and heads[0].group(1).startswith("HISTORY OF FLIGHT") and not text[:heads[0].start(1)].strip():
        start, heads = heads[0].end(1), heads[1:]
    return text[start:heads[0].start(1) if heads else len(text)]


def builder_words(rec: dict) -> list[str]:
    """Words of the "make" that may be a private person's name: every word but kit makers' and company words, for an
    amateur-built aircraft (its make is usually the builder) or a make that is not a known maker (see ``records``)."""
    if rec["make_known"]:
        return []
    return [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{1,}", rec["acft"]["acft_make"])
            if w.lower() not in KIT_MAKERS and w.lower() not in COMPANY_WORDS]


def mask(text: str, rec: dict) -> str:
    text = TITLE_NAME.sub("[name]", text)
    for w in builder_words(rec):
        text = re.sub(r"\b(?:" + re.escape(w.capitalize()) + "|" + re.escape(w.upper()) + r")\b", "[name]", text)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return REGISTRATION.sub("[registration]", text)


def narrative_text(rec: dict) -> str:
    text = protect(R.norm_ws(mask(history(rec["narrative"]), rec)))
    text = " ".join(s for s in R._SENT_END.split(text) if not CAPTION.search(s))
    return R.clip(R.drop_sentences(text, SCRUB_RE), TEXT_LIMIT).replace(KEEP, "")


def _name_case(s: str) -> str:
    """An upper-case place name in title case (small words lower case); mixed-case names as they are."""
    s = s.strip()
    if not s.isupper():
        return s
    return " ".join(w.lower() if i and w.lower() in ("of", "the", "and") else w.capitalize() for i, w in enumerate(s.split()))


def context(rec: dict, states: dict) -> list[str]:
    ev, ac = rec["ev"], rec["acft"]
    lines = ["Aviation accident investigated by the US National Transportation Safety Board",
             f"Date: {ev['ev_date'][:10]}"]
    code = ev["ev_state"].strip()
    state = _name_case(states.get(code, [{}])[0].get("name", "")) or TERRITORIES.get(code, "")
    place = ", ".join(x for x in (_name_case(ev["ev_city"]), state) if x)
    if place:
        lines.append(f"Location: {place}")
    cat = CATEGORY.get(ac["acft_category"].strip(), "Aircraft")
    if ac["homebuilt"] == "Y":
        lines.append(f"Aircraft: {cat}, amateur-built")
    elif rec["make_known"]:
        mm = " ".join(x for x in (ac["acft_make"].strip(), ac["acft_model"].strip()) if x)
        lines.append(f"Aircraft: {cat}, {mm}")
    else:
        lines.append(f"Aircraft: {cat}")
    part, kind = FAR_PART.get(ac["far_part"].strip()), TYPE_FLY.get(ac["type_fly"].strip())
    if part or kind:
        lines.append("Operation: " + ", ".join(x for x in (part, f"{kind} flight" if kind else None) if x))
    if rec["phase"] in PHASE:
        lines.append(f"Phase of flight: {PHASE[rec['phase']]}")
    cond = [x for x in (WEATHER.get(ev["wx_cond_basic"].strip()), LIGHT.get(ev["light_cond"].strip())) if x]
    if cond:
        lines.append(f"Conditions: {', '.join(cond)}")
    return lines


def render(rec: dict, states: dict, rng: random.Random) -> str | None:
    narrative = narrative_text(rec)
    if len(narrative) < MIN_NARRATIVE:
        return None
    record = "\n".join(context(rec, states) + [f"Narrative: {narrative}"])
    if R.scrub_hits(record, SCRUB_RE):          # the record text only: the question below is ours and names "injury"
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    t = tables(raw)
    recs, dropped = records(t)
    n_read = len(t["events"])
    kept, unrendered, seen = [], 0, {}
    for rec in sorted(recs, key=lambda r: R.hash_order(DOMAIN, r["key"])):
        text = render(rec, t["states"], random.Random(f"{DOMAIN}|{rec['key']}"))
        norm = R.norm_ws(text.rsplit("\n\n", 1)[0]).lower() if text else None
        if text is None or norm in seen:
            unrendered += 1
            continue
        seen[norm] = rec["key"]
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    capped, class_report = R.cap_classes(kept, lambda r: r["level"], DOMAIN)
    final = R.take(capped, DOMAIN)
    labels = [LABELS[lv] for lv in LEVELS if lv in {r["level"] for r in capped}]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["level"]], source="ntsb",
                             source_id=rec["ntsb_no"], snapshot=snapshot,
                             record_date=dt.date.fromisoformat(rec["ev"]["ev_date"][:10]), shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "apply_order": fetch["apply_order"],
                "label_field": "events.ev_highest_injury (agreeing with events.inj_tot_* and the injury table)",
                "labels": {lv: LABELS[lv] for lv in LEVELS}, "events_read": n_read, "dropped_by_filter": dropped,
                "candidates": len(recs), "dropped_unrenderable_scrub_or_duplicate": unrendered, **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    """The pinned raw file that holds the record (the event's newest copy), with the NTSB number as a fragment; the case can
    be looked up by that number in NTSB CAROL."""
    _, files = _raw_events(snapshot)
    return f"{FILE_URL.format(files.get(row['source_id'], 'avall.zip'))}#ntsb_no={row['source_id']}"


_RAW: dict[str, tuple[dict, dict]] = {}


def _raw_events(snapshot: str) -> tuple[dict, dict]:
    """ntsb_no -> (highest injury, event date, narrative text) read again with mdb-json (not the builder's CSV path), the
    files applied in order (an event's rows in a later file replace its earlier rows, table by table); and ntsb_no -> the
    zip it was last read from. Cached per process."""
    if snapshot not in _RAW:
        raw = os.path.join(R.RAW, DOMAIN, snapshot)
        events, narr, where = {}, {}, {}
        with tempfile.TemporaryDirectory(prefix="ntsb-audit-") as tmp:
            for zname, mdb in zip(json.load(open(os.path.join(raw, "fetch.json")))["apply_order"], _mdb_files(raw, tmp)):
                found = {}
                for table in ("events", "narratives"):
                    out = subprocess.run(["mdb-json", mdb, table], capture_output=True, check=True).stdout
                    for line in out.decode("utf-8", "replace").splitlines():
                        if line.strip():
                            r = json.loads(line)
                            found.setdefault(table, {}).setdefault(r["ev_id"], []).append(r)
                for ev_id, rs in found.get("events", {}).items():
                    events[ev_id] = rs[0]
                    where[rs[0]["ntsb_no"]] = zname
                for ev_id, rs in found.get("narratives", {}).items():
                    narr[ev_id] = " ".join((r.get("narr_accp") or "") + " " + (r.get("narr_accf") or "") for r in rs)
        _RAW[snapshot] = ({e["ntsb_no"]: (e.get("ev_highest_injury"), e.get("ev_date", ""), narr.get(ev_id, ""))
                           for ev_id, e in events.items()}, where)
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The highest injury read again from the raw files (mdb-json, newest file wins), and whether the item's date is the
    event's date and its narrative is the record's own wording (every unmasked stretch of every sentence is found in the
    raw narrative)."""
    events, _ = _raw_events(snapshot)
    if row["source_id"] not in events:
        return None, False
    level, date, narr = events[row["source_id"]]
    text = row["questions"][0]["instructions"].rsplit("\n\n", 1)[0]
    m = re.search(r"^Date: (\d{4}-\d{2}-\d{2})$", text, re.M)
    mdy = dt.datetime.strptime(date[:8], "%m/%d/%y").date().isoformat() if re.match(r"\d\d/\d\d/\d\d", date) else ""
    story = text.split("\nNarrative: ", 1)[1] if "\nNarrative: " in text else ""
    raw_norm = re.sub(r"\s+", " ", narr)
    pieces = [p.strip() for sent in re.split(r"(?<=[.!?])\s+", story)
              for p in re.split(r"\[(?:name|registration|email|phone)\]", sent) if len(p.strip()) >= 20]
    text_ok = bool(m and m.group(1) == mdy and pieces and all(p in raw_norm for p in pieces))
    return LABELS.get((level or "").strip()), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows (fresh {m['splits'][s]['fresh']}), classes {m['splits'][s]['class_prior']}, "
              f"gold position {m['splits'][s]['gold_position']}")
    print(f"events read {m['events_read']}, candidates {m['candidates']}, dropped by filter {m['dropped_by_filter']}, "
          f"dropped (scrub / short / duplicate) {m['dropped_unrenderable_scrub_or_duplicate']}, "
          f"classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
