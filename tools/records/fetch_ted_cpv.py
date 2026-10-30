"""#17 EU public tenders: TED API v3 anonymous expert search (POST https://api.ted.europa.eu/v3/notices/search, no key),
the notices with English as an official language published 2026-01-01 to 2026-10-26, one query per calendar month in
PAGE_NUMBER mode, every result page stored unmodified (the request body of each page is kept in fetch.json "requests").

    python -I tools/records/fetch_ted_cpv.py [--snapshot 2026-10-27]

Documented limits (api-v3.yaml, "Definition of limits"): at most 250 notices per page, at most 10,000 fields per page
(fields x limit), at most 15,000 retrievable notices per query in PAGE_NUMBER mode (a month holds about 3,500). The script
pages politely: one request at a time and PAUSE_S after each. Pages already recorded are skipped, so a rerun resumes.
Only the fields the build needs are requested; ``notice-title`` is not, since TED composes it from the main CPV code's name.

The official English names of the 45 CPV divisions (CPV 2008, Regulation (EC) No 213/2008) are stored too, as the answer of
the EU Publications Office's public SPARQL endpoint (one GET), so that the builder's division map is tested against them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ted_cpv"
API = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = ["publication-number", "publication-date", "notice-type", "form-type", "title-proc", "description-proc",
          "classification-cpv", "main-classification-proc", "procedure-identifier", "official-language", "buyer-country"]
LIMIT = 250                                 # documented maximum notices per page
MAX_PER_QUERY = 15000                       # documented PAGE_NUMBER limit
FIRST, LAST = dt.date(2026, 1, 1), dt.date(2026, 10, 26)
PAUSE_S = 1.0
RETRY_WAITS = (10, 30, 90, 240)
LICENCE = {"name": "Commission Decision 2011/833/EU (reuse of Commission documents)",
           "url": "https://eur-lex.europa.eu/eli/dec/2011/833/oj/eng",
           "notice": "Source: TED - Tenders Electronic Daily, (c) European Union, https://ted.europa.eu"}
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
DIVISIONS = ("03", "09", "14", "15", "16", "18", "19", "22", "24", "30", "31", "32", "33", "34", "35", "37", "38", "39", "41",
             "42", "43", "44", "45", "48", "50", "51", "55", "60", "63", "64", "65", "66", "70", "71", "72", "73", "75", "76",
             "77", "79", "80", "85", "90", "92", "98")
GB = 1024 ** 3
MIN_FREE, EXPECTED = 40 * GB, int(0.5 * GB)
assert LIMIT * len(FIELDS) <= 10000


def cpv_list_url() -> str:
    values = " ".join(f"<http://data.europa.eu/cpv/cpv/{d}000000>" for d in DIVISIONS)
    q = ("PREFIX skos: <http://www.w3.org/2004/02/skos/core#> SELECT ?c ?label WHERE { VALUES ?c { " + values +
         " } ?c skos:prefLabel ?label . FILTER(lang(?label) = \"en\") } ORDER BY ?c")
    return SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "application/sparql-results+json"})


def months() -> list[tuple[dt.date, dt.date]]:
    out, d = [], FIRST
    while d <= LAST:
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append((d, min(nxt - dt.timedelta(days=1), LAST)))
        d = nxt
    return out


def body(first: dt.date, last: dt.date, page: int) -> str:
    q = (f"publication-date>={first.strftime('%Y%m%d')} AND publication-date<={last.strftime('%Y%m%d')} "
         f"AND official-language IN (ENG)")
    return json.dumps({"query": q, "fields": FIELDS, "page": page, "limit": LIMIT, "scope": "ALL",
                       "paginationMode": "PAGE_NUMBER", "checkQuerySyntax": False}, sort_keys=True)


def post(snapshot: str, req: str, name: str) -> str:
    d = R.raw_dir(DOMAIN, snapshot)
    log_path = os.path.join(d, "fetch.json")
    if os.path.exists(log_path) and name in json.load(open(log_path))["files"] and os.path.exists(os.path.join(d, name)):
        return os.path.join(d, name)
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            print(f"  waiting {wait} s before retry {attempt} of {name}", flush=True)
            time.sleep(wait)
        try:
            path = R.fetch_file(DOMAIN, snapshot, API, name, data=req.encode(), timeout=300,
                                headers={"Content-Type": "application/json", "Accept": "application/json"})
            log = json.load(open(log_path))
            log.setdefault("requests", {})[name] = req
            json.dump(log, open(log_path, "w"), indent=1)
            time.sleep(PAUSE_S)
            return path
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} on {name}: {exc.read()[:300]!r}", flush=True)
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {type(exc).__name__} on {name}: {exc}", flush=True)
        time.sleep(PAUSE_S)
    raise SystemExit(f"{name}: giving up; rerun later to resume")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free = shutil.disk_usage("/").free
    if free - EXPECTED < MIN_FREE:
        raise SystemExit(f"only {free / GB:.1f} GB free on /: stopping (needs {MIN_FREE / GB:.0f} GB to remain)")
    total = 0
    for first, last in months():
        page = 1
        while True:
            name = f"notices/{first.strftime('%Y-%m')}.p{page:03d}.json"
            res = json.load(open(post(a.snapshot, body(first, last, page), name)))
            n, tot = len(res.get("notices", [])), res.get("totalNoticeCount", 0)
            total += n
            print(f"{first:%Y-%m} page {page}: {n} notices of {tot}", flush=True)
            if tot > MAX_PER_QUERY:
                raise SystemExit(f"{first:%Y-%m}: {tot} notices, over the {MAX_PER_QUERY} PAGE_NUMBER limit; split the window")
            if n == 0 or page * LIMIT >= tot:
                break
            page += 1
    cpv = json.load(open(R.fetch_file(DOMAIN, a.snapshot, cpv_list_url(), "cpv_divisions.sparql.json", timeout=120,
                                      headers={"Accept": "application/sparql-results+json"})))
    print(f"official CPV division names: {len(cpv['results']['bindings'])}")
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    log["query"] = {"api": API, "fields": FIELDS, "limit": LIMIT, "windows": [[f.isoformat(), l.isoformat()] for f, l in months()],
                    "filter": "official-language IN (ENG)"}
    json.dump(log, open(path, "w"), indent=1)
    size = sum(f["bytes"] for f in log["files"].values())
    print(f"{total} notices on {len(log['files'])} pages, {size / 1e6:.1f} MB stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
