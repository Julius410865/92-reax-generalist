"""#22 Expense policy: a numbered business-expense policy with per-item rules + 5 expense lines -> one yes / no question per
line (is it reimbursed in full?).

Rules drawn per item: currency, 3-5 expense types out of ten (meals: cap per person, inclusive or exclusive, alcohol never
or only with a client; hotels: nightly cap, optionally a higher cap for listed cities; private car: rate per km, a km
limit per trip, the amount claimed may not exceed km x rate; taxis: cap per ride, optionally only at night or to / from an
airport; flights: business class only from a flight time, optionally a minimum booking lead time; conference fees: always
pre-approved, optional cap; equipment: approval above a limit; client gifts: cap per recipient, no vouchers; parking: cap
per day; phone bills: cap per month), and general rules (receipt threshold, pre-approval threshold, submission deadline
in days, what happens to expense types the policy does not name). Every limit says whether it is inclusive, every
amount has its currency, dates are ISO. 1-3 clauses that decide nothing are mixed in, the clause order is shuffled.

Answers are drawn independently per line (yes with p = 0.5, no forced mix): a "yes" line meets every rule that applies to
it, often exactly at an inclusive limit; a "no" line breaks one rule (sometimes two), often just past a limit. The gold
comes from solve(), which re-checks every rule on the line's data.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from fractions import Fraction

from tools.gen.base import NAMES, Retry, money, pick

TASK = "expense_policy"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None
N_LINES = 5            # every dev item of this type has 5 questions
P_YES = 0.5

CURRENCIES = ("EUR", "USD", "GBP", "CHF", "CAD", "SGD")
COMPANIES = ("Brightwater Analytics", "Halden Instruments", "Corvane Systems", "Mistral Foods", "Oakline Consulting",
             "Pelham & Rowe", "Quillfield Media", "Rivermark Engineering", "Saffron Labs", "Tessaro Group",
             "Umberfield Energy", "Veltra Health", "Westbrook Robotics", "Yarrow Logistics", "Zenith Textiles",
             "Ashgrove Partners", "Bellmont Software", "Cinder Hill Studios", "Dunmore Optics", "Elstree Biotech")
CITIES = ("Lisbon", "Dublin", "Copenhagen", "Geneva", "Tokyo", "Sydney", "Toronto", "Seattle", "Milan", "Munich",
          "Vienna", "Helsinki", "Antwerp", "Porto", "Lyon", "Gdansk", "Tallinn", "Valencia", "Bergen", "Leeds", "Glasgow",
          "Rotterdam", "Hamburg", "Krakow", "Seville", "Turin", "Ghent", "Graz", "Malmo", "Aarhus", "Nantes", "Bilbao")
CATS = ("meal", "hotel", "mileage", "taxi", "flight", "conference", "equipment", "gift", "parking", "phone")
TAGS = {"meal": "Meals:", "hotel": "Hotels:", "mileage": "Private car:", "taxi": "Taxis:", "flight": "Flights:",
        "conference": "Conference and training fees:", "equipment": "Equipment:", "gift": "Client gifts:",
        "parking": "Parking:", "phone": "Mobile phone bills:"}
STARTS = {"meal": "Business meal for", "hotel": "Hotel stay in", "mileage": "Private car trip", "taxi": "Taxi ride", "flight": "Flight in",
          "conference": "Conference fee", "equipment": "Equipment purchase", "gift": "Client gift", "parking": "Parking for",
          "phone": "Mobile phone bill"}
OTHER = ("Courier service", "Laundry service", "Printing service", "Professional books", "Coworking day pass")
EVENTS = ("a data-privacy summit", "a supply-chain forum", "an industry trade fair", "a two-day leadership workshop",
          "a regional sales conference", "a technical training course")
ITEMS = ("a keyboard", "a headset", "a monitor", "a docking station", "a webcam", "an office chair")
GIFTS = ("a box of chocolates", "a bottle of olive oil", "a book", "a desk calendar", "a tea set")
VOUCHER = "gift vouchers"
ROUTES = ("from the hotel to the client office", "from the office to a client site", "from the train station to the hotel",
          "from a client dinner to the hotel")
AIRPORT_ROUTES = ("from the airport to the hotel", "from the hotel to the airport")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")

TITLES = ("{c} - expense reimbursement policy", "Business expense rules ({c})", "Travel and expense policy of {c}",
          "{c}: what we reimburse", "Expense claims at {c}: the rules")
CLOSINGS = ("An expense is paid back in full only when it complies with all of the rules relevant to it.",
            "Each expense must satisfy all rules relevant to it; one broken rule means it is not paid in full.",
            "Only expenses that comply with every relevant rule are paid in full.",
            "If any rule relevant to an expense is broken, the expense is not paid back in full.",
            "Rules written for a different kind of expense do not matter here; an expense is paid in full only when all rules relevant to it are met.")
IRRELEVANT = ("Approved expenses are paid with the next monthly salary.",
              "Questions about this policy go to the finance team.",
              "Unspent travel advances must be returned within {n} days after the trip.",
              "Employees may keep loyalty points earned on business trips.",
              "This policy was last reviewed on {d}.",
              "Corporate cards are issued on request; their monthly limit is {m}.",
              "Expense reports are filed in the company's expense tool.",
              "Exchange-rate differences are booked by finance and are never part of an expense.",
              "Team leads review expense reports once a week.",
              "Finance may ask for a short business reason for any expense.")
LABELS = ("Item", "Entry", "Expense", "Row", "Claim")
Q_LINES = ("Question: Does {lab} {k} get paid back in full?", "Question: Can {lab} {k} be paid out in full?",
           "Question: Does {lab} {k} comply with all rules relevant to it?", "Question: Should finance pay {lab} {k} in full?",
           "Question: Is {lab} {k} fully refundable to the employee?", "Question: Under these rules, is {lab} {k} paid in full?")
Q_PEOPLE = ("Question: Does {name}'s claim get paid back in full?", "Question: Can the claim of {name} be paid out in full?",
            "Question: Does {name}'s claim comply with all rules relevant to it?", "Question: Should finance pay {name} in full?",
            "Question: Is the expense claimed by {name} fully refundable?")


# --------------------------------------------------------------------------------------------------------- helpers

def _ok(v, limit, incl) -> bool:
    """v is within a cap: v <= limit (inclusive) or v < limit (exclusive)."""
    return v <= limit if incl else v < limit


def _reaches(v, limit, incl) -> bool:
    """v reaches a threshold: v >= limit (inclusive) or v > limit (exclusive)."""
    return v >= limit if incl else v > limit


def _within(rng, limit, incl, gran, lo_frac=0.45, edge=0.18):
    """A value that keeps a cap (often exactly on it when the cap is inclusive)."""
    if rng.random() < edge:
        return limit if incl else limit - gran
    lo = max(gran, int(limit * lo_frac) // gran * gran)
    hi = limit if incl else limit - gran
    return rng.randrange(lo, hi + 1, gran) if hi >= lo else hi


def _beyond(rng, limit, incl, gran, hi_frac=1.4, edge=0.3):
    """A value that breaks a cap (often exactly on an exclusive cap or one step past it)."""
    if rng.random() < edge:
        return limit + gran if incl else limit
    lo = limit + gran
    hi = max(lo, int(limit * hi_frac) // gran * gran)
    return rng.randrange(lo, hi + 1, gran)


def _below_threshold(rng, limit, incl, gran):
    """A value that does not reach a threshold (inverse of _reaches)."""
    return _within(rng, limit, not incl, gran, lo_frac=0.3)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


# ------------------------------------------------------------------------------------------------------------ draw

def _cat_rules(rng, cur):
    cats = sorted(pick(rng, CATS, rng.randint(3, 5)), key=CATS.index)
    r = {}
    for c in cats:
        if c == "meal":
            r[c] = {"cap": rng.choice((25, 30, 35, 40, 45, 50, 55, 60, 70, 80)) * 100, "incl": rng.random() < 0.6,
                    "alcohol": rng.choice(("never", "client"))}
        elif c == "hotel":
            r[c] = {"cap": rng.randrange(90, 200, 10) * 100, "incl": rng.random() < 0.7, "high": None}
            if rng.random() < 0.55:
                r[c]["high"] = {"cities": pick(rng, CITIES, rng.randint(2, 4)), "cap": r[c]["cap"] + rng.randrange(30, 130, 10) * 100}
        elif c == "mileage":
            r[c] = {"rate": rng.randrange(22, 48), "max_km": rng.choice((200, 250, 300, 400, 500, 600)), "incl": rng.random() < 0.6}
        elif c == "taxi":
            r[c] = {"cap": rng.choice((30, 40, 50, 60, 75, 90)) * 100, "incl": rng.random() < 0.6, "window": None}
            if rng.random() < 0.5:
                r[c]["window"] = {"start": rng.choice((20, 21, 22, 23)), "end": rng.choice((5, 6, 7)), "airport": rng.random() < 0.5}
        elif c == "flight":
            r[c] = {"hours": rng.choice((4, 5, 6, 7, 8, 9)), "incl": rng.random() < 0.5,
                    "lead": rng.choice((7, 10, 14, 21)) if rng.random() < 0.5 else None}
        elif c == "conference":
            r[c] = {"cap": rng.randrange(400, 1600, 100) * 100 if rng.random() < 0.5 else None}
        elif c == "equipment":
            r[c] = {"limit": rng.choice((100, 150, 200, 250, 300, 400)) * 100, "incl": rng.random() < 0.5}
        elif c == "gift":
            r[c] = {"cap": rng.choice((20, 25, 30, 40, 50, 60)) * 100, "incl": rng.random() < 0.6}
        elif c == "parking":
            r[c] = {"cap": rng.choice((15, 18, 20, 25, 30, 35)) * 100}
        elif c == "phone":
            r[c] = {"cap": rng.choice((40, 50, 60, 75, 90)) * 100}
    return r


def draw(rng):
    cur = rng.choice(CURRENCIES)
    cats = _cat_rules(rng, cur)
    gen = {"receipt": {"amount": rng.choice((10, 15, 20, 25, 30, 40, 50, 75)) * 100, "incl": rng.random() < 0.5} if rng.random() < 0.85 else None,
           "approval": {"amount": rng.choice((250, 300, 400, 500, 600, 750, 1000, 1500)) * 100, "incl": rng.random() < 0.5} if rng.random() < 0.6 else None,
           "deadline": {"days": rng.choice((30, 45, 60, 90))} if rng.random() < 0.5 else None,
           "unlisted": rng.choice(("never", "general")) if rng.random() < 0.4 else None}
    people = rng.random() < 0.35
    case = {"cur": cur, "company": rng.choice(COMPANIES), "cats": cats, "general": gen, "people": people,
            "submitter": rng.choice(NAMES), "submitted": (date(2026, 9, 1) + timedelta(days=rng.randint(0, 100))).isoformat(),
            "irrelevant": [t.format(n=rng.choice((7, 10, 14, 30)), d=(date(2026, 1, 5) + timedelta(days=rng.randint(0, 200))).isoformat(),
                                    m=money(rng.choice((2000, 3000, 5000, 7500)), cur))
                           for t in pick(rng, IRRELEVANT, rng.randint(1, 3))]}
    owners = pick(rng, NAMES, N_LINES) if people else [None] * N_LINES
    claims = []
    for owner in owners:
        target = rng.random() < P_YES
        claims.append(_claim(rng, case, target, owner))
    case["claims"] = claims
    return case


def _unlisted_types(case):
    return [c for c in CATS if c not in case["cats"]] + ["other"]


def _facts(rng, case, cat):
    """Facts of one line that keep its category rule (defaults when the type is not in the policy), and the category
    breaks: (name, fn) pairs, where fn changes the facts so that the category rule is broken and name is None, or
    "approval" when the break is an approval that is then withheld."""
    p = case["cats"].get(cat)
    c = {"cat": cat}
    br = []
    if cat == "meal":
        cap, incl = (p["cap"], p["incl"]) if p else (4000, True)
        c["persons"] = rng.choice((1, 1, 2, 3, 4))
        c["amount"] = _within(rng, cap, incl, 50) * c["persons"]
        c["alcohol"], c["client"] = False, rng.random() < 0.5
        if p and p["alcohol"] == "client" and rng.random() < 0.35:
            c["alcohol"], c["client"] = True, True
        if p:
            br.append((None, lambda: c.update(amount=_beyond(rng, cap, incl, 50) * c["persons"])))
            br.append((None, lambda: c.update(alcohol=True)) if p["alcohol"] == "never"
                      else (None, lambda: c.update(alcohol=True, client=False)))
    elif cat == "hotel":
        high = p["high"]["cities"] if p and p["high"] else []
        c["city"] = rng.choice(high) if high and rng.random() < 0.45 else rng.choice([x for x in CITIES if x not in high])
        c["nights"] = rng.choice((1, 1, 2, 2, 3, 4))
        cap, incl = (_hotel_cap(p, c["city"]), p["incl"]) if p else (15000, True)
        if high and c["city"] in high and rng.random() < 0.5:
            c["rate"] = rng.randrange(p["cap"] + 500, cap + 1, 500)         # above the normal cap, within the city cap
            if not _ok(c["rate"], cap, incl):
                c["rate"] = cap - 500
        else:
            c["rate"] = _within(rng, cap, incl, 500, lo_frac=0.6)
        c["amount"] = c["rate"] * c["nights"]
        if p:
            def hotel_break():
                if high and c["city"] not in high and rng.random() < 0.5:
                    c["rate"] = rng.randrange(p["cap"] + 500, p["high"]["cap"] + 1, 500)   # fine only in a listed city
                else:
                    c["rate"] = _beyond(rng, cap, incl, 500, hi_frac=1.3)
            br.append((None, hotel_break))
    elif cat == "mileage":
        rate, mx, incl = (p["rate"], p["max_km"], p["incl"]) if p else (30, 300, True)
        c["km"] = _within(rng, mx, incl, 1, lo_frac=0.3)
        c["amount"] = c["km"] * rate if rng.random() < 0.8 else max(100, c["km"] * rate // 100 * 100)
        if c["amount"] > c["km"] * rate:
            c["amount"] = c["km"] * rate
        if p:
            def km_break():
                c["km"] = _beyond(rng, mx, incl, 1, hi_frac=1.5)
                c["amount"] = c["km"] * rate
            br.append((None, km_break))
            br.append((None, lambda: c.update(amount=c["km"] * (rate + rng.choice((1, 2, 3, 5, 8))) + rng.choice((0, 0, 7, 50)))))
    elif cat == "taxi":
        cap, incl = (p["cap"], p["incl"]) if p else (5000, True)
        w = p["window"] if p else None
        c["amount"] = _within(rng, cap, incl, 50, lo_frac=0.3)
        c["airport"] = rng.random() < 0.3
        if w and w["airport"] and c["airport"] and rng.random() < 0.6:
            c["time"] = rng.randrange(w["end"] * 60, w["start"] * 60)                    # daytime, allowed as an airport ride
        elif w:
            c["time"] = rng.choice((w["start"] * 60, w["end"] * 60 - 1, rng.randrange(w["start"] * 60, 24 * 60),
                                    rng.randrange(0, w["end"] * 60)))
        else:
            c["time"] = rng.randrange(6 * 60, 24 * 60)
        if p:
            br.append((None, lambda: c.update(amount=_beyond(rng, cap, incl, 50))))
            if w:
                br.append((None, lambda: c.update(airport=False, time=rng.choice((w["end"] * 60, w["start"] * 60 - 1,
                                                                                  rng.randrange(w["end"] * 60, w["start"] * 60))))))
    elif cat == "flight":
        hrs, incl, lead = (p["hours"], p["incl"], p["lead"]) if p else (6, True, None)
        lim = hrs * 60
        c["business"] = rng.random() < 0.5
        c["minutes"] = _reaches_value(rng, lim, incl) if c["business"] else rng.randrange(45, lim + 120, 5)
        c["amount"] = rng.randrange(90, 2400, 5) * 100 if c["business"] else rng.randrange(60, 900, 5) * 100
        c["lead_days"] = (lead if rng.random() < 0.2 else lead + rng.randint(1, 40)) if lead else rng.randint(1, 60)
        if p:
            br.append((None, lambda: c.update(business=True, minutes=_below_threshold(rng, lim, incl, 5))))
            if lead:
                br.append((None, lambda: c.update(lead_days=rng.choice((lead - 1, lead - 1, max(0, lead - rng.randint(2, 6)))))))
    elif cat == "conference":
        cap = p["cap"] if p else None
        c["event"] = rng.choice(EVENTS)
        c["amount"] = _within(rng, cap, True, 500, lo_frac=0.4) if cap else rng.randrange(150, 1800, 5) * 100
        if p:
            br.append(("approval", None))                                         # always needs prior approval
            if cap:
                br.append((None, lambda: c.update(amount=_beyond(rng, cap, True, 500))))
    elif cat == "equipment":
        lim, incl = (p["limit"], p["incl"]) if p else (20000, True)
        c["item"] = rng.choice(ITEMS)
        c["amount"] = lim if rng.random() < 0.2 else rng.randrange(20, 600) * 100 + rng.choice((0, 0, 50, 99))
        if p:
            br.append(("approval", lambda: c.update(amount=_beyond(rng, lim, incl, 100))))   # above the free limit
    elif cat == "gift":
        cap, incl = (p["cap"], p["incl"]) if p else (3000, True)
        c["recipients"] = rng.choice((1, 2, 3, 4, 5))
        c["item"] = rng.choice(GIFTS)
        c["amount"] = _within(rng, cap, incl, 50) * c["recipients"]
        if p:
            br.append((None, lambda: c.update(amount=_beyond(rng, cap, incl, 50) * c["recipients"])))
            br.append((None, lambda: c.update(item=VOUCHER)))
    elif cat == "parking":
        cap = p["cap"] if p else 2000
        c["days"] = rng.choice((1, 2, 3, 4, 5))
        c["amount"] = _within(rng, cap, True, 50) * c["days"]
        if p:
            br.append((None, lambda: c.update(amount=_beyond(rng, cap, True, 50) * c["days"])))
    elif cat == "phone":
        cap = p["cap"] if p else 6000
        c["month_lag"] = rng.choice((0, 1, 0, 1))      # the bill covers the month of its date or the month before
        c["amount"] = _within(rng, cap, True, 1, lo_frac=0.5)
        if p:
            br.append((None, lambda: c.update(amount=_beyond(rng, cap, True, 1, hi_frac=1.3))))
    else:
        c["item"] = rng.choice(OTHER)
        c["amount"] = rng.randrange(8, 260) * 100 + rng.choice((0, 0, 50, 95))
    return c, br


def _claim(rng, case, target, owner):
    cats, gen = case["cats"], case["general"]
    pool = list(cats)
    if gen["unlisted"] and rng.random() < 0.15 and (gen["unlisted"] == "general" or not target):
        pool = _unlisted_types(case)
    c, br = _facts(rng, case, rng.choice(pool))
    covered = c["cat"] in cats or gen["unlisted"] == "general"
    if owner:
        c["owner"] = owner
        c["submitted"] = (date(2026, 9, 1) + timedelta(days=rng.randint(0, 100))).isoformat()
    dl = gen["deadline"]
    age = (dl["days"] if rng.random() < 0.15 else rng.randint(0, dl["days"] - 1)) if dl else rng.randint(1, 120)
    if dl:
        br.append(("deadline", None))
    withhold = set()
    if not target and covered:
        if _needs_receipt(case, c):
            br.append(("receipt", None))
        if _needs_approval(case, c) and not any(n == "approval" for n, _ in br):
            br.append(("approval", None))
        if not br:
            raise Retry("no rule to break")
        for name, fn in pick(rng, br, 1 if (rng.random() < 0.8 or len(br) < 2) else 2):
            if fn:
                fn()
            if name == "deadline":
                age = dl["days"] + rng.choice((1, 1, 2, 5, 12, 30))
            elif name:
                withhold.add(name)
    if c["cat"] == "hotel":
        c["amount"] = c["rate"] * c["nights"]
    sub = c.get("submitted") or case["submitted"]
    c["date"] = (date.fromisoformat(sub) - timedelta(days=age)).isoformat()
    if c["cat"] == "flight":
        c["depart"] = (date.fromisoformat(c["date"]) + timedelta(days=c.pop("lead_days"))).isoformat()
    if c["cat"] == "phone":
        d = date.fromisoformat(c["date"]).replace(day=1) - timedelta(days=c.pop("month_lag"))   # lag 1: the previous month
        c["month"] = f"{MONTH_NAMES[d.month - 1]} {d.year}"
    c["receipt"] = False if "receipt" in withhold else (True if _needs_receipt(case, c) else rng.random() < 0.5)
    c["approved"] = False if "approval" in withhold else (True if _needs_approval(case, c) else rng.random() < 0.4)
    if line_ok(case, c) != target:
        raise Retry("line does not match its target")
    return c


def _reaches_value(rng, lim, incl):
    """A duration that allows business class (reaches the flight-time threshold)."""
    if rng.random() < 0.25:
        return lim if incl else lim + 5
    return rng.randrange(lim + 5, lim + 360, 5)


def _hotel_cap(p, city):
    return p["high"]["cap"] if p["high"] and city in p["high"]["cities"] else p["cap"]


def _needs_receipt(case, c) -> bool:
    r = case["general"]["receipt"]
    exempt = c["cat"] == "mileage" and "mileage" in case["cats"]          # the exemption is stated only then
    return bool(r) and not exempt and _reaches(c["amount"], r["amount"], r["incl"])


def _needs_approval(case, c) -> bool:
    a, cats = case["general"]["approval"], case["cats"]
    if c["cat"] == "conference" and "conference" in cats:
        return True
    if c["cat"] == "equipment" and "equipment" in cats and not _ok(c["amount"], cats["equipment"]["limit"], cats["equipment"]["incl"]):
        return True
    return bool(a) and _reaches(c["amount"], a["amount"], a["incl"])


# ----------------------------------------------------------------------------------------------------------- solve

def line_ok(case, c) -> bool:
    """Every rule that applies to the line is met."""
    cats, gen = case["cats"], case["general"]
    cat, p = c["cat"], case["cats"].get(c["cat"])
    if p is None and gen["unlisted"] != "general":
        return False
    sub = c.get("submitted") or case["submitted"]
    if gen["deadline"] and _days(c["date"], sub) > gen["deadline"]["days"]:
        return False
    if _needs_receipt(case, c) and not c["receipt"]:
        return False
    if _needs_approval(case, c) and not c["approved"]:
        return False
    if p is None:
        return True
    if cat == "meal":
        return (_ok(Fraction(c["amount"], c["persons"]), p["cap"], p["incl"])
                and (not c["alcohol"] or (p["alcohol"] == "client" and c["client"])))
    if cat == "hotel":
        return _ok(c["rate"], _hotel_cap(p, c["city"]), p["incl"])
    if cat == "mileage":
        return _ok(c["km"], p["max_km"], p["incl"]) and c["amount"] <= c["km"] * p["rate"]
    if cat == "taxi":
        w = p["window"]
        timely = not w or c["time"] >= w["start"] * 60 or c["time"] < w["end"] * 60 or (w["airport"] and c["airport"])
        return _ok(c["amount"], p["cap"], p["incl"]) and timely
    if cat == "flight":
        cls_ok = not c["business"] or _reaches(c["minutes"], p["hours"] * 60, p["incl"])
        return cls_ok and (not p["lead"] or _days(c["date"], c["depart"]) >= p["lead"])
    if cat == "conference":
        return not p["cap"] or c["amount"] <= p["cap"]
    if cat == "gift":
        return c["item"] != VOUCHER and _ok(Fraction(c["amount"], c["recipients"]), p["cap"], p["incl"])
    if cat == "parking":
        return Fraction(c["amount"], c["days"]) <= p["cap"]
    if cat == "phone":
        return c["amount"] <= p["cap"]
    return True                       # equipment: only the approval rule (checked above)


def solve(case):
    return [line_ok(case, c) for c in case["claims"]]


# ---------------------------------------------------------------------------------------------------------- render

def _m(cents, cur):
    return money(cents / 100, cur)


def _cap_phrase(amount: str, incl: bool, unit: str = "") -> str:
    unit = f" {unit}" if unit else ""
    return (f"no more than {amount}{unit} (exactly {amount} is accepted)" if incl
            else f"below {amount}{unit} (exactly {amount} is not accepted)")


def _threshold_phrase(amount: str, incl: bool) -> str:
    return f"{amount} or more" if incl else f"above {amount} ({amount} itself does not count)"


def _rules(case, rng) -> list[str]:
    cur, cats, gen = case["cur"], case["cats"], case["general"]
    out = []
    for cat, p in cats.items():
        if cat == "meal":
            alc = ("drinks containing alcohol are not paid for." if p["alcohol"] == "never"
                   else "drinks containing alcohol are paid for only when a client attended the meal.")
            out.append(f"Meals: the cost per person (the total divided by the number of people) may be "
                       f"{_cap_phrase(_m(p['cap'], cur), p['incl'])}; {alc}")
        elif cat == "hotel":
            t = f"Hotels: room rate {_cap_phrase(_m(p['cap'], cur), p['incl'], 'per night')}"
            if p["high"]:
                cs = p["high"]["cities"]
                t += f"; in {', '.join(cs[:-1])} or {cs[-1]} the limit is {_m(p['high']['cap'], cur)} per night instead, with the same rule at the limit"
            out.append(t + ".")
        elif cat == "mileage":
            km = (f"trips of more than {p['max_km']} km are not paid at all ({p['max_km']} km itself is fine)" if p["incl"]
                  else f"trips of {p['max_km']} km or more are not paid at all")
            out.append(f"Private car: paid at {_m(p['rate'], cur)} per km driven; {km}; the amount claimed must not be "
                       "higher than km driven x rate.")
        elif cat == "taxi":
            t = f"Taxis: {_cap_phrase(_m(p['cap'], cur), p['incl'], 'per ride')}"
            w = p["window"]
            if w:
                t += (f"; a ride is paid only if it starts at {w['start']:02d}:00 or later or before {w['end']:02d}:00"
                      + (", or, at any time of day, if it goes to or from an airport" if w["airport"] else ""))
            out.append(t + ".")
        elif cat == "flight":
            h = (f"the scheduled flight time is {p['hours']} hours or more" if p["incl"]
                 else f"the scheduled flight time is more than {p['hours']} hours (exactly {p['hours']} hours is not enough)")
            t = f"Flights: economy class; business class is allowed only when {h}"
            if p["lead"]:
                t += (f"; every flight must be booked at least {p['lead']} days before departure (exactly {p['lead']} days "
                      "is enough; the date of a flight expense is its booking date)")
            out.append(t + ".")
        elif cat == "conference":
            t = "Conference and training fees: always need prior approval, whatever the amount"
            if p["cap"]:
                t += f"; at most {_m(p['cap'], cur)} per event (exactly {_m(p['cap'], cur)} is accepted)"
            out.append(t + ".")
        elif cat == "equipment":
            lim = _m(p["limit"], cur)
            t = f"an item costing more than {lim}" if p["incl"] else f"an item costing {lim} or more"
            out.append(f"Equipment: {t} needs prior approval, in addition to any other approval rule in this policy.")
        elif cat == "gift":
            out.append(f"Client gifts: {_cap_phrase(_m(p['cap'], cur), p['incl'], 'per recipient')}; gift vouchers and cash are never paid for.")
        elif cat == "parking":
            out.append(f"Parking: no more than {_m(p['cap'], cur)} per day (exactly {_m(p['cap'], cur)} is accepted).")
        elif cat == "phone":
            out.append(f"Mobile phone bills: no more than {_m(p['cap'], cur)} per month (exactly {_m(p['cap'], cur)} is accepted).")
    r, a, d = gen["receipt"], gen["approval"], gen["deadline"]
    if r:
        out.append(f"Receipts: a receipt must be attached to every expense whose total is {_threshold_phrase(_m(r['amount'], cur), r['incl'])}"
                   + ("; private-car mileage never needs one." if "mileage" in cats else "."))
    if a:
        out.append(f"Prior approval: an expense whose total is {_threshold_phrase(_m(a['amount'], cur), a['incl'])} "
                   "is paid only if it was approved beforehand.")
    if d:
        out.append(f"Deadline: an expense must be submitted within {d['days']} days of its expense date (the expense "
                   f"date is day 0; a submission on day {d['days']} is still in time).")
    if gen["unlisted"] == "never":
        out.append("Other expense types: any type of expense not named in this policy is not reimbursed.")
    elif gen["unlisted"] == "general":
        out.append("Other expense types: a type of expense not named in this policy is reimbursed if it meets the rules "
                   "on receipts, prior approval and deadlines in this policy.")
    out += case["irrelevant"]
    rng.shuffle(out)
    return out


def _desc(case, c, rng) -> str:
    cur, cat = case["cur"], c["cat"]
    a = _m(c["amount"], cur)
    if cat == "meal":
        who = "one person" if c["persons"] == 1 else f"{c['persons']} people"
        alc = "includes alcohol" if c["alcohol"] else "no alcohol"
        cl = "with a client" if c["client"] else "no client present"
        return f"Business meal for {who}, {a} in total, {alc}, {cl}"
    if cat == "hotel":
        n = "1 night" if c["nights"] == 1 else f"{c['nights']} nights"
        return (f"Hotel stay in {c['city']}: {n}, room rate {_m(c['rate'], cur)} per night" if rng.random() < 0.5 or c["nights"] == 1
                else f"Hotel stay in {c['city']}: {n}, {a} in total")
    if cat == "mileage":
        return f"Private car trip of {c['km']} km, {a} claimed"
    if cat == "taxi":
        route = rng.choice(AIRPORT_ROUTES) if c["airport"] else rng.choice(ROUTES)
        return f"Taxi ride starting at {_hhmm(c['time'])} {route}, {a}"
    if cat == "flight":
        cls = "business" if c["business"] else "economy"
        return (f"Flight in {cls} class, scheduled flight time {c['minutes'] // 60} h {c['minutes'] % 60:02d} min, "
                f"departure on {c['depart']}, {a}")
    if cat == "conference":
        return f"Conference fee for {c['event']}, {a}"
    if cat == "equipment":
        return f"Equipment purchase: {c['item']}, {a}"
    if cat == "gift":
        n = "1 recipient" if c["recipients"] == 1 else f"{c['recipients']} recipients"
        return f"Client gift ({c['item']}) for {n}, {a} in total"
    if cat == "parking":
        n = "1 day" if c["days"] == 1 else f"{c['days']} days"
        return f"Parking for {n}, {a} in total"
    if cat == "phone":
        return f"Mobile phone bill for {c['month']}, {a}"
    return f"{c['item']}, {a}"


def _line(case, c, kv: bool, rng) -> str:
    frags = [_desc(case, c, rng)]
    extra = []
    if kv:
        extra.append(f"date: {c['date']}")
        extra.append(f"receipt: {'yes' if c['receipt'] else 'no'}")
        extra.append(f"approved beforehand: {'yes' if c['approved'] else 'no'}")
    else:
        extra.append(f"dated {c['date']}")
        extra.append("receipt enclosed" if c["receipt"] else "no receipt")
        extra.append("approved beforehand" if c["approved"] else "not approved beforehand")
    if c.get("submitted"):
        extra.append(f"submitted: {c['submitted']}" if kv else f"submitted on {c['submitted']}")
    rng.shuffle(extra)
    return ("; ".join(frags + extra) if kv else ", ".join(frags + extra)) + "."


def render(case, rng):
    rules = _rules(case, rng)
    head = (rng.choice(TITLES).format(c=case["company"]) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
            + "\n" + rng.choice(CLOSINGS))
    kv = rng.random() < 0.4
    if case["people"]:
        top = rng.choice(("Claims received this week (each with its own submission date):", "Open expense claims:",
                          "Claims to decide:"))
        body = top + "\n" + "\n".join(f"{c['owner']}: {_line(case, c, kv, rng)}" for c in case["claims"])
        qt = rng.choice(Q_PEOPLE)
        qs = [qt.format(name=c["owner"]) for c in case["claims"]]
    else:
        lab = rng.choice(LABELS)
        name, sub = case["submitter"], case["submitted"]
        top = rng.choice((f"Expense report of {name}, submitted on {sub}:", f"Expenses submitted by {name} on {sub}:",
                          f"{name} submitted the following expenses on {sub}:"))
        body = top + "\n" + "\n".join(f"{lab} {k}: {_line(case, c, kv, rng)}" for k, c in enumerate(case["claims"], 1))
        qt = rng.choice(Q_LINES)
        qs = [qt.format(lab=lab.lower(), k=k) for k in range(1, len(case["claims"]) + 1)]
    return [{"instructions": f"{head}\n\n{body}\n\n{q}", "options": None} for q in qs]


# ------------------------------------------------------------------------------------------------- second solver

MONEY_RE = r"[A-Z]{3} (\d[\d,]*\.\d{2})"
RULE_TAGS = tuple(TAGS.values()) + ("Receipts:", "Prior approval:", "Deadline:", "Other expense types:")


def _cents(s: str) -> int:
    whole, frac = s.replace(",", "").split(".")
    return int(whole) * 100 + int(frac)


def _first_money(text: str) -> int:
    return _cents(re.search(MONEY_RE, text).group(1))


def _iso(pattern: str, text: str) -> date:
    return date.fromisoformat(re.search(pattern, text).group(1))


def solve_text(q: dict) -> str:
    """Reads only the rendered question: the numbered rules, then the line that the question names."""
    policy, body, question = q["instructions"].split("\n\n")
    rules = {}
    for ln in policy.splitlines():
        mt = re.match(r"\d+\. (.*)$", ln)
        tag = next((t for t in RULE_TAGS if mt and mt.group(1).startswith(t)), None)
        if tag:
            rules[tag] = mt.group(1)
    head, *lines = body.splitlines()
    line = next(l for l in lines if re.search(rf"\b{re.escape(l.split(': ', 1)[0])}\b", question, re.I))
    desc = line.split(": ", 1)[1]
    sub = _iso(r"submitted(?: on|:) (\d{4}-\d{2}-\d{2})", desc) if "submitted" in desc else _iso(r"(\d{4}-\d{2}-\d{2})", head)
    dated = _iso(r"(?:dated|date:) (\d{4}-\d{2}-\d{2})", desc)
    receipt = "receipt: yes" in desc or "receipt enclosed" in desc
    approved = ("approved beforehand: yes" in desc) if "approved beforehand:" in desc else "not approved beforehand" not in desc
    kind = next((k for k, st in STARTS.items() if desc.startswith(st)), "other")
    total = _first_money(desc)
    if kind == "hotel":
        nights = int(re.search(r"(\d+) nights?", desc).group(1))
        per = Fraction(total, nights) if " in total" in desc else Fraction(total)
        total = per * nights
    listed = TAGS.get(kind) in rules
    if not listed and "is reimbursed if it meets" not in rules.get("Other expense types:", ""):
        return "no"
    # ---- general rules
    if "Deadline:" in rules and (sub - dated).days > int(re.search(r"within (\d+) days", rules["Deadline:"]).group(1)):
        return "no"

    def reaches(rule: str) -> bool:
        lim = _first_money(rule)
        return total >= lim if " or more" in rule.split(";")[0] else total > lim

    exempt = kind == "mileage" and "private-car mileage never needs one" in rules.get("Receipts:", "")
    if "Receipts:" in rules and not exempt and reaches(rules["Receipts:"]) and not receipt:
        return "no"
    need = "Prior approval:" in rules and reaches(rules["Prior approval:"])
    if listed and kind == "conference":
        need = True
    if listed and kind == "equipment":
        e = rules["Equipment:"]
        need = need or (total > _first_money(e) if "costing more than" in e else total >= _first_money(e))
    if need and not approved:
        return "no"
    if not listed:
        return "yes"
    rule = rules[TAGS[kind]]

    def within(v, text) -> bool:
        lim = _first_money(text)
        return v < lim if "is not accepted" in rule else v <= lim

    ok = True
    if kind == "meal":
        persons = 1 if "for one person" in desc else int(re.search(r"meal for (\d+) people", desc).group(1))
        ok = within(Fraction(total, persons), rule)
        if "includes alcohol" in desc and ("are not paid for" in rule or "no client present" in desc):
            ok = False
    elif kind == "hotel":
        city = re.search(r"Hotel stay in ([A-Z][a-z]+)", desc).group(1)
        normal, _, special = rule.partition("; in ")
        cities = re.findall(r"[A-Z][a-z]+", special.split(" the limit is")[0]) if special else []
        ok = within(per, special if city in cities else normal)
    elif kind == "mileage":
        km = int(re.search(r"trip of (\d+) km", desc).group(1))
        rate = _cents(re.search(rf"{MONEY_RE} per km", rule).group(1))
        if "trips of more than" in rule:
            ok = km <= int(re.search(r"trips of more than (\d+) km", rule).group(1))
        else:
            ok = km < int(re.search(r"trips of (\d+) km or more", rule).group(1))
        ok = ok and total <= km * rate
    elif kind == "taxi":
        ok = within(total, rule.split(";")[0])
        w = re.search(r"starts at (\d{2}):00 or later or before (\d{2}):00", rule)
        if w:
            hh, mm = re.search(r"starting at (\d{2}):(\d{2})", desc).groups()
            t = int(hh) * 60 + int(mm)
            timely = t >= int(w.group(1)) * 60 or t < int(w.group(2)) * 60
            if "if it goes to or from an airport" in rule and "airport" in desc:
                timely = True
            ok = ok and timely
    elif kind == "flight":
        hh, mm = re.search(r"scheduled flight time (\d+) h (\d+) min", desc).groups()
        mins = int(hh) * 60 + int(mm)
        lim = int(re.search(r"flight time is (?:more than )?(\d+) hours", rule).group(1)) * 60
        if desc.startswith("Flight in business class"):
            ok = mins >= lim if "hours or more" in rule else mins > lim
        lead = re.search(r"booked at least (\d+) days before departure", rule)
        if lead and (_iso(r"departure on (\d{4}-\d{2}-\d{2})", desc) - dated).days < int(lead.group(1)):
            ok = False
    elif kind == "conference":
        cap = re.search(rf"at most {MONEY_RE} per event", rule)
        ok = cap is None or total <= _cents(cap.group(1))
    elif kind == "gift":
        n = int(re.search(r"for (\d+) recipients?", desc).group(1))
        ok = "(gift vouchers)" not in desc and within(Fraction(total, n), rule)
    elif kind == "parking":
        ok = Fraction(total, int(re.search(r"Parking for (\d+) days?", desc).group(1))) <= _first_money(rule)
    elif kind == "phone":
        ok = total <= _first_money(rule)
    return "yes" if ok else "no"
