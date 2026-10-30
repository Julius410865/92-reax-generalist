"""#14 NOAA Storm Events -> event type: eval-v5.1 mirror rows (part N, task type ``noaa_storm_event_type``).

    python -I tools/records/build_noaa_storm_type.py --snapshot 2026-10-27

Records: the yearly "details" files of the Storm Events Database (2024, 2025 and 2026; the 2026 file was created
2026-10-26 but its newest events begin in July 2026), read from the raw .csv.gz files as data.
* Label: the ``EVENT_TYPE`` field. The 26 most frequent types of the snapshot are considered (``TOP_N``); of those, the types
  in ``DROPPED`` are left out because they cannot be told apart once their own words are removed (see there), and the rest
  are kept (``LABELS``). Classes under 20 records are dropped and each class is capped at 3x the median per split.
* Record text: state, month and the ``EVENT_NARRATIVE``, cut at a sentence boundary. Not used, because they give the type
  away: magnitude and magnitude type (wind speed in knots or hail size in inches), flood cause, tornado scale / length /
  width, the county-or-zone type and name (zone names and marine zones name the hazard), the episode narrative (it names
  every phenomenon of the episode), injuries, deaths and damage. Every sentence with a word of ``SCRUB`` (the kept types'
  names, their variants and obvious synonyms, and the terms that name the phenomenon: hail sizes, tornado ratings and
  touch-down / path words, drought categories, wind-speed units, tide datums, tropical-cyclone names) is removed, and so are
  every sentence with an unreadable character (the source has U+FFFD in place of some characters) and the sentences about
  the report rather than the event (``META``: estimated times and places, how it was relayed, data sources); a record left with
  fewer than ``MIN_NARRATIVE`` characters is dropped, and so is a record whose text equals another record's (all copies
  when their types differ).
* Group key: the episode id (an episode's events stay in one split); records are ordered by event id.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "noaa_storm_type"
TASK = "noaa_storm_event_type"
AREA = "retrieval"          # one of many categories
EVAL_FRAC = 0.05            # tens of thousands of kept records
TEXT_LIMIT = 900
MIN_NARRATIVE = 80
TOP_N = 26
EVENT_URL = "https://www.ncei.noaa.gov/stormevents/eventdetails.jsp?id={}"
LABELS = {"Thunderstorm Wind": "Thunderstorm Wind", "Hail": "Hail", "Flash Flood": "Flash Flood (rapid onset)",
          "Flood": "Flood (slow-rising)", "Drought": "Drought", "High Wind": "High Wind (non-thunderstorm)",
          "Winter Weather": "Winter Weather (advisory level)", "Winter Storm": "Winter Storm (warning level)",
          "Excessive Heat": "Excessive Heat", "Tornado": "Tornado", "Extreme Cold/Wind Chill": "Extreme Cold / Wind Chill",
          "Dense Fog": "Dense Fog", "Wildfire": "Wildfire",
          "Frost/Freeze": "Frost / Freeze", "Tropical Storm": "Tropical Storm", "Dust Storm": "Dust Storm"}
DROPPED = {
    "Heat": "told apart from Excessive Heat only by local warning thresholds; once heat words are removed both are "
            "temperature reports (or heat-death reports with no cue left)",
    "Cold/Wind Chill": "told apart from Extreme Cold/Wind Chill only by local warning thresholds; both read as low "
                       "temperature reports once cold / wind-chill words are removed",
    "Strong Wind": "told apart from High Wind only by the measured speed, which is in the removed wind / gust / mph "
                   "sentences; the rest is the same tree and power-line damage",
    "Heavy Snow": "told apart from Winter Storm only by whether other hazards (sleet, ice, wind) occurred, which are "
                  "removed words; both read as snowfall-amount reports",
    "Blizzard": "defined by wind, blowing snow and visibility together; with those words removed it reads as Winter "
                "Weather / Winter Storm",
    "Marine Thunderstorm Wind": "the narratives are wind-gust measurements; few records keep any text without the type's "
                                "own words",
    "Funnel Cloud": "the narratives only say that a funnel was seen; almost nothing is left without the type's own words",
    "Lightning": "what is left without lightning / thunderstorm words is a fire or an injury with no cue to the type",
    "Coastal Flood": "with tide / coastal / flood words removed it reads as Flood (water on roads)",
    "Heavy Rain": "with rain words removed what is left is an amount in inches (read as snowfall) or water, rock and mud "
                  "on roads (read as Flood / Flash Flood)"}
SCRUB = (
    # convective and non-convective wind
    "thunderstorm", "thunderstorms", "tstm", "tstms", "t-storm", "t-storms", "tstorm", "tstorms", "thunder",
    "thundershower", "thundershowers", "storm", "storms", "stormy", "wind", "winds", "windy", "windstorm", "windstorms",
    "gust", "gusts", "gusted", "gusting", "gusty", "gustnado", "downburst", "downbursts", "microburst", "microbursts",
    "macroburst", "derecho", "straight-line", "straight line", "outflow", "gust front", "bow echo", "squall", "squalls",
    "mph", "m.p.h.", "miles per hour", "knot", "knots", "kt", "kts", "marine", "sustained",
    # hail and hail sizes
    "hail", "hailstone", "hailstones", "hailstorm", "hailstorms", "hailfall", "graupel", "ping pong", "ping-pong",
    "golf ball", "golf balls", "golfball", "golfballs", "golf-ball", "baseball", "baseballs", "softball", "softballs",
    "tennis ball", "tennis balls", "quarter size", "quarter sized", "quarter-size", "quarter-sized", "quarters",
    "half dollar", "half dollars", "half-dollar", "nickel", "nickels", "nickel-size", "nickel-sized", "dime", "dimes",
    "penny", "pennies", "pea", "peas", "pea-size", "pea-sized", "marble", "marbles", "hen egg", "egg", "eggs", "walnut",
    "grape", "grapes", "grapefruit", "teacup", "tea cup", "lime", "limes", "diameter", "mping",
    # floods, rain, coast
    "flood", "floods", "flooded", "flooding", "floodwater", "floodwaters", "floodplain", "flash", "inundate", "inundated",
    "inundating", "inundation", "submerge", "submerged", "overflow", "overflowed", "overflowing", "overtop", "overtopped",
    "overtopping", "bankfull", "crest", "crested", "cresting", "ponding", "coastal", "tide", "tides", "tidal", "mllw",
    "mhhw", "mhw", "surge", "surges", "storm surge", "astronomical", "lakeshore", "rain", "rains", "rained", "raining",
    "rainfall", "rainfalls", "rainwater", "rainy", "downpour", "downpours", "deluge", "cloudburst", "debris flow",
    "debris flows", "mudslide", "mudslides", "mud slide", "mud slides", "landslide", "landslides", "rockslide",
    "rockslides", "rock slide", "mudflow", "mudflows", "slide", "slides",
    # drought
    "drought", "droughts", "drought monitor", "dry", "abnormally dry", "dryness", "drier", "driest", "d0", "d1", "d2", "d3",
    "d4", "usdm", "deficit", "deficits",
    # winter
    "winter", "wintry", "wintery", "snow", "snows", "snowed", "snowing", "snowfall", "snowfalls", "snowstorm", "snowstorms",
    "snowpack", "snowmelt", "snowy", "snowflake", "snowflakes", "snowplow", "snowplows", "snowmobile", "snowmobiles",
    "snotel", "snotels", "flurries", "flurry", "sleet", "ice pellets", "freezing rain", "freezing drizzle", "freezing fog",
    "ice", "icy", "iced", "icing", "icicles", "glaze", "glazed", "glazing", "accretion", "accretions", "blizzard",
    "blizzards", "whiteout", "whiteouts", "white-out", "white-outs", "lake effect", "lake-effect", "lake enhanced",
    "avalanche", "avalanches", "drift", "drifts", "drifting", "drifted", "plow", "plows", "plowed", "plowing",
    # heat and cold
    "heat", "heat index", "heatwave", "heatwaves", "heatrisk", "heatstroke", "excessive", "hot", "hotter", "hottest",
    "sweltering", "scorching", "hyperthermia", "cold", "colder", "coldest", "chill", "chills", "chilly", "wind chill",
    "windchill", "windchills", "frigid", "frostbite", "hypothermia", "arctic", "frost", "frosts", "frosty", "freeze",
    "freezes", "freezing", "froze", "frozen",
    # fog, dust, fire, lightning
    "fog", "fogs", "foggy", "dense", "dust", "dusty", "haboob", "haboobs", "brownout", "brownouts", "wildfire", "wildfires",
    "fire", "fires", "wildland", "blaze", "blazes", "burn", "burns", "burned", "burning", "burnt", "red flag", "containment",
    "lightning", "lightening",
    # tropical cyclones and the 2024-2026 storm names
    "tropical", "hurricane", "hurricanes", "typhoon", "typhoons", "cyclone", "cyclones", "landfall", "post-tropical",
    "alberto", "beryl", "chris", "debby", "ernesto", "francine", "gordon", "helene", "isaac", "joyce", "kirk", "leslie",
    "milton", "nadine", "oscar", "patty", "rafael", "sara", "andrea", "barry", "chantal", "dexter", "erin", "fernand",
    "gabrielle", "humberto", "imelda", "jerry", "karen", "lorenzo", "melissa", "hone", "gilma", "hector", "kiko", "flossie",
    "priscilla", "raymond", "arthur", "bertha", "cristobal", "dolly", "edouard", "fay", "gonzalo", "hanna", "isaias",
    "josephine",
    # tornadoes, funnels, waterspouts
    "tornado", "tornadoes", "tornados", "tornadic", "twister", "twisters", "landspout", "landspouts", "touched down",
    "touchdown", "touch down", "touching down", "touches down", "touched", "ef0", "ef1", "ef2", "ef3", "ef4", "ef5", "ef-0",
    "ef-1", "ef-2", "ef-3", "ef-4", "ef-5", "efu", "ef-u", "fujita", "vortex", "vortices", "multi-vortex", "rotation",
    "rotating", "funnel", "funnels", "waterspout", "waterspouts", "spout", "path", "paths", "width", "widths",
    "dissipated", "dissipating", "dissipate", "lifted", "lifting", "lifts", "circulation", "circulations",
    # found by the leak test and in the items: words that name a kept type's phenomenon or its defining measure
    "contained", "smoke", "smoky", "fuels", "perimeter", "index", "indices",
    # further forms and compounds of label words
    "hailing", "hailed", "derechos", "flashflood", "flashflooding", "rainstorm", "rainstorms", "snowdrift", "snowdrifts",
    "snowbank", "snowbanks", "brushfire", "brushfires", "grassfire", "grassfires", "firestorm", "duststorm",
    "duststorms", "sandstorm", "sandstorms", "blowing dirt", "blowing sand", "high water", "high-water", "firefighter",
    "firefighters", "firefighting")
SCRUB_RE = R.scrub_pattern(SCRUB)
UNREADABLE = re.compile("\ufffd|\\bxxx+\\b", re.I)          # replaced characters and "xxx" placeholders of the source
# sentences about the report rather than the event (how it was received, estimated times and places, data sources); once
# the type's own sentences are removed they are often all that is left, and they say nothing about the event
META = re.compile("|".join((
    r"\btime\b[^.]{0,40}\b(?:estimated|approximate|approximated)\b", r"\b(?:estimated|approximated) (?:from|by|based on|using) radar\b",
    r"\blocations? (?:is |was |are |were )?(?:approximate|estimated)\b", r"\bapproximate location\b", r"\brelayed\b",
    r"\bsocial media\b", r"\bspotter network\b", r"\bsources? (?:include|included|were|was)\b",
    r"\b(?:image|images|photo|photos|picture|pictures|video|videos)\b[^.]{0,30}\b(?:shared|posted|received|provided|submitted|sent)\b",
    r"\b(?:shared|posted|received|provided|submitted|sent)\b[^.]{0,30}\b(?:image|images|photo|photos|picture|pictures|video|videos)\b",
    r"\bperiod of record\b", r"\bnearest (?:asos|awos|coop|cooperative|weather|observ)", r"\bremote sensing\b",
    r"\b(?:damages?|costs?|losses)\b[^.]{0,30}\b(?:rough )?estimated?\b",
    r"\bno (?:known |other )?(?:reports? of )?(?:damages?|injuries|fatalities)\b")), re.I)
QUESTIONS = ("Which event type was this storm event recorded as?",
             "What type of weather event does this record describe?",
             "Under which event type is this event filed in the Storm Events Database?",
             "Which storm event category does this record belong to?",
             "What kind of event does this report describe?")

# periods that do not end a sentence: a zero-width space after them keeps common.drop_sentences / clip from splitting there
ABBREV = re.compile(r"\b(?:St|Ste|Mt|Ft|Pt|Rd|Ave|Blvd|Hwy|Hwys|Co|Twp|Jct|Dr|Mr|Mrs|Ms|Jr|Sr|No|Nos|Lt|Sgt|Capt|Gen|Col|Gov|"
                    r"Dept|Inc|Corp|Ltd|Univ|approx|Approx|est|vs|Lat|Long|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|"
                    r"Dec|ft|mi|nm|hr|hrs|min|sec|lbs|deg|Fig|U\.S|a\.m|p\.m|A\.M|P\.M|e\.g|i\.e)\.(?=\s)")
KEEP = "​"


def protect(text: str) -> str:
    return re.sub(r"(?<=[.!?])(?=\s+[a-z])", KEEP, ABBREV.sub(lambda m: m.group(0) + KEEP, text))


def details_files(raw: str) -> list[str]:
    names = json.load(open(os.path.join(raw, "fetch.json")))["details_files"]
    return [os.path.join(raw, names[y]) for y in sorted(names)]


def read_rows(raw: str) -> list[dict]:
    rows = []
    for path in details_files(raw):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def top_types(rows: list[dict]) -> list[str]:
    n: dict[str, int] = {}
    for r in rows:
        n[r["EVENT_TYPE"]] = n.get(r["EVENT_TYPE"], 0) + 1
    return [t for t, _ in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]]


def records(rows: list[dict]) -> tuple[list[dict], dict, list[str]]:
    top = top_types(rows)
    unknown = [t for t in top if t not in LABELS and t not in DROPPED]
    if unknown:
        raise SystemExit(f"top types with no decision (add them to LABELS or DROPPED): {unknown}")
    by_id, why = {}, {}
    for r in rows:
        t = r["EVENT_TYPE"].strip()
        if t not in LABELS:
            why[t if t in DROPPED else "outside the top types"] = why.get(t if t in DROPPED else "outside the top types", 0) + 1
            continue
        if not r["EVENT_ID"].isdigit() or not r["EPISODE_ID"].isdigit():
            why["no event / episode id"] = why.get("no event / episode id", 0) + 1
            continue
        by_id[r["EVENT_ID"]] = {"event_id": r["EVENT_ID"], "episode_id": r["EPISODE_ID"], "type": t, "row": r,
                                "key": f"event-{r['EVENT_ID']}", "group": f"episode-{r['EPISODE_ID']}"}
    return list(by_id.values()), why, top


def narrative_text(narr: str) -> str:
    text = protect(R.norm_ws(narr.replace("|", " ")))
    text = R.drop_sentences(R.drop_sentences(R.drop_sentences(text, UNREADABLE), META), SCRUB_RE)
    return R.clip(text, TEXT_LIMIT).replace(KEEP, "")


def state_name(s: str) -> str:
    return " ".join(w.lower() if i and w.lower() in ("of", "the", "and") else w.capitalize()
                    for i, w in enumerate(s.strip().split()))


def begin_date(r: dict) -> dt.date | None:
    try:
        ym = r["BEGIN_YEARMONTH"].strip()
        return dt.date(int(ym[:4]), int(ym[4:6]), int(r["BEGIN_DAY"]))
    except (ValueError, KeyError):
        return None


def render(rec: dict, rng: random.Random) -> str | None:
    r = rec["row"]
    narrative = narrative_text(r["EVENT_NARRATIVE"])
    if len(narrative) < MIN_NARRATIVE:
        return None
    record = "\n".join(["NOAA NCEI weather event record", f"State: {state_name(r['STATE'])}",
                        f"Month: {r['MONTH_NAME'].strip()} {r['YEAR'].strip()}", f"Narrative: {narrative}"])
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours and names "storm"
        return ""                           # a scrub word in the state line (none is expected)
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    rows = read_rows(raw)
    recs, dropped, top = records(rows)
    rendered, short, scrub_header = [], 0, 0
    for rec in sorted(recs, key=lambda r: R.hash_order(DOMAIN, r["key"])):
        text = render(rec, random.Random(f"{DOMAIN}|{rec['key']}"))
        if not text:
            short += text is None
            scrub_header += text == ""
            continue
        rec["text"] = text
        rendered.append(rec)
    same: dict[str, list[dict]] = {}
    for rec in rendered:
        same.setdefault(R.norm_ws(rec["text"].rsplit("\n\n", 1)[0]).lower(), []).append(rec)
    kept, dup_same, dup_conflict = [], 0, 0
    for group in same.values():
        if len({r["type"] for r in group}) > 1:
            dup_conflict += len(group)
            continue
        dup_same += len(group) - 1
        rec = group[0]                       # the first in hash order
        rec["split"] = R.split_of(DOMAIN, rec["group"], EVAL_FRAC)
        kept.append(rec)
    kept.sort(key=lambda r: R.hash_order(DOMAIN, r["key"]))
    capped, class_report = R.cap_classes(kept, lambda r: r["type"], DOMAIN)
    final = R.take(capped, DOMAIN)
    labels = [LABELS[t] for t in LABELS if t in {r["type"] for r in capped}]
    out, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        out.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                            instructions=rec["text"], options=labels, gold=LABELS[rec["type"]], source="noaa_storm_events",
                            source_id=rec["event_id"], snapshot=snapshot, record_date=begin_date(rec["row"]),
                            shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    dates = [d for d in (begin_date(r) for r in rows) if d]
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "EVENT_TYPE", "labels": LABELS, "top_types": top,
                "types_dropped_not_separable": {t: {"reason": DROPPED[t], "records": dropped.get(t, 0)} for t in DROPPED},
                "events_read": len(rows), "newest_event_begin": max(dates).isoformat() if dates else None,
                "dropped_by_filter": {k: v for k, v in dropped.items() if k not in DROPPED},
                "candidates": len(recs), "dropped_short_after_scrub": short, "dropped_scrub_word_in_state": scrub_header,
                "dropped_duplicate_text_same_type": dup_same, "dropped_duplicate_text_conflicting_type": dup_conflict,
                **class_report}
    return R.write_domain(DOMAIN, out, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return EVENT_URL.format(row["source_id"])


_RAW: dict[str, dict[str, tuple[str, str, str, str]]] = {}


def _raw_events(snapshot: str) -> dict[str, tuple[str, str, str, str]]:
    """EVENT_ID -> (EVENT_TYPE, STATE, "MONTH_NAME YEAR", EVENT_NARRATIVE), read again with a plain csv.reader by column
    position from each file's header row (not the builder's DictReader path); cached per process."""
    if snapshot not in _RAW:
        out = {}
        for path in details_files(os.path.join(R.RAW, DOMAIN, snapshot)):
            with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
                rd = csv.reader(fh)
                head = next(rd)
                i = {c: head.index(c) for c in ("EVENT_ID", "EVENT_TYPE", "STATE", "MONTH_NAME", "YEAR", "EVENT_NARRATIVE")}
                for cells in rd:
                    out[cells[i["EVENT_ID"]]] = (cells[i["EVENT_TYPE"]], cells[i["STATE"]],
                                                 f"{cells[i['MONTH_NAME']]} {cells[i['YEAR']]}", cells[i["EVENT_NARRATIVE"]])
        _RAW[snapshot] = out
    return _RAW[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The event type read again from the raw file, and whether the item's state, month and narrative are the record's own
    (every sentence of the item's narrative found in the raw narrative)."""
    raw = _raw_events(snapshot).get(row["source_id"])
    if raw is None:
        return None, False
    etype, state, month, narr = raw
    text = row["questions"][0]["instructions"].rsplit("\n\n", 1)[0]
    lines = dict(ln.split(": ", 1) for ln in text.split("\n")[1:] if ": " in ln)
    story = lines.get("Narrative", "")
    raw_norm = re.sub(r"\s+", " ", narr.replace("|", " "))
    pieces = [p for p in re.split(r"(?<=[.!?])\s+", story) if p]
    text_ok = (lines.get("State", "").lower() == " ".join(state.split()).lower() and lines.get("Month") == month
               and bool(pieces) and all(p in raw_norm for p in pieces))
    return LABELS.get(etype.strip()), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows (fresh {m['splits'][s]['fresh']}), {len(m['splits'][s]['class_prior'])} "
              f"classes {m['splits'][s]['class_prior']}")
    print(f"events read {m['events_read']} (newest begins {m['newest_event_begin']}), candidates {m['candidates']}, "
          f"dropped short after scrub {m['dropped_short_after_scrub']}, duplicate text {m['dropped_duplicate_text_same_type']}"
          f" + {m['dropped_duplicate_text_conflicting_type']} conflicting, classes dropped {m['classes_dropped_under_min']}")
    print("types left out:", {t: v["records"] for t, v in m["types_dropped_not_separable"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
