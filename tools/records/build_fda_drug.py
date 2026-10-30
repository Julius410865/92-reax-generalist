"""#7 FDA drug products -> marketing status: eval-v5.1 mirror rows (part N, task type ``fda_drug_marketing_status``).

    python -I tools/records/build_fda_drug.py --snapshot 2026-10-27

Records: the products of the openFDA drugsfda bulk file (Drugs@FDA), read from the raw zip as data. One product = one record.
* Label: the product's ``products[].marketing_status`` field only. Kept: Prescription, Over-the-counter, Discontinued and
  None (Tentative Approval), the four current Drugs@FDA marketing statuses (each is the product's status today, as the
  question asks). Dropped: products without a status (none in the 2026-10-27 file) and records whose rendered text is
  identical to another record's with a different status (conflicting).
* Record text: application type, drug (brand) name, active ingredients with their strengths (the generic name), dosage form,
  route, sponsor (a company). Not used: marketing status, the ``submissions`` (submission status TA / AP and their dates),
  ``te_code`` and ``reference_drug`` / ``reference_standard`` (only marketed products carry TE codes), the ``openfda`` block
  (present only for products with a current label), and the notes appended to a strength (stripped): ``**Federal Register
  determination that product was not discontinued ...**`` (discontinued products only) and ``**See current Annual
  Edition ...`` (listed levothyroxine products only). Dosage form and route are upper-cased (a few later entries are in
  mixed case, mostly discontinued products).
* Dropped as unrenderable: products without a route (81 % of them are tentative approvals, so a missing route would be a
  cue), without a dosage form, a drug name or active ingredients, or with an ingredient without a strength (also mostly
  tentative approvals). A record any of whose fields contains a word of ``SCRUB`` is dropped (brand names such as
  "PRILOSEC OTC" or "NEO-RX", the sponsor "CHARTWELL RX").
* Group key: the application number (NDA / ANDA / BLA), so all products of one application stay in one split. Records with
  identical text and the same status are kept once (the lowest product key).
* Fresh: the application's original submission (ORIG) status date, on or after 2026-08-01.
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
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "fda_drug"
TASK = "fda_drug_marketing_status"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.05            # a large domain (tens of thousands of products): about 5 % test and 5 % select
# The class cap draws its records in a hash order of its own (with the take's order a capped class keeps the front of
# the take order and the take of at most 3,000 / 150 refills it, undoing the cap). Here no class reaches the cap.
CAP_ORDER = f"{DOMAIN}|cap"
LABELS = {"Prescription": "Prescription: on the market, dispensed only with a prescription",
          "Over-the-counter": "Over-the-counter: on the market, sold without a prescription",
          "Discontinued": "Discontinued: no longer on the market",
          "None (Tentative Approval)": "Tentative approval only: may not be sold yet"}
APP_TYPES = {"NDA": "NDA (new drug application)", "ANDA": "ANDA (abbreviated new drug application, generic drug)",
             "BLA": "BLA (biologics license application)"}
SCRUB = ("prescription", "prescriptions", "nonprescription", "non-prescription", "over-the-counter", "over the counter",
         "otc", "rx", "discontinued", "discontinue", "discontinuation", "withdrawn", "withdrawal", "tentative",
         "tentatively", "approval", "approved", "approvable", "unapproved", "marketed", "marketing", "market",
         "federal register", "no longer", "inactive", "obsolete", "status")
SCRUB_RE = R.scrub_pattern(SCRUB)
# Drugs@FDA / Orange Book notes appended to a strength, closed or not: "**Federal Register determination that product was
# not discontinued ...**" (discontinued products only), "**See current Annual Edition, 1.8 Description of Special
# Situations, Levothyroxine Sodium" (listed products only). Notes, not strengths, and both tell the status.
NOTE_RE = re.compile(r"\*+[^*]*(?:\*+|$)")
QUESTIONS = ("What is the marketing status of this drug product today?",
             "Which marketing status does Drugs@FDA list for this product now?",
             "How is this drug product listed in Drugs@FDA today?",
             "Which of these is the product's current marketing status?",
             "Where does this drug product stand today?")


def load(raw: str) -> list[dict]:
    zp = sorted(glob.glob(os.path.join(raw, "drug-drugsfda-*.json.zip")))
    if not zp:
        raise SystemExit(f"no drugsfda partition in {raw}")
    out = []
    for p in zp:
        with zipfile.ZipFile(p) as zf:
            for name in sorted(zf.namelist()):
                if name.endswith(".json"):
                    out += json.loads(zf.read(name))["results"]
    return out


def strength(s: str) -> str:
    return R.norm_ws(NOTE_RE.sub(" ", s or ""))


def orig_date(app: dict) -> dt.date | None:
    dates = sorted(s.get("submission_status_date") or "" for s in app.get("submissions") or []
                   if s.get("submission_type") == "ORIG" and re.fullmatch(r"\d{8}", s.get("submission_status_date") or ""))
    if not dates:
        return None
    d = dates[0]
    return dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))


def render_record(app: dict, prod: dict) -> str | None:
    """The record text (no question), or None if a field is missing or contains a SCRUB word."""
    num = app.get("application_number") or ""
    kind = re.match(r"[A-Z]+", num)
    kind = kind.group(0) if kind else ""
    name = R.norm_ws(prod.get("brand_name"))
    form = R.norm_ws(prod.get("dosage_form")).upper()
    route = R.norm_ws(prod.get("route")).upper()
    sponsor = R.norm_ws(app.get("sponsor_name"))
    ais = prod.get("active_ingredients") or []
    pairs = [(R.norm_ws(a.get("name")), strength(a.get("strength"))) for a in ais]
    if kind not in APP_TYPES or not (name and form and route and sponsor and pairs) or not all(n and s for n, s in pairs):
        return None
    ingr = "; ".join(f"{n} ({s})" for n, s in pairs)
    lines = ["FDA drug product",
             f"Application type: {APP_TYPES[kind]}",
             f"Drug name: {name}",
             f"Active ingredient{'s' if len(pairs) > 1 else ''} and strength{'s' if len(pairs) > 1 else ''}: {ingr}",
             f"Dosage form: {form}",
             f"Route: {route}",
             f"Sponsor: {sponsor}"]
    record = "\n".join(lines)
    if R.scrub_hits(record, SCRUB_RE):
        return None
    return record


def records(raw: str) -> tuple[list[dict], int]:
    out, n_read = [], 0
    for app in load(raw):
        num = app.get("application_number") or ""
        day = orig_date(app)
        for prod in app.get("products") or []:
            n_read += 1
            status = prod.get("marketing_status")
            if status not in LABELS:
                continue
            out.append({"app": num, "prod": prod.get("product_number") or "", "status": status, "date": day,
                        "record": render_record(app, prod), "key": f"{num}-{prod.get('product_number') or ''}"})
    return out, n_read


def dedupe(recs: list[dict]) -> tuple[list[dict], int, int]:
    """One record per distinct text: kept once if all copies agree on the status, dropped if they conflict."""
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
    recs, n_read = records(raw)
    unrendered = sum(r["record"] is None for r in recs)
    kept, dup, conflict = dedupe([r for r in recs if r["record"] is not None])
    for rec in kept:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        rec["text"] = rec["record"] + "\n\n" + rng.choice(QUESTIONS)
        rec["split"] = R.split_of(DOMAIN, rec["app"], EVAL_FRAC)
    capped, class_report = R.cap_classes(kept, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["status"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["status"]], source=DOMAIN,
                             source_id=rec["key"], snapshot=snapshot, record_date=rec["date"], shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "export_date": fetch.get("export_date"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "products[].marketing_status", "labels": {k: LABELS[k] for k in LABELS if k in present},
                "group_key": "application_number", "eval_frac": EVAL_FRAC, "records_read": n_read,
                "records_with_label": len(recs), "dropped_unrenderable_or_scrub": unrendered,
                "dropped_duplicate_text": dup, "dropped_conflicting_text": conflict, "records_kept": len(kept),
                **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    """The application's Drugs@FDA overview page (it lists every product with its marketing status)."""
    num = row["source_id"].rsplit("-", 1)[0]
    return ("https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo="
            + re.sub(r"\D", "", num))


_APPS: dict[str, dict[str, dict]] = {}


def _apps(snapshot: str) -> dict[str, dict]:
    """application number -> application object of the raw bulk file, read once per process."""
    if snapshot not in _APPS:
        out = {}
        for p in sorted(glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "drug-drugsfda-*.json.zip"))):
            with zipfile.ZipFile(p) as zf:
                for name in zf.namelist():
                    for app in json.loads(zf.read(name)).get("results", []):
                        out[app.get("application_number")] = app
        _APPS[snapshot] = out
    return _APPS[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The marketing status read again from the raw file (a direct lookup of application and product number, not the
    builder's filters), and whether the item shows that product's own drug name, dosage form and sponsor."""
    num, prod_no = row["source_id"].rsplit("-", 1)
    app = _apps(snapshot).get(num)
    if app is None:
        return None, False
    prods = [p for p in app.get("products") or [] if p.get("product_number") == prod_no]
    if len(prods) != 1:
        return None, False
    p = prods[0]
    text = row["questions"][0]["instructions"]
    text_ok = (f"Drug name: {R.norm_ws(p.get('brand_name'))}\n" in text
               and f"Dosage form: {R.norm_ws(p.get('dosage_form')).upper()}\n" in text
               and f"Sponsor: {R.norm_ws(app.get('sponsor_name'))}\n" in text)
    return LABELS.get(p.get("marketing_status")), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), classes {m['splits'][s]['class_prior']}, "
              f"gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']}, dropped (scrub / missing field) {m['dropped_unrenderable_or_scrub']}, "
          f"duplicate text {m['dropped_duplicate_text']}, conflicting text {m['dropped_conflicting_text']}, kept "
          f"{m['records_kept']}, classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
