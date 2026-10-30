"""#10 Medical-device recalls -> recall class: eval-v5.1 mirror rows (part N, task type ``fda_device_recall_class``).

    python -I tools/records/build_fda_device_recall.py --snapshot 2026-10-27

Records: the openFDA device enforcement bulk file (FDA enforcement reports of device recalls), read from the raw zip as data.
* Label: the structured ``classification`` field only: Class I, Class II, Class III. Dropped: "Not Yet Classified", and every
  recall event whose products carry different classes (conflicting labels inside one group).
* One record per recall event (``event_id``): an event lists one product per recall number, with the same reason for recall
  and near-identical product texts, so only the event's first renderable product in hash order of its recall number is
  used (no near-copies inside a split, every row a different recall). The recall initiation date and the recalling firm
  (a company) are shown in the header.
* Record text: product description, reason for recall, distribution pattern, each cut at a sentence boundary (a product
  list or distribution list with no sentence end in reach is cut at its last list item that fits, marked " ...").
  Not used: classification, center_classification_date, status, termination_date, voluntary_mandated,
  initial_firm_notification (a press release goes with the most serious recalls), product_quantity, code_info, the firm's
  address and the ``openfda`` block (device class 1 / 2 / 3 of the product code). Every sentence that contains a word of
  ``SCRUB`` (the class names, "classification", and the health-hazard wording of FDA's class definitions: "serious adverse
  health consequences or death", "medically reversible", "remote probability", "not likely to cause", death, serious
  injury, life-threatening ...) is removed; a record without a reason left is dropped. Names after a title (Dr. / Mr. /
  Mrs. / Ms.: surgeons' custom packs), e-mail addresses and phone numbers are masked.
* Group key: the recall event id, so all products of one event stay in one split.
* Balance: classes capped at 3x the median class count per split (``R.cap_classes`` in its own hash order, see
  ``CAP_ORDER``), then at most 3,000 / 150 / 150 rows by hash order (``R.take``).
* Fresh: the enforcement report date (the day the classified record was published), on or after 2026-08-01.
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

DOMAIN = "fda_device_recall"
TASK = "fda_device_recall_class"
AREA = "language"           # severity / class domain
EVAL_FRAC = 0.05            # over 3,300 kept records (one per recall event): about 5 % test and 5 % select
# The class cap draws its records in a hash order of its own. With the take's order (R.cap_classes(..., DOMAIN)), the records
# a capped class keeps are the front of the take order, so the take of 3,000 / 150 refills it and undoes the cap (train
# came out at Class II's raw 89 %). A different order keeps the capped mix through the take.
CAP_ORDER = f"{DOMAIN}|cap"
PRODUCT_LIMIT, REASON_LIMIT, DIST_LIMIT = 600, 900, 250
LABELS = {"Class I": "Class I (most serious: may cause serious harm or death)",
          "Class II": "Class II (may cause temporary or reversible harm)",
          "Class III": "Class III (unlikely to cause harm)"}
SCRUB = ("class i", "class ii", "class iii", "class 1", "class 2", "class 3", "class one", "class two", "class three",
         "classification", "classifications", "classified", "classify", "reclassified", "reclassification",
         "health hazard", "health hazards", "adverse health consequence", "adverse health consequences",
         "serious adverse", "reasonable probability", "remote probability", "medically reversible",
         "not likely to cause", "unlikely to cause", "most serious", "death", "deaths", "died", "fatal", "fatality",
         "fatalities", "mortality", "life-threatening", "life threatening", "serious injury", "serious injuries",
         "seriously injured", "serious harm")
SCRUB_RE = R.scrub_pattern(SCRUB)
QUESTIONS = ("Which recall class did FDA assign to this recall?",
             "How did FDA rank the seriousness of this device recall?",
             "Which FDA recall class applies to this product?",
             "What is the FDA recall class of this action?",
             "Which of these recall classes did FDA give this recall?")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\(\d{3}\)\s?\d{3}[-. ]\d{4}(?!\d)"                                   # (301) 504-7052
                      r"|(?<![\w-])(?:\+?1[-. ]?|[l1]-)?\d{3}[-. /]\d{3}[-. ]\d{4}(?!\d)")    # 1-800-638-2772, 800/638-2772
TITLED_NAME_RE = re.compile(r"\b(Dr|Mr|Mrs|Ms|Miss)(\.?\s+)"
                            r"([A-Z][A-Za-z'-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z][A-Za-z'-]*){0,2})")


def mask(text: str) -> str:
    """E-mail addresses and phone numbers -> [email] / [phone]; a name after Dr. / Mr. / Mrs. / Ms. -> [name] (not when
    "Dr" is a street suffix, i.e. a house number comes shortly before it)."""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)

    def name(m: re.Match) -> str:
        before = text[max(0, m.start() - 40):m.start()].split()[-3:]
        if m.group(1) == "Dr" and any(re.search(r"\d", w) for w in before):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}[name]"
    return TITLED_NAME_RE.sub(name, text)


def clip_list(text: str, limit: int) -> str:
    """``R.clip`` (a sentence boundary); a list with no sentence end in reach is cut after its last item that fits."""
    out = R.clip(text, limit)
    if out:
        return out
    cut = R.norm_ws(text)[:limit - 4]
    for sep in ("; ", ", ", " "):
        i = cut.rfind(sep)
        if i > limit // 3:
            return cut[:i].rstrip(" ,;:") + " ..."
    return ""


def part(text: str, limit: int) -> str:
    return clip_list(mask(R.drop_sentences(text or "", SCRUB_RE)), limit)


def load(raw: str) -> list[dict]:
    zp = sorted(glob.glob(os.path.join(raw, "device-enforcement-*.json.zip")))
    if not zp:
        raise SystemExit(f"no device enforcement partition in {raw}")
    out = []
    for p in zp:
        with zipfile.ZipFile(p) as zf:
            for name in sorted(zf.namelist()):
                if name.endswith(".json"):
                    out += json.loads(zf.read(name))["results"]
    return out


def ymd(s: str) -> dt.date | None:
    s = s or ""
    if not re.fullmatch(r"\d{8}", s):
        return None
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def render_record(r: dict) -> str | None:
    firm = R.norm_ws(r.get("recalling_firm"))
    started = ymd(r.get("recall_initiation_date"))
    product = part(r.get("product_description"), PRODUCT_LIMIT)
    reason = part(r.get("reason_for_recall"), REASON_LIMIT)
    dist = part(r.get("distribution_pattern"), DIST_LIMIT)
    if not (firm and product and reason) or R.scrub_hits(firm, SCRUB_RE):
        return None
    head = "Medical device recall (" + (f"initiated {started.isoformat()}; " if started else "") + f"recalling firm: {firm})"
    lines = [head, f"Product: {product}", f"Reason for recall: {reason}"]
    if dist:
        lines.append(f"Distribution: {dist}")
    record = "\n".join(lines)
    if R.scrub_hits(record, SCRUB_RE):
        return None
    return record


def records(raw: str) -> tuple[list[dict], dict]:
    """One record per recall event with a single class: its first renderable product in hash order of recall number."""
    events: dict[str, list[dict]] = {}
    n_read = 0
    for r in load(raw):
        n_read += 1
        events.setdefault(str(r.get("event_id") or ""), []).append(r)
    out, stats = [], {"records_read": n_read, "events": len(events), "events_unclassified": 0,
                      "events_conflicting_class": 0, "events_unrenderable_or_scrub": 0}
    for ev in sorted(events):
        rs = events[ev]
        classes = {r.get("classification") for r in rs}
        if not ev or not classes <= set(LABELS):
            stats["events_unclassified"] += 1
            continue
        if len(classes) > 1:
            stats["events_conflicting_class"] += 1
            continue
        for r in sorted(rs, key=lambda r: R.hash_order(DOMAIN, r.get("recall_number"))):
            record = render_record(r)
            if record is not None:
                out.append({"event": ev, "recall_number": r["recall_number"], "status": r["classification"],
                            "date": ymd(r.get("report_date")), "record": record, "key": f"event-{ev}"})
                break
        else:
            stats["events_unrenderable_or_scrub"] += 1
    return out, stats


def dedupe(recs: list[dict]) -> tuple[list[dict], int, int]:
    """One record per distinct text: kept once if all copies agree on the class, dropped if they conflict."""
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
        rec["split"] = R.split_of(DOMAIN, rec["event"], EVAL_FRAC)
    capped, class_report = R.cap_classes(kept, lambda r: r["status"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["status"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["status"]], source=DOMAIN,
                             source_id=rec["recall_number"], snapshot=snapshot, record_date=rec["date"],
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "export_date": fetch.get("export_date"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "classification", "labels": {k: LABELS[k] for k in LABELS if k in present},
                "group_key": "event_id (one record per event)", "eval_frac": EVAL_FRAC, **stats,
                "dropped_duplicate_text": dup, "dropped_conflicting_text": conflict, "records_kept": len(kept),
                **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    """The recall's enforcement record in the openFDA device enforcement API (the same dataset as the bulk file)."""
    return f'https://api.fda.gov/device/enforcement.json?search=recall_number:"{row["source_id"]}"'


_RECALLS: dict[str, dict[str, dict]] = {}


def _recalls(snapshot: str) -> dict[str, dict]:
    """recall number -> enforcement record of the raw bulk file, read once per process."""
    if snapshot not in _RECALLS:
        out = {}
        for p in sorted(glob.glob(os.path.join(R.RAW, DOMAIN, snapshot, "device-enforcement-*.json.zip"))):
            with zipfile.ZipFile(p) as zf:
                for name in zf.namelist():
                    for r in json.loads(zf.read(name)).get("results", []):
                        out[r.get("recall_number")] = r
        _RECALLS[snapshot] = out
    return _RECALLS[snapshot]


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in ("name", "phone", "email")]


def _in_order(sub: list[str], full: list[str]) -> bool:
    it = iter(full)
    return all(any(w == x for x in it) for w in sub)


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The class read again from the raw file (a direct lookup of the recall number, not the builder's event logic), and
    whether the item's product and reason lines are the record's own words in the record's order (masks skipped)."""
    r = _recalls(snapshot).get(row["source_id"])
    if r is None:
        return None, False
    lines = {ln.split(": ", 1)[0]: ln.split(": ", 1)[1] for ln in row["questions"][0]["instructions"].split("\n")
             if ": " in ln}
    prod = _tokens(lines.get("Product", "").removesuffix(" ..."))
    reason = _tokens(lines.get("Reason for recall", ""))
    text_ok = bool(prod and reason) and _in_order(prod, _tokens(r.get("product_description", ""))) and \
        _in_order(reason, _tokens(r.get("reason_for_recall", "")))
    return LABELS.get(r.get("classification")), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        print(f"{s}: {m['splits'][s]['rows']} rows ({m['splits'][s]['fresh']} fresh), classes {m['splits'][s]['class_prior']}, "
              f"gold position {m['splits'][s]['gold_position']}")
    print(f"records read {m['records_read']} in {m['events']} events; events dropped: unclassified "
          f"{m['events_unclassified']}, conflicting class {m['events_conflicting_class']}, unrenderable / scrub "
          f"{m['events_unrenderable_or_scrub']}; duplicate text {m['dropped_duplicate_text']}, conflicting text "
          f"{m['dropped_conflicting_text']}; kept {m['records_kept']}; classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
