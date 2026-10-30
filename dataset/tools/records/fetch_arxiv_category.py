"""Fetch the raw OpenAlex works for the T type ``arxiv_category`` (paper title + abstract -> its research field).

    python -I tools/records/fetch_arxiv_category.py

Source: the OpenAlex REST API (https://api.openalex.org, data CC0). No API key, no login and no e-mail address are sent
(no ``mailto``, no ``api_key``): the keyless tier allows 10 requests per second and a daily budget of $0.10 per network
(1,000 list calls at 1 credit each, per https://help.openalex.org/api/authentication/ and
https://help.openalex.org/access/example-costs/). This script makes one request at a time with ``PAUSE_S`` between requests,
stops when fewer than ``MIN_REMAINING`` credits are left today, and needs about 105 credits in all.

Cursor paging past the first page needs an API key since 2026 (https://help.openalex.org/api/paging/), so it is not used.
Instead, per OpenAlex field (the 26 fields of the topic hierarchy), one seeded random sample (``sample=PER_FIELD``,
``seed=SEED``) of works is read with basic paging (``page=1..4``, ``per_page=100``; documented keyless up to 10,000 results).
The sample spreads over the subfields and topics of each field. The server-side filters only narrow the sample; the builder
applies every exclusion again on the stored records (arXiv locations, licence, language, abstract).

Every response is stored unmodified in data/generalist/raw/arxiv_category/ and listed in SOURCE.json with its URL, fetch time,
size and sha256. Files already listed there are not fetched again, so a rerun resumes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.records import common as C  # noqa: E402

TASK = "arxiv_category"
API = "https://api.openalex.org"
SNAPSHOT = "2026-10-28"
SEED = 92
PER_FIELD = 400                 # works sampled per field (4 pages of 100)
PER_PAGE = 100                  # documented maximum
PAUSE_S = 1.0                   # one request per second; the keyless limit is 10 per second
RETRY_WAITS = (10, 30, 90, 240)
MIN_REMAINING = 150             # stop before the shared keyless daily budget (1,000 credits) runs low
GB = 1024 ** 3
MIN_FREE = 40 * GB
FIELD_IDS = tuple(range(11, 37))   # OpenAlex fields 11..36 (26 fields); checked against /fields below

ARXIV_SOURCE = "S4306400194"    # "arXiv (Cornell University)" in OpenAlex sources
FILTERS = (
    "type:article",
    "language:en",
    "has_abstract:true",
    "is_retracted:false",
    "indexed_in:!arxiv",
    f"locations.source.id:!{ARXIV_SOURCE}",
    "primary_location.source.type:journal",
    "primary_location.license:cc-by|cc-by-sa|public-domain",
    "from_publication_date:2010-01-01",
    "to_publication_date:2026-07-31",
)
SELECT = ("id", "doi", "title", "display_name", "publication_year", "publication_date", "language", "type", "ids",
          "indexed_in", "primary_topic", "topics", "primary_location", "best_oa_location", "locations", "locations_count",
          "open_access", "is_retracted", "abstract_inverted_index")

LICENCE = ("CC0 1.0 (OpenAlex data: titles, abstracts as inverted indexes, topics, ids). Only works whose publisher "
           "version (primary_location) carries a CC BY, CC BY-SA or public-domain licence in OpenAlex are used, so the "
           "abstract texts are openly licensed as well (CC BY / CC BY-SA require attribution: every row's source_id is the "
           "OpenAlex work id, which resolves to the DOI and the licence)")
LICENCE_URL = "https://help.openalex.org/access/pricing/#free-data-paid-services (CC0: https://creativecommons.org/publicdomain/zero/1.0/)"


def works_url(field: int, page: int) -> str:
    q = {"filter": ",".join((f"primary_topic.field.id:fields/{field}",) + FILTERS), "select": ",".join(SELECT),
         "sample": str(PER_FIELD), "seed": str(SEED), "per_page": str(PER_PAGE), "page": str(page)}
    return f"{API}/works?" + urllib.parse.urlencode(q, safe=":,|!/")


def source_path() -> Path:
    return C.RAW / TASK / "SOURCE.json"


def load_source() -> dict:
    p = source_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"task": TASK, "licence": LICENCE, "licence_url": LICENCE_URL, "downloaded": SNAPSHOT, "files": {}, "notes": ""}


def save_source(src: dict) -> None:
    source_path().write_text(json.dumps(src, indent=1, ensure_ascii=False) + "\n")


def get(src: dict, url: str, name: str) -> Path:
    """GET ``url`` into raw/<task>/<name> unmodified (skipped when SOURCE.json already lists it with a matching sha256)."""
    assert "@" not in url and "mailto" not in url and "api_key" not in url, url
    d = C.RAW / TASK
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    if name in src["files"] and p.exists():
        if hashlib.sha256(p.read_bytes()).hexdigest() != src["files"][name]["sha256"]:
            raise SystemExit(f"{p}: sha256 differs from SOURCE.json")
        return p
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            print(f"  waiting {wait} s before retry {attempt} of {name}", flush=True)
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body, status, hdr = r.read(), r.status, r.headers
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} on {name}: {exc.read()[:300]!r}", flush=True)
            if exc.code in (401, 403):
                raise SystemExit(f"{name}: HTTP {exc.code}; OpenAlex refused a keyless request, stopping (no key is used)")
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(PAUSE_S)
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {type(exc).__name__} on {name}: {exc}", flush=True)
            time.sleep(PAUSE_S)
            continue
        json.loads(body)                     # must be JSON; stored as received
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(body)
        tmp.rename(p)
        src["files"][name] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "status": status,
                              "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "credits_used": hdr.get("X-RateLimit-Credits-Used")}
        save_source(src)
        remaining = hdr.get("X-RateLimit-Remaining")
        time.sleep(PAUSE_S)
        if remaining is not None and int(remaining) < MIN_REMAINING:
            raise SystemExit(f"only {remaining} keyless credits left today; stopping, rerun after the reset to resume")
        return p
    raise SystemExit(f"{name}: giving up; rerun later to resume")


def main() -> None:
    free = shutil.disk_usage(C.RAW.parent).free if C.RAW.parent.exists() else shutil.disk_usage("/").free
    if free < MIN_FREE:
        raise SystemExit(f"only {free / GB:.1f} GB free: stopping (needs {MIN_FREE / GB:.0f} GB)")
    src = load_source()
    p = get(src, f"{API}/fields?per_page=100&select=id,display_name,domain,subfields", "fields.json")
    fields = {int(f["id"].rsplit("/", 1)[1]): f["display_name"] for f in json.loads(p.read_text())["results"]}
    if tuple(sorted(fields)) != FIELD_IDS:
        raise SystemExit(f"OpenAlex fields changed: {sorted(fields)}")
    n = 0
    for field in FIELD_IDS:
        got = 0
        for page in range(1, PER_FIELD // PER_PAGE + 1):
            res = json.loads(get(src, works_url(field, page), f"works__field-{field}__seed-{SEED}__page-{page}.json").read_text())
            got += len(res.get("results") or [])
            if len(res.get("results") or []) < PER_PAGE:
                break
        n += got
        print(f"field {field} {fields[field]}: {got} works", flush=True)
    src.update(task=TASK, licence=LICENCE, licence_url=LICENCE_URL, downloaded=SNAPSHOT)
    src["notes"] = (
        "OpenAlex works API, keyless (no api_key, no mailto; nothing identifying the owner is sent). Per OpenAlex field "
        f"11..36: a seeded random sample (sample={PER_FIELD}, seed={SEED}) read with basic paging (per_page={PER_PAGE}, "
        "pages 1..4); cursor paging past page 1 needs an API key, so it is not used. Server-side filters: "
        + ", ".join(FILTERS) + f". Fields selected: {', '.join(SELECT)}. fields.json is the OpenAlex field list "
        "(the label set). Gold = primary_topic.field of each work: a structured OpenAlex field, assigned by OpenAlex's own "
        "topic classifier (https://help.openalex.org/data/topics/#assigning-topics-to-works), not by this build. Every "
        "response is stored unmodified; the builder re-applies the exclusions (any location or id on arXiv, licence, "
        "language, abstract quality) on the stored records.")
    src["sampling"] = {"api": API, "seed": SEED, "per_field": PER_FIELD, "per_page": PER_PAGE, "fields": list(FIELD_IDS),
                       "filters": list(FILTERS), "select": list(SELECT), "paging": "basic (page=1..4), keyless"}
    save_source(src)
    print(f"{n} works on {len(src['files']) - 1} pages, "
          f"{sum(f['bytes'] for f in src['files'].values()) / 1e6:.1f} MB stored in {C.RAW / TASK}")


if __name__ == "__main__":
    main()
