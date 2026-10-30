"""T type ``omniscience``: single fact questions with five options (the renderer adds "I don't know").

    python -I tools/records/build_omniscience.py            # build from the saved query results (fetching missing ones)
    python -I tools/records/build_omniscience.py --fetch    # only fetch the missing query results

Source: Wikidata (CC0 1.0) through the public SPARQL endpoint. Each query in ``QUERIES`` is run once (one at a time,
at most one per minute: the endpoint currently rate-limits to 1 request / minute) and its raw JSON result is saved in
data/generalist/raw/omniscience/<name>.json; later runs read the saved files, so the build is deterministic. A fresh
fetch on another machine or day can return different rows (Wikidata is edited continuously).

Fact kinds (one per subject QID, each a single best-rank value): year of birth of a person (P569), country of a city
(P17), capital of a sovereign state or first-level division (P36), author of a literary work (P50), publication year of a
literary work (P577), director of a film (P57), founding year of a university (P571), mountain range of a mountain
(P4552) and composer of an opera (P86). Five options each (the gold plus four distractors of the same kind); the
renderer adds "I don't know" (``idk: true``). Nobel laureates are never subjects and no text mentions Nobel.
"""
from __future__ import annotations

import collections
import functools
import json
import math
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.records import common as C  # noqa: E402

TASK = "omniscience"
ENDPOINT = "https://query.wikidata.org/sparql"
RAW_DIR = C.RAW / TASK
QUERY_GAP_S = 75          # the endpoint asks for at most 1 request / minute
RETRIES = 3

# --- SPARQL queries (each with a LIMIT). Best-rank statements only; the builder keeps subjects with exactly one value.
_PERSON = """SELECT ?p ?l ?d ?st ?t ?prec ?sl WHERE {{
  ?p wdt:P106 wd:{occ} .
  ?p wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl . FILTER(?sl >= {minsl})
  ?p p:P569 ?st . ?st a wikibase:BestRank ; psv:P569 [ wikibase:timeValue ?t ; wikibase:timePrecision ?prec ] .
  ?p rdfs:label ?l . FILTER(LANG(?l) = "en")
  OPTIONAL {{ ?p schema:description ?d . FILTER(LANG(?d) = "en") }}
}} LIMIT 20000"""

OCCUPATIONS = (("painter", "Q1028181", 15), ("composer", "Q36834", 15), ("architect", "Q42973", 12),
               ("mathematician", "Q170790", 15), ("sculptor", "Q1281618", 12), ("explorer", "Q11900058", 10),
               ("poet", "Q49757", 20))

QUERIES: dict[str, str] = {f"persons_{name}": _PERSON.format(occ=occ, minsl=minsl) for name, occ, minsl in OCCUPATIONS}
QUERIES.update({
    # Nobel laureates (any rank): excluded as subjects of every question (the dev set's source is the Nobel Prize API).
    "nobel_laureates": """SELECT DISTINCT ?p WHERE {
  VALUES ?a { wd:Q38104 wd:Q44585 wd:Q80061 wd:Q37922 wd:Q35637 wd:Q47170 }
  ?p p:P166 ?s . ?s ps:P166 ?a .
} LIMIT 5000""",
    # sovereign states: continent and capital (best rank)
    "countries": """SELECT ?c ?l ?sl ?cont ?contl ?cap ?capl WHERE {
  ?c wdt:P31 wd:Q3624078 ; wikibase:sitelinks ?sl .
  FILTER NOT EXISTS { ?c wdt:P576 ?end }
  ?c rdfs:label ?l . FILTER(LANG(?l) = "en")
  OPTIONAL { ?c wdt:P30 ?cont . ?cont rdfs:label ?contl . FILTER(LANG(?contl) = "en") }
  OPTIONAL { ?c wdt:P36 ?cap . OPTIONAL { ?cap rdfs:label ?capl . FILTER(LANG(?capl) = "en") } }
} LIMIT 5000""",
    # first-level administrative divisions: country and capital
    "regions": """SELECT ?r ?l ?sl ?country ?cap ?capl WHERE {
  ?r wdt:P31 ?type . ?type wdt:P279 wd:Q10864048 .
  ?r wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  FILTER NOT EXISTS { ?r wdt:P576 ?end }
  ?r wdt:P17 ?country .
  ?r rdfs:label ?l . FILTER(LANG(?l) = "en")
  OPTIONAL { ?r wdt:P36 ?cap . OPTIONAL { ?cap rdfs:label ?capl . FILTER(LANG(?capl) = "en") } }
} LIMIT 30000""",
    # cities: country (best rank); the low sitelink floor also feeds the label-collision check
    "cities": """SELECT ?c ?l ?sl ?country ?countryl WHERE {
  VALUES ?cls { wd:Q515 wd:Q1549591 wd:Q1637706 wd:Q200250 wd:Q208511 }
  ?c wdt:P31 ?cls ; wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  ?c rdfs:label ?l . FILTER(LANG(?l) = "en")
  OPTIONAL { ?c wdt:P17 ?country . OPTIONAL { ?country rdfs:label ?countryl . FILTER(LANG(?countryl) = "en") } }
} LIMIT 40000""",
    # literary works: author (best rank), the author's birth year and the work's country of origin
    "works_author": """SELECT ?w ?l ?sl ?cls ?a ?al (MIN(YEAR(?ab)) AS ?aby) (SAMPLE(?o) AS ?origin) WHERE {
  VALUES ?cls { wd:Q7725634 wd:Q8261 wd:Q25379 wd:Q5185279 wd:Q49084 }
  ?w wdt:P31 ?cls ; wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  ?w rdfs:label ?l . FILTER(LANG(?l) = "en")
  ?w wdt:P50 ?a .
  OPTIONAL { ?a rdfs:label ?al . FILTER(LANG(?al) = "en") }
  OPTIONAL { ?a wdt:P569 ?ab }
  OPTIONAL { ?w wdt:P495 ?o }
} GROUP BY ?w ?l ?sl ?cls ?a ?al LIMIT 40000""",
    # literary works: publication date statements (best rank) with precision. Literary works are P31 Q7725634 (the
    # form classes novel / play / poem / short story have no instances with enough sitelinks); the broader form of
    # this query timed out, so it keeps works with 15+ sitelinks and fixes the join order.
    "works_pubdate": """SELECT ?w ?l ?sl ?st ?t ?prec WHERE {
  hint:Query hint:optimizer "None" .
  ?w wdt:P31 wd:Q7725634 .
  ?w wikibase:sitelinks ?sl . FILTER(?sl >= 15)
  ?w p:P577 ?st . ?st a wikibase:BestRank ; psv:P577 ?v . ?v wikibase:timeValue ?t ; wikibase:timePrecision ?prec .
  ?w rdfs:label ?l . FILTER(LANG(?l) = "en")
} LIMIT 40000""",
    # films: director (best rank), first release year, a country of origin
    "films": """SELECT ?f ?l ?sl ?dir ?dirl (MIN(YEAR(?date)) AS ?y) (SAMPLE(?o) AS ?origin) WHERE {
  ?f wdt:P31 wd:Q11424 ; wikibase:sitelinks ?sl . FILTER(?sl >= 15)
  ?f rdfs:label ?l . FILTER(LANG(?l) = "en")
  ?f wdt:P57 ?dir .
  OPTIONAL { ?dir rdfs:label ?dirl . FILTER(LANG(?dirl) = "en") }
  OPTIONAL { ?f wdt:P577 ?date }
  OPTIONAL { ?f wdt:P495 ?o }
} GROUP BY ?f ?l ?sl ?dir ?dirl LIMIT 40000""",
    # universities: inception statements (best rank) with precision, and a country
    "universities": """SELECT ?u ?l ?sl ?st ?t ?prec (SAMPLE(?c) AS ?country) WHERE {
  ?u wdt:P31 wd:Q3918 ; wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  ?u rdfs:label ?l . FILTER(LANG(?l) = "en")
  ?u p:P571 ?st . ?st a wikibase:BestRank ; psv:P571 [ wikibase:timeValue ?t ; wikibase:timePrecision ?prec ] .
  OPTIONAL { ?u wdt:P17 ?c }
} GROUP BY ?u ?l ?sl ?st ?t ?prec LIMIT 30000""",
    # mountains: mountain range (best rank) and a country
    "mountains": """SELECT ?m ?l ?sl ?rng ?rngl (SAMPLE(?c) AS ?country) WHERE {
  ?m wdt:P31 wd:Q8502 ; wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  ?m rdfs:label ?l . FILTER(LANG(?l) = "en")
  ?m wdt:P4552 ?rng .
  OPTIONAL { ?rng rdfs:label ?rngl . FILTER(LANG(?rngl) = "en") }
  OPTIONAL { ?m wdt:P17 ?c }
} GROUP BY ?m ?l ?sl ?rng ?rngl LIMIT 40000""",
    # operas: composer (best rank), the composer's birth date, the opera's country of origin. Operas are modelled as
    # dramatico-musical works (Q58483083) with genre opera or a subclass of it (P31 opera itself has almost no items).
    "operas": """SELECT ?o ?l ?sl ?c ?cl ?cb ?ctry WHERE {
  ?o wdt:P31 wd:Q58483083 ; wikibase:sitelinks ?sl . FILTER(?sl >= 4)
  FILTER EXISTS { ?o wdt:P136/wdt:P279* wd:Q1344 }
  ?o rdfs:label ?l . FILTER(LANG(?l) = "en")
  ?o wdt:P86 ?c .
  OPTIONAL { ?c rdfs:label ?cl . FILTER(LANG(?cl) = "en") }
  OPTIONAL { ?c wdt:P569 ?cb }
  OPTIONAL { ?o wdt:P495 ?ctry }
} LIMIT 40000""",
    # mountain ranges used above and their ancestors (range or part-of chains), to keep nested ranges out of the options
    "range_parents": """SELECT DISTINCT ?r ?parent WHERE {
  ?m wdt:P31 wd:Q8502 ; wikibase:sitelinks ?sl . FILTER(?sl >= 8)
  ?m wdt:P4552 ?r .
  ?r (wdt:P4552|wdt:P361)+ ?parent .
} LIMIT 50000""",
})


def query_url(q: str) -> str:
    return ENDPOINT + "?format=json&query=" + urllib.parse.quote(q)


def fetch_all() -> list[dict[str, str]]:
    """Fetch every missing query result (one at a time, QUERY_GAP_S apart); return the SOURCE.json entries."""
    C.USER_AGENT = C.USER_AGENT + " omniscience Wikidata SPARQL, one query per minute"
    entries, failed, last = [], [], 0.0
    for name, q in QUERIES.items():
        fn = f"{name}.json"
        p = RAW_DIR / fn
        for attempt in range(RETRIES):
            if p.exists():
                try:
                    json.loads(p.read_bytes())["results"]["bindings"]
                    break
                except Exception:  # noqa: BLE001  (a timed-out query can end in a truncated 200 body)
                    print(f"{fn}: saved result is not valid JSON, refetching", file=sys.stderr)
                    p.unlink()
            wait = QUERY_GAP_S * (attempt + 1) - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            try:
                C.fetch(TASK, query_url(q), fn)
                print(f"{fn}: fetched {p.stat().st_size} bytes", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001  (HTTP errors, timeouts, a stream cut by the server's timeout)
                print(f"{fn}: attempt {attempt + 1} failed: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
                part = p.with_suffix(p.suffix + ".part")
                if part.exists():
                    part.unlink()
        if p.exists():
            try:
                json.loads(p.read_bytes())["results"]["bindings"]
            except Exception:  # noqa: BLE001
                p.unlink()
        if not p.exists():
            failed.append(fn)
            continue
        entries.append({"name": fn, "url": query_url(q)})
    if failed:
        raise SystemExit(f"could not fetch: {failed}")
    return entries


# ------------------------------------------------------------------------------------------------------------ build

SOURCE = f"wikidata_sparql_{C.COLLECTED}"
LICENCE = "CC0 1.0 (Wikidata structured data)"
LICENCE_URL = "https://www.wikidata.org/wiki/Wikidata:Licensing"
SPLIT_TOTAL = {"train": 3000, "select": C.SPLIT_SIZES["select"], "test": C.SPLIT_SIZES["test"]}
KIND_MAX_SHARE = 0.24      # no fact kind above 25 % of a split
GOLD_CAP_SHARE = 0.03      # one gold value at most 3 % of a kind's items in a split (at least 2)
SPLIT_SHARE = 0.06         # select and test each take ~6 % of the subject QIDs
YEAR_SPAN = 15             # year distractors: gold +- 1..15, all distinct
THIS_YEAR = 2026
SCRUB = re.compile(r"nobel", re.I)


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def val(b: dict, k: str) -> str | None:
    v = b.get(k)
    return v["value"] if v else None


def bindings(name: str) -> list[dict]:
    return json.loads((RAW_DIR / f"{name}.json").read_bytes())["results"]["bindings"]


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


@functools.lru_cache(maxsize=None)
def words(t: str) -> frozenset[str]:
    """The checker's word set (normalised, words longer than 2 characters)."""
    return frozenset(w for w in re.sub(r"\W+", " ", str(t).lower()).split() if len(w) > 2)


@functools.lru_cache(maxsize=None)
def nkey(t: str) -> str:
    return re.sub(r"\W+", " ", str(t).lower()).strip()


def good_label(label: str | None, subject: str) -> bool:
    return bool(label) and not re.fullmatch(r"[QL]\d+", label) and len(label) <= 90 and not SCRUB.search(label) \
        and "?" not in label


TIME_RE = re.compile(r"^(-?)(\d{1,6})-(\d\d)-(\d\d)T")


def year_of(t: str, prec: str | int, lo: int, hi: int) -> int | None:
    """Year of a Wikidata time value with at least year precision, inside [lo, hi]. Day-precision dates on 1-12 January
    before 1924 are dropped: WDQS shows Julian dates converted to Gregorian, which can move them into the next year."""
    m = TIME_RE.match(t or "")
    if not m or int(prec) < 9:
        return None
    y = int(m.group(2)) * (-1 if m.group(1) else 1)
    if int(prec) >= 11 and m.group(3) == "01" and int(m.group(4)) <= 12 and y < 1924:
        return None
    return y if lo <= y <= hi else None


# --- question templates (own wording; at least five per kind). {s} = the subject as shown.
TEMPLATES = {
    "birth_year": ("In which year was {s} born?", "{s} was born in which year?", "What is the year of birth of {s}?",
                   "Give the birth year of {s}.", "Which year saw the birth of {s}?",
                   "Identify the year in which {s} was born."),
    "city_country": ("In which country is the city of {s} located?", "{s} is a city in which country?",
                     "Which country does the city of {s} belong to?", "Name the country in which the city {s} lies.",
                     "The city of {s} lies in which present-day country?", "Which sovereign state is {s} part of?"),
    "capital": ("What is the capital of {s}?", "Which city is the capital of {s}?", "{s} has which city as its capital?",
                "Name the capital city of {s}.", "Which of these is the capital of {s}?",
                "The capital of {s} is which city?"),
    "work_author": ("Who wrote the {n} {s}?", "Who is the author of the {n} {s}?", "The {n} {s} was written by whom?",
                    "Which writer is the author of the {n} {s}?", "Name the author of the {n} {s}.",
                    "{S} is a {n} by which author?"),
    "work_year": ("In which year was the {n} {s} published?", "What is the publication year of the {n} {s}?",
                  "The {n} {s} came out in which year?", "In what year did the {n} {s} appear in print?",
                  "Give the year of publication of the {n} {s}.", "When was the {n} {s} published? Choose the year."),
    "film_director": ("Who directed the {y} film {s}?", "Who was the director of the film {s} ({y})?",
                      "The {y} film {s} was directed by whom?", "Name the director of {s}, a film released in {y}.",
                      "Which filmmaker directed {s} ({y} film)?", "{S} ({y}) is a film by which director?"),
    "founding_year": ("In which year was {s} founded?", "What is the founding year of {s}?",
                      "{S} was established in which year?", "Give the year in which {s} was founded.",
                      "In what year was {s} established?", "When was {s} founded? Choose the year."),
    "mountain_range": ("Which mountain range is {s} part of?", "In which mountain range is {s} located?",
                       "{S} belongs to which mountain range?", "Name the mountain range that contains {s}.",
                       "{S} is a peak in which mountain range?", "Which range does the mountain {s} lie in?"),
    "opera_composer": ("Who composed the opera {s}?", "Which composer wrote the music of the opera {s}?",
                       "The opera {s} was composed by whom?", "Name the composer of the opera {s}.",
                       "{S} is an opera by which composer?", "Whose opera is {s}?"),
}
KINDS = tuple(TEMPLATES)
WORK_NOUN = {"Q8261": "novel", "Q25379": "play", "Q5185279": "poem", "Q49084": "short story"}


def quoted(t: str) -> str:
    return f"“{t}”"


# --- loading: one dict per candidate subject, {"qid", "kind", "show", "ctx", "answer", "sl", ...}

def load_laureates() -> set[str]:
    return {qid(b["p"]["value"]) for b in bindings("nobel_laureates")}


def load_countries() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for b in bindings("countries"):
        c = qid(b["c"]["value"])
        d = out.setdefault(c, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "cont": set(), "cap": {}})
        if val(b, "contl"):
            d["cont"].add(qid(val(b, "cont")))
        if val(b, "cap"):
            d["cap"][qid(val(b, "cap"))] = clean(val(b, "capl"))
    return out


def load_persons() -> list[dict]:
    per: dict[str, dict] = {}
    for name, _occ, _sl in OCCUPATIONS:
        for b in bindings(f"persons_{name}"):
            p = qid(b["p"]["value"])
            d = per.setdefault(p, {"label": clean(val(b, "l")), "desc": clean(val(b, "d")), "sl": int(val(b, "sl")),
                                   "st": {}})
            d["st"][val(b, "st")] = (val(b, "t"), val(b, "prec"))
    out, seen = [], collections.Counter()
    for p, d in per.items():
        desc = clean(re.sub(r"\([^)]*\)?", " ", d["desc"])).strip(" ,;:-–")
        desc = re.sub(r"^(an?|the) ", "", desc, flags=re.I)
        if not desc or re.search(r"\d|centur|born|died|nobel|\(|\)", desc, re.I) or not 3 <= len(desc) <= 70:
            continue
        d["desc"] = desc
        seen[(nkey(d["label"]), nkey(desc))] += 1
        if len(d["st"]) != 1:
            continue
        t, prec = next(iter(d["st"].values()))
        y = year_of(t, prec, 1500, 2005)
        if y is None:
            continue
        out.append({"qid": p, "kind": "birth_year", "show": f"{d['label']} ({desc})", "ctx": d["label"] + " " + desc,
                    "label": d["label"], "answer": y, "sl": d["sl"], "key": (nkey(d["label"]), nkey(desc))})
    return [x for x in out if seen[x["key"]] == 1]


def load_cities(countries: dict) -> list[dict]:
    per: dict[str, dict] = {}
    for b in bindings("cities"):
        c = qid(b["c"]["value"])
        d = per.setdefault(c, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "country": set()})
        if val(b, "country"):
            d["country"].add(qid(val(b, "country")))
    names = collections.Counter(nkey(d["label"]) for d in per.values())
    out = []
    for c, d in per.items():
        if names[nkey(d["label"])] != 1 or len(d["country"]) != 1:
            continue
        k = next(iter(d["country"]))
        if k not in countries or c in countries:
            continue
        out.append({"qid": c, "kind": "city_country", "show": d["label"], "ctx": d["label"], "label": d["label"],
                    "answer": k, "sl": d["sl"]})
    return out


def load_capitals(countries: dict) -> list[dict]:
    out = []
    for c, d in countries.items():
        if len(d["cap"]) == 1:
            cap, capl = next(iter(d["cap"].items()))
            if capl:
                out.append({"qid": c, "kind": "capital", "show": d["label"], "ctx": d["label"], "label": d["label"],
                            "answer": cap, "answer_label": capl, "pool": ("continent", tuple(sorted(d["cont"]))),
                            "sl": d["sl"]})
    per: dict[str, dict] = {}
    for b in bindings("regions"):
        r = qid(b["r"]["value"])
        d = per.setdefault(r, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "country": set(), "cap": {}})
        d["country"].add(qid(val(b, "country")))
        if val(b, "cap"):
            d["cap"][qid(val(b, "cap"))] = clean(val(b, "capl"))
    names = collections.Counter(nkey(d["label"]) for d in per.values())
    for r, d in per.items():
        if names[nkey(d["label"])] != 1 or len(d["country"]) != 1 or len(d["cap"]) != 1 or r in countries:
            continue
        k = next(iter(d["country"]))
        cap, capl = next(iter(d["cap"].items()))
        if k not in countries or not capl or cap == r:
            continue
        ctry = countries[k]["label"]
        out.append({"qid": r, "kind": "capital", "show": f"{d['label']} ({ctry})", "ctx": d["label"] + " " + ctry,
                    "label": d["label"], "answer": cap, "answer_label": capl, "pool": ("country", k), "sl": d["sl"]})
    return out


def load_works() -> tuple[list[dict], list[dict]]:
    per: dict[str, dict] = {}
    for b in bindings("works_author"):
        w = qid(b["w"]["value"])
        d = per.setdefault(w, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "cls": set(), "auth": {}})
        d["cls"].add(qid(val(b, "cls")))
        a = qid(val(b, "a"))
        d["auth"][a] = (clean(val(b, "al")), int(val(b, "aby")) if val(b, "aby") else None,
                        qid(val(b, "origin")) if val(b, "origin") else None)
    pub: dict[str, dict] = {}
    for b in bindings("works_pubdate"):
        w = qid(b["w"]["value"])
        d = pub.setdefault(w, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "st": {}})
        d["st"][val(b, "st")] = (val(b, "t"), val(b, "prec"))
    labels = {}
    for src in (per, pub):
        for w, d in src.items():
            labels[w] = nkey(d["label"])
    names = collections.Counter(labels.values())

    def noun(w: str) -> str:
        spec = sorted({WORK_NOUN[c] for c in per.get(w, {}).get("cls", ()) if c in WORK_NOUN})
        return spec[0] if len(spec) == 1 else "literary work"

    authors_out = []
    for w, d in per.items():
        if names[labels[w]] != 1 or len(d["auth"]) != 1:
            continue
        a, (al, aby, origin) = next(iter(d["auth"].items()))
        if not al or aby is None:
            continue
        authors_out.append({"qid": w, "kind": "work_author", "show": quoted(d["label"]), "ctx": d["label"],
                            "label": d["label"], "answer": a, "answer_label": al, "era": aby, "origin": origin,
                            "noun": noun(w), "sl": d["sl"]})
    years_out = []
    for w, d in pub.items():
        if names[labels[w]] != 1 or len(d["st"]) != 1:
            continue
        y = year_of(*next(iter(d["st"].values())), 1500, THIS_YEAR - 3)
        if y is None:
            continue
        show, ctx = quoted(d["label"]), d["label"]
        if w in per and len(per[w]["auth"]) == 1 and next(iter(per[w]["auth"].values()))[0]:
            al = next(iter(per[w]["auth"].values()))[0]
            show, ctx = f"{show} by {al}", f"{ctx} {al}"
        years_out.append({"qid": w, "kind": "work_year", "show": show, "ctx": ctx, "label": d["label"], "answer": y,
                          "noun": noun(w), "sl": d["sl"]})
    return authors_out, years_out


def load_films() -> list[dict]:
    per: dict[str, dict] = {}
    for b in bindings("films"):
        f = qid(b["f"]["value"])
        d = per.setdefault(f, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "dir": {}})
        d["dir"][qid(val(b, "dir"))] = (clean(val(b, "dirl")), int(val(b, "y")) if val(b, "y") else None,
                                         qid(val(b, "origin")) if val(b, "origin") else None)
    names = collections.Counter((nkey(d["label"]), next(iter(d["dir"].values()))[1]) for d in per.values())
    out = []
    for f, d in per.items():
        if len(d["dir"]) != 1:
            continue
        a, (al, y, origin) = next(iter(d["dir"].items()))
        if not al or y is None or not 1895 <= y <= THIS_YEAR or names[(nkey(d["label"]), y)] != 1:
            continue
        out.append({"qid": f, "kind": "film_director", "show": quoted(d["label"]), "ctx": d["label"], "label": d["label"],
                    "answer": a, "answer_label": al, "era": y, "origin": origin, "year": y, "sl": d["sl"]})
    return out


def load_universities(countries: dict) -> list[dict]:
    per: dict[str, dict] = {}
    for b in bindings("universities"):
        u = qid(b["u"]["value"])
        d = per.setdefault(u, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "st": {},
                               "country": qid(val(b, "country")) if val(b, "country") else None})
        d["st"][val(b, "st")] = (val(b, "t"), val(b, "prec"))
    names = collections.Counter(nkey(d["label"]) for d in per.values())
    out = []
    for u, d in per.items():
        if names[nkey(d["label"])] != 1 or len(d["st"]) != 1:
            continue
        y = year_of(*next(iter(d["st"].values())), 1000, THIS_YEAR - 6)
        if y is None:
            continue
        show = d["label"]
        ctry = countries.get(d["country"] or "", {}).get("label")
        if ctry and not words(ctry) & words(show):
            show = f"{show} ({ctry})"
        out.append({"qid": u, "kind": "founding_year", "show": show, "ctx": show, "label": d["label"], "answer": y,
                    "sl": d["sl"]})
    return out


def load_ranges() -> dict[str, set[str]]:
    """range -> its ancestors (P4552 / P361 chains) from the range_parents query."""
    anc: dict[str, set[str]] = collections.defaultdict(set)
    for b in bindings("range_parents"):
        anc[qid(b["r"]["value"])].add(qid(b["parent"]["value"]))
    return anc


def load_mountains(countries: dict) -> list[dict]:
    per: dict[str, dict] = {}
    for b in bindings("mountains"):
        m = qid(b["m"]["value"])
        d = per.setdefault(m, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "rng": {}, "country": None})
        d["rng"][qid(val(b, "rng"))] = clean(val(b, "rngl"))
        if val(b, "country") and not d["country"]:
            d["country"] = qid(val(b, "country"))
    names = collections.Counter(nkey(d["label"]) for d in per.values())
    out = []
    for m, d in per.items():
        if names[nkey(d["label"])] != 1 or len(d["rng"]) != 1:
            continue
        rg, rl = next(iter(d["rng"].items()))
        if not rl:
            continue
        cont = tuple(sorted(countries.get(d["country"] or "", {}).get("cont", ())))
        out.append({"qid": m, "kind": "mountain_range", "show": d["label"], "ctx": d["label"], "label": d["label"],
                    "answer": rg, "answer_label": rl, "country": d["country"], "cont": cont, "sl": d["sl"]})
    return out


def load_operas() -> list[dict]:
    per: dict[str, dict] = {}
    for b in bindings("operas"):
        o = qid(b["o"]["value"])
        d = per.setdefault(o, {"label": clean(val(b, "l")), "sl": int(val(b, "sl")), "c": {}, "origin": set()})
        c = d["c"].setdefault(qid(val(b, "c")), {"label": clean(val(b, "cl")), "years": set()})
        if val(b, "cb") and TIME_RE.match(val(b, "cb")):
            m = TIME_RE.match(val(b, "cb"))
            c["years"].add(int(m.group(2)) * (-1 if m.group(1) else 1))
        if val(b, "ctry"):
            d["origin"].add(qid(val(b, "ctry")))
    names = collections.Counter(nkey(d["label"]) for d in per.values())
    out = []
    for o, d in per.items():
        if names[nkey(d["label"])] != 1 or len(d["c"]) != 1:
            continue
        a, c = next(iter(d["c"].items()))
        if not c["label"] or not c["years"]:
            continue
        out.append({"qid": o, "kind": "opera_composer", "show": quoted(d["label"]), "ctx": d["label"],
                    "label": d["label"], "answer": a, "answer_label": c["label"], "era": min(c["years"]),
                    "origin": min(d["origin"]) if d["origin"] else None, "sl": d["sl"]})
    return out


# --- distractors

def year_options(gold: int, r: random.Random, hi: int) -> list[int]:
    """Four distinct years within gold +- 1..YEAR_SPAN (never above ``hi``); the number below the gold is drawn uniformly
    among the feasible counts, so the gold's rank among the five options carries no signal."""
    below = [gold - d for d in range(1, YEAR_SPAN + 1)]
    above = [gold + d for d in range(1, YEAR_SPAN + 1) if gold + d <= hi]
    k = r.randint(max(0, 4 - len(above)), min(4, len(below)))
    return r.sample(below, k) + r.sample(above, 4 - k)


def compatible(gold: str, cand: str, ctx: str) -> bool:
    """A distractor label differs from the gold (no shared or nested wording) and shares no word with the subject."""
    gw, cw = words(gold), words(cand)
    if nkey(gold) == nkey(cand) or nkey(gold) in nkey(cand) or nkey(cand) in nkey(gold):
        return False
    if gw and cw and (gw <= cw or cw <= gw):
        return False
    return not (cw & words(ctx))


def pick_entities(item: dict, tiers: list[list[tuple[str, str]]], weight: dict[str, int], r: random.Random,
                  exclude: set[str] = frozenset()) -> list[str] | None:
    """Four distractor labels: from the first tier first, then the next; within a tier drawn with weight (gold count +
    1) so that a value appears as a distractor about as often as it is a gold answer."""
    chosen: list[str] = []
    used_q = {item["answer"]} | set(exclude)
    used_l = {nkey(item["answer_label"])}
    for tier in tiers:
        cands = [(q, l) for q, l in tier if q not in used_q and nkey(l) not in used_l
                 and compatible(item["answer_label"], l, item["ctx"]) and good_label(l, "")]
        # unique by qid, stable order
        seen, uniq = set(), []
        for q, l in cands:
            if q not in seen:
                seen.add(q)
                uniq.append((q, l))
        while uniq and len(chosen) < 4:
            w = [weight.get(q, 0) + 1 for q, _ in uniq]
            i = r.choices(range(len(uniq)), weights=w)[0]
            q, l = uniq.pop(i)
            if nkey(l) in used_l or any(not compatible(c, l, "") for c in chosen):
                continue
            chosen.append(l)
            used_q.add(q)
            used_l.add(nkey(l))
        if len(chosen) == 4:
            return chosen
    return None


# --- items

def render(item: dict, pools: dict, r: random.Random) -> dict | None:
    kind = item["kind"]
    tpl = r.choice(TEMPLATES[kind])
    show = item["show"]
    text = tpl.format(s=show, S=show[0].upper() + show[1:], n=item.get("noun", ""), y=item.get("year", ""))
    if kind in ("birth_year", "work_year", "founding_year"):
        gold = str(item["answer"])
        opts = [gold] + [str(y) for y in year_options(item["answer"], r, THIS_YEAR - 1)]
    else:
        gold = item["answer_label"]
        if not good_label(gold, "") or words(gold) & words(item["ctx"]) or nkey(gold) in nkey(text):
            return None
        tiers, exclude = pools[kind](item)
        picked = pick_entities(item, tiers, pools["weight"][kind], r, exclude)
        if picked is None:
            return None
        opts = [gold] + picked
    if len({nkey(o) for o in opts}) != 5 or SCRUB.search(text) or any(SCRUB.search(o) for o in opts):
        return None
    criteria, expected = C.mc(opts, 0, r)
    return {"instructions": text, "criteria": criteria, "expected": expected}


def make_pools(cands: list[dict], countries: dict, anc: dict[str, set[str]]) -> dict:
    """Distractor tiers per kind (same type; same region or era first)."""
    weight = {k: collections.Counter(c["answer"] for c in cands if c["kind"] == k) for k in KINDS}
    clabel = {c: d["label"] for c, d in countries.items()}
    cont_of = {c: d["cont"] for c, d in countries.items()}

    def city_country(item):
        gc = cont_of[item["answer"]]
        same = [(c, clabel[c]) for c in countries if cont_of[c] & gc]
        return [same], set()

    nat_caps = [(c, next(iter(d["cap"].items()))) for c, d in countries.items() if len(d["cap"]) == 1]
    reg_caps = collections.defaultdict(list)
    for c in cands:
        if c["kind"] == "capital" and c["pool"][0] == "country":
            reg_caps[c["pool"][1]].append((c["answer"], c["answer_label"]))

    def capital(item):
        how, key = item["pool"]
        if how == "country":
            return [reg_caps[key]], set()
        return [[cap for c, cap in nat_caps if cont_of[c] & set(key) and cap[1]]], set()

    def people(kind: str, span: tuple[int, ...]):
        info: dict[str, dict] = {}
        for c in cands:
            if c["kind"] == kind:
                d = info.setdefault(c["answer"], {"label": c["answer_label"], "eras": [], "origins": set()})
                d["eras"].append(c["era"])
                if c.get("origin"):
                    d["origins"].add(c["origin"])
        era = {a: sorted(d["eras"])[len(d["eras"]) // 2] for a, d in info.items()}
        order = sorted(info)

        def tiers(item):
            gera, gor = era[item["answer"]], info[item["answer"]]["origins"]
            out = [[(a, info[a]["label"]) for a in order if abs(era[a] - gera) <= span[0] and info[a]["origins"] & gor]]
            out += [[(a, info[a]["label"]) for a in order if abs(era[a] - gera) <= w] for w in span]
            return out, set()
        return tiers

    rinfo: dict[str, dict] = {}
    for c in cands:
        if c["kind"] == "mountain_range":
            d = rinfo.setdefault(c["answer"], {"label": c["answer_label"], "countries": set(), "conts": set()})
            if c.get("country"):
                d["countries"].add(c["country"])
            d["conts"].update(c["cont"])
    rorder = sorted(rinfo)
    desc: dict[str, set[str]] = collections.defaultdict(set)
    for rr in sorted(anc):
        for a in sorted(anc[rr]):
            desc[a].add(rr)

    def mountain_range(item):
        # only leaf ranges (no known sub-range) as gold and as distractors, so that no option contains another
        if item["answer"] in desc:
            return [], set()
        g = rinfo[item["answer"]]
        excl = anc.get(item["answer"], set()) | set(desc)
        t1 = [(q, rinfo[q]["label"]) for q in rorder if rinfo[q]["countries"] & g["countries"]]
        t2 = [(q, rinfo[q]["label"]) for q in rorder if rinfo[q]["conts"] & g["conts"]]
        return [t1, t2], excl

    return {"city_country": city_country, "capital": capital, "work_author": people("work_author", (25, 50, 80)),
            "film_director": people("film_director", (10, 20)), "opera_composer": people("opera_composer", (25, 50)),
            "mountain_range": mountain_range, "weight": weight}


def waterfill(avail: dict[str, int], total: int, cap: int) -> dict[str, int]:
    lim = {k: min(a, cap) for k, a in avail.items()}
    ks = sorted(lim, key=lambda k: (lim[k], k))
    q, left = {}, total
    for i, k in enumerate(ks):
        q[k] = min(lim[k], left // (len(ks) - i))
        left -= q[k]
    for k in sorted(ks, key=lambda k: (-lim[k], k)):
        if left and q[k] < lim[k]:
            q[k] += 1
            left -= 1
    return q


def build(entries: list[dict]) -> None:
    laureates = load_laureates()
    countries = load_countries()
    for d in countries.values():
        d["cap"] = {k: v for k, v in d["cap"].items() if v}
    anc = load_ranges()
    works_a, works_y = load_works()
    cands = (load_persons() + load_cities(countries) + load_capitals(countries) + works_a + works_y + load_films()
             + load_universities(countries) + load_mountains(countries) + load_operas())
    for c in cands:
        if c["kind"] == "city_country":
            c["answer_label"] = countries[c["answer"]]["label"]
    cands = [c for c in cands if c["qid"] not in laureates and good_label(c["label"], c["qid"])
             and not SCRUB.search(c["show"] + " " + c["ctx"])]
    pools = make_pools(cands, countries, anc)

    # one fact kind per subject (a work is asked for its author or its year, never both)
    by_q: dict[str, list[dict]] = collections.defaultdict(list)
    for c in cands:
        by_q[c["qid"]].append(c)
    chosen = [min(v, key=lambda c: C.unit("kind", TASK, c["qid"], c["kind"])) for v in by_q.values()]

    # sitelink terciles per kind; order = bands interleaved, hash order inside a band
    per_kind: dict[str, list[dict]] = collections.defaultdict(list)
    for c in chosen:
        per_kind[c["kind"]].append(c)
    ordered: dict[str, list[dict]] = {}
    for k in KINDS:
        xs = sorted(per_kind[k], key=lambda c: (c["sl"], c["qid"]))
        n = len(xs)
        bands = [xs[: n // 3], xs[n // 3: 2 * n // 3], xs[2 * n // 3:]]
        bands = [sorted(b, key=lambda c: C.unit("pick", TASK, k, c["qid"])) for b in bands]
        ordered[k] = [b[i] for i in range(max(map(len, bands), default=0)) for b in bands if i < len(b)]

    rows_by_split: dict[str, list[dict]] = {}
    stats: dict[str, dict] = {}
    meta = C.dev_meta(TASK)
    for split, total in SPLIT_TOTAL.items():
        gold_cap = max(2, math.ceil(GOLD_CAP_SHARE * total / len(KINDS)))
        ready: dict[str, list[dict]] = {}
        for k in KINDS:
            used = collections.Counter()
            out = []
            for c in ordered[k]:
                if C.split_of(TASK, c["qid"], select=SPLIT_SHARE, test=SPLIT_SHARE) != split:
                    continue
                if used[c["answer"]] >= gold_cap:
                    continue
                q = render(c, pools, C.rng(TASK, k, c["qid"]))
                if q is None:
                    continue
                used[c["answer"]] += 1
                out.append(C.row(TASK, meta, SOURCE, c["qid"], [q], idk=True))
                if len(out) >= total:
                    break
            ready[k] = out
        quota = waterfill({k: len(v) for k, v in ready.items()}, total, int(KIND_MAX_SHARE * total))
        rows_by_split[split] = [r for k in KINDS for r in ready[k][: quota[k]]]
        stats[split] = {"available": {k: len(v) for k, v in ready.items()}, "used": quota}
    counts = C.write_splits(TASK, rows_by_split, SPLIT_TOTAL["train"])
    C.record_source(TASK, entries, LICENCE, LICENCE_URL, NOTES)
    print(json.dumps({"counts": counts, "per_kind": {s: v["used"] for s, v in stats.items()},
                      "available": {s: v["available"] for s, v in stats.items()}}, indent=1))


NOTES = ("Wikidata (CC0 1.0) through the public SPARQL endpoint " + ENDPOINT + ", queried on " + C.COLLECTED
         + ", one query at a time and at most one per minute (the endpoint's current rate limit), every query with a "
         "LIMIT; each file here is one query's raw JSON result, unmodified, and its URL holds the full query text. "
         "Wikidata is edited continuously: a fresh fetch on another machine or day can return different rows, so the "
         "build reads these saved files. Fact kinds: " + ", ".join(KINDS) + ". Only best-rank (truthy) statements are "
         "used and only subjects with exactly ONE value for the property; time values need year precision or better "
         "(day-precision dates on 1-12 January before 1924 are dropped because of the Julian-to-Gregorian conversion). "
         "Subjects need an English label; subjects whose label repeats within their kind (birth year: label plus "
         "description) are dropped as ambiguous. Nobel laureates (any rank of P166 for the six Nobel prizes) are never "
         "subjects and no text mentions Nobel (the dev set's source is the Nobel Prize API). Distractors: years = four "
         "distinct years within the gold +-1..15 (the gold's rank among the options is uniform); entities = four values "
         "of the same kind from the same continent / country / era first, weighted by how often a value is a gold "
         "answer, never sharing or nesting wording with the gold or the subject, and for mountain ranges never an "
         "ancestor or descendant range of the gold (gold and distractor ranges are leaf ranges, i.e. no other range in the data lies inside them). Group key (source_id) = the subject QID; split = sha256 of the "
         "QID; one fact kind per subject; per split each kind is filled from interleaved sitelink terciles (popular to "
         "obscure), one gold value at most 3 % of a kind, no kind above 24 % of a split.")


def main(argv: list[str]) -> None:
    entries = fetch_all()
    if "--fetch" in argv:
        return
    build(entries)


if __name__ == "__main__":
    main(sys.argv[1:])
