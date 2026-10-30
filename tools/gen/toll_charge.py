"""Road tolls: a motorway operator's tariff + one trip -> the toll charged.

Rules: a rate per km by vehicle class on the distance driven, a peak surcharge (percent of the distance charge) when the
trip enters the motorway inside a peak window (start inclusive, end exclusive), an electronic-tag discount (percent of
the distance charge after the surcharge), a flat bridge or tunnel fee that is neither surcharged nor discounted, and a
minimum charge per trip. Exact decimal arithmetic, the toll rounded to cents (halves up) at the end. Distractors are the
results with one rule misapplied (tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from tools.gen import _options as O
from tools.gen.base import Retry, money, pick

TASK = "toll_charge"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CHF", "AUD", "NZD", "SGD")
CLASSES = ("car", "van", "truck with 2 axles", "truck with 3 or more axles")
JUNCTIONS = ("Ashford", "Brightwater", "Cedar Point", "Dunmore", "Elmstead", "Fairhaven", "Glenrock", "Harbourside", "Ironbridge",
             "Juniper Hill", "Kingsgate", "Lakeview", "Millbrook", "Northfield", "Oakridge", "Pinecrest")
TITLES = ("MOTORWAY TOLL TARIFF", "Toll rules for the coastal motorway", "How the toll is calculated", "Tariff and charging rules",
          "Motorway charging schedule")
QUESTIONS = ("What toll is charged for this trip?", "How much is the toll for this trip?", "What does this trip cost in tolls?",
             "What is the toll for this journey?", "What amount is charged for this trip?")
D = lambda x: Decimal(str(x))


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def toll(case, *, err=None) -> float:
    km = sum(D(s) for s in case["segments"]) - (D(case["segments"][-1]) if err == "drop_segment" else 0)
    rate = D(case["rates"][case["vclass"] if err != "wrong_class" else case["wrong_class"]])
    dist = km * rate
    t = hm(case["entry"])
    peak = any(hm(a) <= t < hm(b) for a, b in case["peaks"])
    if err == "peak_inclusive_end":
        peak = any(hm(a) <= t <= hm(b) for a, b in case["peaks"])
    if err == "no_peak":
        peak = False
    p, d = D(case["peak"]) / 100, D(case["tag"]) / 100 if case["has_tag"] else Decimal(0)
    if err == "additive":
        charged = dist * (1 + (p if peak else 0) - d)
    else:
        charged = dist * (1 + (p if peak else 0)) * (1 - d)
    flat = D(case["flat"])
    if err == "discount_flat":
        tot = (dist * (1 + (p if peak else 0)) + flat) * (1 - d)
    else:
        tot = charged + flat
    if err != "no_minimum":
        tot = max(tot, D(case["minimum"]))
    return float(tot.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def draw(rng):
    rates = {c: f"{r:.3f}" for c, r in zip(CLASSES, sorted(rng.uniform(0.05, 0.6) for _ in CLASSES))}
    vclass = rng.choice(CLASSES)
    case = {"cur": rng.choice(CURS), "rates": rates, "vclass": vclass, "wrong_class": rng.choice([c for c in CLASSES if c != vclass]),
            "peak": rng.choice([10, 15, 20, 25, 30]), "tag": rng.choice([5, 10, 12, 15]), "has_tag": rng.random() < 0.6,
            "peaks": [("07:00", "09:30"), ("16:00", "19:00")] if rng.random() < 0.5 else [("06:30", "09:00"), ("15:30", "18:30")],
            "flat_name": rng.choice(["the Harbour Bridge", "the Ridge Tunnel", "the River Bridge", "the Hill Tunnel"]),
            "flat": rng.choice(["2.50", "3.00", "4.20", "5.80", "7.50"])}
    n = rng.randint(2, 4)
    case["segments"] = [f"{rng.randrange(40, 600) / 10:.1f}" for _ in range(n)]
    case["route"] = pick(rng, JUNCTIONS, n + 1)
    # entry time often right at a window edge
    a, b = rng.choice(case["peaks"])
    case["entry"] = rng.choice([a, b, f"{hm(b) // 60 - 1:02d}:{hm(b) % 60:02d}", "12:15", "05:45", "20:10"])
    km = sum(D(s) for s in case["segments"])
    base = float(km * D(rates[vclass]))
    case["minimum"] = f"{max(1.0, round(base * rng.choice([0.5, 0.9, 1.1, 1.6]), 1)):.2f}"
    gold = toll(case)
    errors = [toll(case, err=e) for e in ("drop_segment", "wrong_class", "peak_inclusive_end", "no_peak", "additive", "discount_flat", "no_minimum")]
    case["options"] = O.options(rng, gold, errors, 5, lambda v: money(v, case["cur"]))
    return case


def solve(case):
    return [case["options"].index(money(toll(case), case["cur"]))]


def render(case, rng):
    cur = case["cur"]
    rules = [f"Distance charge per km: " + "; ".join(f"{c} {cur} {r}" for c, r in case["rates"].items()) + ".",
             f"Peak surcharge: {case['peak']} % on the distance charge if the trip enters the motorway between "
             + " or between ".join(f"{a} and {b}" for a, b in case["peaks"])
             + " (the start time is inside the window, the end time is not).",
             f"Electronic tag: {case['tag']} % off the distance charge (after any peak surcharge) for vehicles with a registered tag.",
             f"{case['flat_name'][0].upper() + case['flat_name'][1:]}: a flat fee of {money(D(case['flat']), cur)}, never surcharged or discounted.",
             f"Minimum charge: every trip costs at least {money(D(case['minimum']), cur)} in total."]
    legs = "; ".join(f"{case['route'][i]} - {case['route'][i + 1]} {s} km" for i, s in enumerate(case["segments"]))
    tag = "with a registered electronic tag" if case["has_tag"] else "without an electronic tag"
    trip = (f"Trip: a {case['vclass']} {tag} enters at {case['route'][0]} at {case['entry']} and drives {legs}, crossing "
            f"{case['flat_name']}.")
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
            + "\nThe toll is rounded to cents at the end.\n\n" + trip + "\n\n" + rng.choice(QUESTIONS))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer arithmetic (km in tenths, rates in thousandths, percents)."""
    t = q["instructions"]
    cur = re.search(r"per km: .*?([A-Z]{3}) ", t).group(1)
    rates = {c: int(r.replace(".", "")) for c, r in re.findall(r"(car|van|truck with 2 axles|truck with 3 or more axles) [A-Z]{3} (\d+\.\d{3})", t)}
    trip = t.split("\n\nTrip: ")[1]
    vclass = re.match(r"an? (car|van|truck with 2 axles|truck with 3 or more axles) ", trip).group(1)
    km10 = sum(int(x.replace(".", "")) for x in re.findall(r" (\d+\.\d) km", trip))
    entry = re.search(r" at (\d{2}):(\d{2}) and drives", trip)
    tm = int(entry.group(1)) * 60 + int(entry.group(2))
    wins = re.findall(r"(\d{2}):(\d{2}) and (\d{2}):(\d{2})", t.split("Peak surcharge:")[1].split("\n")[0])
    peak = any(int(a) * 60 + int(b) <= tm < int(c) * 60 + int(d) for a, b, c, d in wins)
    p = int(re.search(r"Peak surcharge: (\d+) %", t).group(1)) if peak else 0
    tag = int(re.search(r"Electronic tag: (\d+) % off", t).group(1)) if "with a registered electronic tag" in trip else 0
    cents = lambda s: int(s.replace(",", "").replace(".", ""))
    flat = cents(re.search(r"a flat fee of [A-Z]{3} ([\d,]+\.\d{2})", t).group(1))
    minimum = cents(re.search(r"costs at least [A-Z]{3} ([\d,]+\.\d{2})", t).group(1))
    # distance charge in 1e-4 cents units: km10 (x10) * rate (x1000) -> currency x 1e4; x (100+p) x (100-tag) -> x 1e8
    dist = km10 * rates[vclass] * (100 + p) * (100 - tag)           # currency x 1e8
    tot = dist + flat * 10 ** 6                                     # flat cents -> currency x 1e8
    tot = max(tot, minimum * 10 ** 6)
    c_tot = (tot + 500000) // 10 ** 6                               # cents, halves up
    want = f"{cur} {c_tot // 100:,}.{c_tot % 100:02d}"
    return next(k for k, v in q["criteria"].items() if v == want)
