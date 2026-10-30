"""#23 Shipping rate: a parcel tariff (destination zones x chargeable-weight bands, surcharges, discount, VAT, rounding) and
one shipment -> the price (one question, 4 or 5 options).

Rules drawn per item: currency, carrier, 2-5 zones (countries, or 5-digit postcode ranges for a domestic tariff), 3-6
weight bands whose upper limits are inclusive or exclusive (always stated), the price grid, the volumetric divisor (or
none), whether the chargeable weight is rounded up (to 0.5 kg / 1 kg) before the band is looked up, what happens above the
top band (refused, or a price per started kg), 2-6 surcharge clauses (fuel %, express % or flat, oversize with an
inclusive or exclusive side limit, remote area, insurance % with a minimum, Saturday, signature, lithium batteries,
private address, cash on delivery, peak season by ISO date range), an optional discount (on the base price, on the net
amount, or a fixed credit; optionally only for online bookings / business accounts), an optional minimum charge, optional
VAT, and the rounding rule (every percentage amount to 0.01 as it is calculated, only the final price to 0.01, or the
final price to a coarser step). The order of calculation is stated. 1-3 clauses that do not affect the price are mixed in.

Options: the gold plus distractors from named mistakes (wrong band, wrong zone, actual instead of chargeable weight,
weight not rounded, a surcharge missing / applied twice / applied although it does not apply, fuel on the wrong base,
discount missing or applied without the condition, discount after VAT, VAT missing, minimum ignored, rounding at the wrong
step), then near values on the same rounding step. All options use one money format.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from fractions import Fraction

from tools.gen.base import NAMES, Retry, money, pick

TASK = "shipping_rate"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURRENCIES = ("EUR", "USD", "GBP", "CHF", "CAD", "AUD")
CARRIERS = ("Harbourline Couriers", "Pinecrest Parcel Service", "Swiftmark Logistics", "Meridian Cargo", "Corvid Post",
            "Larkspur Freight", "Saltmarsh Delivery", "Quayside Parcels", "Redwing Courier", "Tallow & Finch Couriers",
            "Brightpath Express", "Ironbark Shipping", "Kingfisher Parcels", "Northgate Courier", "Oakmere Logistics",
            "Silverline Despatch", "Wrenfield Carriers", "Amberley Freight", "Coldwater Parcel Co.", "Driftwood Couriers")
COUNTRIES = ("Portugal", "Ireland", "Belgium", "Denmark", "Finland", "Greece", "Hungary", "Romania", "Slovenia", "Croatia",
             "Estonia", "Latvia", "Lithuania", "Luxembourg", "Malta", "Cyprus", "Slovakia", "Bulgaria", "Canada", "Mexico",
             "Brazil", "Chile", "Japan", "South Korea", "Australia", "New Zealand", "Thailand", "Kenya", "Morocco", "Turkey",
             "Egypt", "India", "Vietnam", "Argentina", "Peru", "Colombia", "Philippines", "Indonesia", "Ghana", "Tunisia",
             "Jordan", "Uruguay", "Malaysia", "Senegal", "Albania", "Georgia", "Armenia", "Mongolia")
ZONE_PREFIX = ("Zone", "Area", "Region")
LIMITS_G = (500, 1000, 2000, 2500, 3000, 5000, 7000, 10000, 15000, 20000, 25000, 30000, 40000, 50000)
FLAT = ("saturday", "signature", "lithium", "residential", "cod")
CHARGE_P = (("fuel", 0.5), ("express", 0.5), ("oversize", 0.4), ("remote", 0.4), ("insurance", 0.4), ("saturday", 0.3),
            ("signature", 0.3), ("lithium", 0.25), ("residential", 0.3), ("cod", 0.2), ("peak", 0.3))
LABEL_RE = r"\b(?:Zone|Area|Region) [1-5A-E]\b"
MONEY_RE = r"([A-Z]{3}) (\d[\d,]*\.\d{2})"

TITLES = ("{c}: parcel rate card", "Parcel price list of {c}", "{c} - tariff for single parcels", "Courier tariff ({c})",
          "{c} delivery charges", "Rate sheet for the {c} parcel service", "{c}: what a parcel costs")
QUESTIONS = ("What does this parcel cost in total, in {cur}?", "How much will {name} be charged for this parcel?",
             "Which amount appears on the invoice for this shipment?", "What is the final price of this parcel under the tariff?",
             "How much must be paid to send this parcel?", "Under this rate card, what is the total charge for the shipment?")
IRRELEVANT = ("Pick-ups booked after {h}:00 are collected on the next working day.",
              "Damage must be reported within {d} days of delivery.",
              "Tracking updates by e-mail are included at no charge.",
              "Parcels that cannot be delivered are kept at the depot for {d} days.",
              "Labels can be printed at any of our {n} service points.",
              "Delivery times are estimates and are not guaranteed.",
              "Invoices are sent once a month and are payable within {d} days.",
              "The first re-delivery after a failed attempt costs nothing extra.",
              "Customs paperwork is the sender's responsibility.",
              "Our depots are open from 07:00 to {h}:00 on working days.",
              "Packaging material is sold separately at the counter.")


# --------------------------------------------------------------------------------------------------------- helpers

def kg(grams) -> str:
    """0.5, 1, 2.5, 7.4, 3.25 (kg, no trailing zeros except one decimal for weights given in 0.1 kg)."""
    s = f"{Decimal(grams) / 1000:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def weight_text(grams: int) -> str:
    return f"{Decimal(grams) / 1000:.2f}" if grams % 100 else f"{Decimal(grams) / 1000:.1f}"


def pct(tenths: int) -> str:
    return str(tenths // 10) if tenths % 10 == 0 else f"{tenths // 10}.{tenths % 10}"


def m(cents, cur: str) -> str:
    return money(cents / 100, cur)


def _round_cents(x: Fraction) -> Fraction:
    """Half up to whole cents (amounts are never negative)."""
    return Fraction(math.floor(x + Fraction(1, 2)))


# ------------------------------------------------------------------------------------------------------------ draw

def _postcode_zones(rng, nz):
    cuts = sorted(pick(rng, list(range(11, 100)), nz - 1 + rng.randint(0, 2)))
    bounds = [10] + cuts + [100]
    blocks = [[bounds[i] * 1000, bounds[i + 1] * 1000 - 1] for i in range(len(bounds) - 1)]
    owner = list(range(nz)) + [rng.randrange(nz) for _ in range(len(blocks) - nz)]
    rng.shuffle(owner)
    out = []
    for z in range(nz):
        rs = []
        for b, o in zip(blocks, owner):
            if o != z:
                continue
            if rs and rs[-1][1] + 1 == b[0]:
                rs[-1][1] = b[1]          # adjacent blocks of one zone form one range
            else:
                rs.append(list(b))
        out.append(rs)
    return out


def _prices(rng, nz, nb):
    first = [rng.randint(350, 950)]
    for _ in range(nb - 1):
        first.append(int(first[-1] * rng.uniform(1.12, 1.6)))
    grid = [first]
    for _ in range(nz - 1):
        f = rng.uniform(1.15, 1.55)
        grid.append([int(p * f) for p in grid[-1]])
    if rng.random() < 0.4:
        grid = [[max(5, p - p % 5) for p in row] for row in grid]
    for row in grid:
        if any(a >= b for a, b in zip(row, row[1:])):
            raise Retry("prices not increasing")
    for z in range(nz - 1):
        if any(a >= b for a, b in zip(grid[z], grid[z + 1])):
            raise Retry("zones not increasing")
    return grid


def _fee(rng, lo=150, hi=1500):
    v = rng.randint(lo, hi)
    return v - v % rng.choice((1, 5, 10, 50))


def _dims_for(rng, target_cm3, longest=None):
    """Integer box dimensions whose product is close to target_cm3 (exactly when possible)."""
    L = longest or rng.randint(15, 100)
    for _ in range(25):
        W = rng.randint(8, max(8, min(L, 80)))
        if target_cm3 % (L * W) == 0 and 2 <= target_cm3 // (L * W) <= 150:
            return [L, W, target_cm3 // (L * W)]
    W = rng.randint(8, max(8, min(L, 80)))
    return [L, W, max(2, min(150, round(target_cm3 / (L * W))))]


def draw(rng):
    cur = rng.choice(CURRENCIES)
    nz, nb = rng.choice((2, 3, 3, 4, 4, 5)), rng.choice((3, 4, 4, 5, 5, 6))
    domestic = rng.random() < 0.35
    prefix, codes = rng.choice(ZONE_PREFIX), rng.choice(("12345", "ABCDE"))
    labels = [f"{prefix} {codes[i]}" for i in range(nz)]
    if domestic:
        zones = [{"label": l, "ranges": r} for l, r in zip(labels, _postcode_zones(rng, nz))]
    else:
        dests = pick(rng, COUNTRIES, sum(sizes := [rng.randint(2, 4) for _ in range(nz)]))
        zones, k = [], 0
        for l, n in zip(labels, sizes):
            zones.append({"label": l, "dest": dests[k:k + n]})
            k += n
    case = {"cur": cur, "carrier": rng.choice(CARRIERS), "domestic": domestic, "zones": zones,
            "limits": sorted(pick(rng, LIMITS_G, nb)), "incl": rng.random() < 0.5, "prices": _prices(rng, nz, nb),
            "per_kg": rng.randint(30, 250) if rng.random() < 0.4 else None,
            "divisor": rng.choice((None, 4000, 5000, 5000, 6000)), "wround": rng.choice((0, 0, 500, 1000, 1000))}
    charges = {}
    for name, p in CHARGE_P:
        if rng.random() < p:
            charges[name] = None
    if len(charges) < 2:
        for name in pick(rng, [n for n, _ in CHARGE_P if n not in charges], 2 - len(charges)):
            charges[name] = None
    charges = {n: None for n, _ in CHARGE_P if n in charges}     # fixed order (rendering shuffles)
    disc = None
    if rng.random() < 0.45:
        kind = rng.choice(("base", "base", "net", "net", "voucher"))
        disc = {"kind": kind, "cond": rng.choice((None, None, "online", "account")),
                "pct": rng.choice((50, 75, 100, 120, 150, 200, 250)) if kind != "voucher" else None,
                "amount": _fee(rng, 200, 1200) if kind == "voucher" else None}
    case["discount"] = disc
    for name in charges:
        if name == "fuel":
            charges[name] = {"pct": rng.randrange(35, 190, 5), "after": (rng.random() < 0.5) if disc and disc["kind"] == "base" else None}
        elif name == "express":
            charges[name] = {"pct": rng.randrange(100, 610, 50), "fee": None} if rng.random() < 0.5 else {"pct": None, "fee": _fee(rng, 300, 2000)}
        elif name == "oversize":
            charges[name] = {"side": rng.choice((60, 80, 100, 120, 150)), "incl": rng.random() < 0.5, "fee": _fee(rng, 500, 3500)}
        elif name == "remote":
            if domestic:
                charges[name] = {"prefixes": sorted(pick(rng, [f"{i}" for i in range(10, 100)], rng.randint(2, 3))), "dest": None,
                                 "fee": _fee(rng, 200, 1500)}
            else:
                pool = [d for z in zones for d in z["dest"]]
                charges[name] = {"prefixes": None, "dest": pick(rng, pool, min(len(pool) - 1, rng.randint(2, 3))),
                                 "fee": _fee(rng, 200, 1500)}
        elif name == "insurance":
            charges[name] = {"pct": rng.randrange(5, 35, 5), "min": _fee(rng, 150, 800)}
        elif name == "peak":
            start = date(2026, 11, 1) + timedelta(days=rng.randint(5, 30))
            charges[name] = {"start": start.isoformat(), "end": (start + timedelta(days=rng.randint(10, 40))).isoformat(),
                             "fee": _fee(rng, 100, 900)}
        else:
            charges[name] = {"fee": _fee(rng)}
    case["charges"] = charges
    case["vat"] = rng.choice((50, 70, 80, 100, 120, 150, 160, 190, 200, 210, 230, 250)) if rng.random() < 0.5 else None
    mode = rng.choice(("each", "each", "final", "final", "coarse"))
    case["rounding"] = {"mode": mode, "step": rng.choice((5, 10, 50, 100)) if mode == "coarse" else 1,
                        "dir": rng.choice(("nearest", "up")) if mode == "coarse" else "nearest"}
    case["irrelevant"] = [t.format(h=rng.choice((15, 16, 17, 18)), d=rng.choice((5, 7, 10, 14, 30)), n=rng.randint(40, 900))
                          for t in pick(rng, IRRELEVANT, rng.randint(1, 3))]
    case["shipment"] = _shipment(rng, case)
    case["minimum"] = None
    if rng.random() < 0.2:
        net = _price(case, {"stop": "net"})
        case["minimum"] = max(100, int(net * rng.uniform(0.75, 1.3)) // 100 * 100)
    gold = _price(case)
    case["options"] = _options(rng, case, gold, 5 if rng.random() < 0.73 else 4)
    return case


def _shipment(rng, case):
    zones, ch = case["zones"], case["charges"]
    z = rng.randrange(len(zones))
    if case["domestic"]:
        if "remote" in ch and rng.random() < 0.4:
            p = int(rng.choice(ch["remote"]["prefixes"]))
            dest = p * 1000 + rng.randint(0, 999)
        else:
            lo, hi = rng.choice(zones[z]["ranges"])
            dest = rng.randint(lo, hi)
    else:
        if "remote" in ch and rng.random() < 0.4:
            dest = rng.choice(ch["remote"]["dest"])
        else:
            dest = rng.choice(zones[z]["dest"])
    lim, top = case["limits"], case["limits"][-1]
    if case["per_kg"] and rng.random() < 0.15:
        target = top + rng.randint(1, 120) * 100
    else:
        b = rng.randrange(len(lim))
        lo, hi = (lim[b - 1] if b else 0), lim[b]
        r = rng.random()
        target = hi if r < 0.18 else lo if (r < 0.3 and lo) else rng.randint(lo // 100 + 1, max(lo // 100 + 1, hi // 100 - 1)) * 100
    target = max(100, target)
    longest = None
    if "oversize" in ch and rng.random() < 0.55:
        longest = ch["oversize"]["side"] + rng.choice((-4, -1, 0, 0, 1, 3, 8))
    div = case["divisor"]
    if div and rng.random() < 0.5:               # the volumetric weight decides
        dims = _dims_for(rng, target * div // 1000, longest)
        vol_g = Fraction(dims[0] * dims[1] * dims[2] * 1000, div)
        weight = max(100, int(vol_g * Fraction(rng.randint(35, 95), 100)) // 100 * 100)
    else:                                        # the actual weight decides (or there is no volumetric rule)
        weight = target if rng.random() < 0.75 else target + rng.choice((-50, -30, 20, 40))
        weight = max(100, weight)
        dims = _dims_for(rng, max(400, int(weight * (div or 5000) // 1000 * rng.uniform(0.2, 0.9))), longest)
    rng.shuffle(dims)
    s = {"sender": rng.choice(NAMES), "dest": dest, "weight": weight, "dims": dims,
         "declared": rng.randint(15, 1500) * 100 + rng.choice((0, 0, 0, 50, 99)),
         "express": rng.random() < 0.5, "insured": rng.random() < 0.45, "online": rng.random() < 0.5,
         "account": rng.random() < 0.5}
    for f in FLAT:
        s[f] = rng.random() < 0.4
    if "peak" in ch:
        p = ch["peak"]
        st, en = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        d = rng.choice((st - timedelta(days=1), st, en, en + timedelta(days=1), st + timedelta(days=rng.randint(1, 9)),
                        st - timedelta(days=rng.randint(2, 40)), en + timedelta(days=rng.randint(2, 30))))
    else:
        d = date(2026, 9, 1) + timedelta(days=rng.randint(0, 150))
    s["date"] = d.isoformat()
    case["shipment"] = s
    cw = _chargeable(case)
    if not case["per_kg"] and (cw > Fraction(top, 1000) if case["incl"] else cw >= Fraction(top, 1000)):
        raise Retry("heavier than the top band")
    if case["discount"] and case["discount"]["kind"] == "voucher" and _price(case, {"stop": "subtotal"}) <= case["discount"]["amount"] + 100:
        raise Retry("voucher larger than the price")
    return s


# ----------------------------------------------------------------------------------------------------------- solve

def zone_index(case, dest=None) -> int:
    dest = case["shipment"]["dest"] if dest is None else dest
    for i, z in enumerate(case["zones"]):
        if case["domestic"] and any(lo <= dest <= hi for lo, hi in z["ranges"]):
            return i
        if not case["domestic"] and dest in z["dest"]:
            return i
    raise ValueError(f"destination {dest} in no zone")


def _chargeable(case, how=None) -> Fraction:
    s = case["shipment"]
    actual = Fraction(s["weight"], 1000)
    vol = Fraction(s["dims"][0] * s["dims"][1] * s["dims"][2], case["divisor"]) if case["divisor"] else None
    if vol is None or how == "actual":
        cw = actual
    elif how == "smaller":
        cw = min(actual, vol)
    else:
        cw = max(actual, vol)
    if case["wround"] and how != "no_round":
        step = Fraction(case["wround"], 1000)
        cw = math.ceil(cw / step) * step
    return cw


def band(case, cw: Fraction) -> tuple[int, int]:
    """(band index, started kg above the top band)."""
    lim = [Fraction(x, 1000) for x in case["limits"]]
    for i, u in enumerate(lim):
        if (cw <= u) if case["incl"] else (cw < u):
            return i, 0
    return len(lim) - 1, math.ceil(cw - lim[-1])


def applies(case, name) -> bool:
    s, p = case["shipment"], case["charges"][name]
    if name == "fuel":
        return True
    if name == "express":
        return s["express"]
    if name == "oversize":
        side = max(s["dims"])
        return side >= p["side"] if p["incl"] else side > p["side"]
    if name == "remote":
        return str(s["dest"])[:2] in p["prefixes"] if case["domestic"] else s["dest"] in p["dest"]
    if name == "insurance":
        return s["insured"]
    if name == "peak":
        return p["start"] <= s["date"] <= p["end"]
    return s[name]


def discount_applies(case) -> bool:
    d = case["discount"]
    return bool(d) and (d["cond"] is None or case["shipment"][d["cond"]])


def _price(case, mods=None) -> int:
    """The price in cents (exact rational arithmetic); ``mods`` reproduce one named mistake."""
    mods = mods or {}
    s, ch = case["shipment"], case["charges"]
    rnd = case["rounding"]
    mode = mods.get("mode", rnd["mode"])
    R = _round_cents if mode == "each" else (lambda x: x)
    cw = _chargeable(case, mods.get("weight"))
    z = zone_index(case) + mods.get("zone", 0)
    b, extra = band(case, cw)
    if "band" in mods:
        b, extra = b + mods["band"], 0
    if not 0 <= z < len(case["zones"]) or not 0 <= b < len(case["limits"]):
        raise LookupError("no such zone or band")
    if mods.get("no_extra"):
        extra = 0
    base = Fraction(case["prices"][z][b] + extra * (case["per_kg"] or 0))
    d = case["discount"]
    d_on = discount_applies(case)
    if mods.get("discount") == "skip":
        d_on = False
    elif mods.get("discount") == "force":
        d_on = bool(d)
    disc_amt = Fraction(0)
    base_after = base
    if d_on and d["kind"] == "base":
        disc_amt = R(base * Fraction(d["pct"], 1000))
        base_after = base - disc_amt
    charges = []
    for name, p in ch.items():
        on = applies(case, name)
        if mods.get("drop") == name:
            on = False
        if mods.get("add") == name:
            on = True
        if not on:
            continue
        if name == "fuel":
            after = p["after"] if mods.get("fuel") != "swap" else not p["after"]
            amt = R(Fraction(p["pct"], 1000) * (base_after if after else base))
        elif name == "express" and p["pct"]:
            amt = R(Fraction(p["pct"], 1000) * base)
        elif name == "insurance":
            amt = max(R(Fraction(p["pct"], 1000) * s["declared"]), Fraction(p["min"]))
        else:
            amt = Fraction(p["fee"])
        charges.append(amt * (2 if mods.get("double") == name else 1))
    subtotal = base_after + sum(charges)
    if mods.get("stop") == "subtotal":
        return int(subtotal)
    net = subtotal
    if d_on and d["kind"] == "net":
        disc_amt = R(subtotal * Fraction(d["pct"], 1000))
        net = subtotal - disc_amt
    elif d_on and d["kind"] == "voucher":
        disc_amt = Fraction(d["amount"])
        net = subtotal - disc_amt
    if case.get("minimum") and not mods.get("no_min"):
        net = max(net, Fraction(case["minimum"]))
    if mods.get("stop") == "net":
        return int(net)
    total = net
    if case["vat"] and not mods.get("no_vat"):
        if mods.get("vat_order") and disc_amt:
            pre = net + disc_amt
            total = pre + R(pre * Fraction(case["vat"], 1000)) - disc_amt
        else:
            total = net + R(net * Fraction(case["vat"], 1000))
    step = rnd["step"] if rnd["mode"] == "coarse" else 1
    direction = rnd["dir"] if not mods.get("flip_dir") else ("up" if rnd["dir"] == "nearest" else "nearest")
    if direction == "up" and step > 1:
        return math.ceil(total / step) * step
    return math.floor(total / step + Fraction(1, 2)) * step


def _mistakes(case) -> list[dict]:
    ch, s = case["charges"], case["shipment"]
    out = [{"band": 1}, {"band": -1}, {"zone": 1}, {"zone": -1}]
    if case["divisor"]:
        out += [{"weight": "actual"}, {"weight": "smaller"}]
    if case["wround"]:
        out.append({"weight": "no_round"})
    if band(case, _chargeable(case))[1]:
        out.append({"no_extra": True})
    for name in ch:
        if applies(case, name):
            out.append({"drop": name})
            out.append({"double": name})
        else:
            out.append({"add": name})
    if "fuel" in ch and ch["fuel"]["after"] is not None and discount_applies(case):
        out.append({"fuel": "swap"})
    if case["discount"]:
        out.append({"discount": "skip"} if discount_applies(case) else {"discount": "force"})
        if case["vat"] and discount_applies(case):
            out.append({"vat_order": True})
    if case["vat"]:
        out.append({"no_vat": True})
    if case.get("minimum"):
        out.append({"no_min": True})
    mode = case["rounding"]["mode"]
    out.append({"mode": "final"} if mode == "each" else {"mode": "each"} if mode == "final" else {"flip_dir": True})
    return out


def _options(rng, case, gold, k):
    """Gold + k-1 distractors. The gold's rank among the sorted values is drawn uniformly (no 'middle value' cue); each side
    is filled with named mistakes first, then near values on the same rounding step."""
    below_n = rng.randrange(k)
    named = _mistakes(case)
    rng.shuffle(named)
    lo, hi = [], []
    for mods in named:
        try:
            v = _price(case, mods)
        except LookupError:
            continue
        if v <= 0 or v == gold or v in lo or v in hi:
            continue
        side = lo if v < gold else hi
        if len(side) < (below_n if side is lo else k - 1 - below_n):
            side.append(v)
    step = case["rounding"]["step"] if case["rounding"]["mode"] == "coarse" else 1
    for side, sign, want in ((lo, -1, below_n), (hi, 1, k - 1 - below_n)):
        tries = 0
        while len(side) < want:
            tries += 1
            if tries > 60:
                raise Retry("no near values")
            v = gold + sign * max(1, round(gold * rng.randint(2, 14) / 100 / step)) * step
            if v > 0 and v not in lo and v not in hi:
                side.append(v)
    vals = lo + hi
    rng.shuffle(vals)
    return [gold] + vals


def solve(case):
    return [case["options"].index(_price(case))]


# ---------------------------------------------------------------------------------------------------------- render

def _desc(case, i) -> str:
    lim = case["limits"]
    if case["incl"]:
        return f"up to and including {kg(lim[0])} kg" if i == 0 else f"over {kg(lim[i - 1])} kg, up to and including {kg(lim[i])} kg"
    return f"under {kg(lim[0])} kg" if i == 0 else f"{kg(lim[i - 1])} kg to under {kg(lim[i])} kg"


def _table(case, rng) -> str:
    cur, zones, P = case["cur"], case["zones"], case["prices"]
    rule = ("a weight exactly on a band limit belongs to the lower band" if case["incl"]
            else "a weight exactly on a band limit belongs to the next band up")
    head = rng.choice((f"Base price per parcel by zone and chargeable weight ({rule}):",
                       f"Base prices ({rule}):",
                       f"Base price table, by chargeable weight band and zone; {rule}:"))
    layout = rng.choice(("grid", "band", "zone"))
    rows = []
    if layout == "grid":
        rows.append("Chargeable weight | " + " | ".join(z["label"] for z in zones))
        for i in range(len(case["limits"])):
            rows.append(_desc(case, i) + " | " + " | ".join(m(P[z][i], cur) for z in range(len(zones))))
    elif layout == "band":
        for i in range(len(case["limits"])):
            rows.append(_desc(case, i) + ": " + ", ".join(f"{zones[z]['label']} {m(P[z][i], cur)}" for z in range(len(zones))))
    else:
        for z in range(len(zones)):
            rows.append(zones[z]["label"] + ": " + ", ".join(f"{m(P[z][i], cur)} ({_desc(case, i)})" for i in range(len(case["limits"]))))
    return head + "\n" + "\n".join("   " + r for r in rows)


def _zones(case, rng) -> str:
    head = rng.choice(("Destination zones:", "Zones:", "Zone assignment:", "Delivery zones by destination:"))
    style = rng.randrange(3)
    parts = []
    for z in case["zones"]:
        if case["domestic"]:
            what = " and ".join(f"postcodes {lo} to {hi}" for lo, hi in z["ranges"])
        else:
            what = ", ".join(z["dest"][:-1]) + " and " + z["dest"][-1] if len(z["dest"]) > 1 else z["dest"][0]
        parts.append((f"{z['label']} = {what}", f"{z['label']} covers {what}", f"{z['label']}: {what}")[style])
    tail = " (both ends of every postcode range are included)" if case["domestic"] else ""
    return head + " " + "; ".join(parts) + tail + "."


def _weight(case, rng) -> str:
    div = case["divisor"]
    if div:
        t = rng.choice((f"Chargeable weight: whichever is greater of the scale weight and the dimensional weight; dimensional weight in kg = L x W x H (all in cm) / {div}.",
                        f"We bill the greater of two figures: the weight on the scale, or the dimensional weight, which is the box volume in cubic centimetres divided by {div} (result in kg)."))
    else:
        t = rng.choice(("Chargeable weight: the scale weight; the size of the parcel does not change the base price.",
                        "We bill the weight on the scale; there is no dimensional weight rule."))
    r = {0: " The chargeable weight is not rounded.", 500: " The chargeable weight is rounded up to the next half kilogram (0.5 kg) before the band is looked up.",
         1000: " The chargeable weight is rounded up to the next full kilogram before the band is looked up."}[case["wround"]]
    return t + r


def _over(case) -> str:
    top, cur = kg(case["limits"][-1]), case["cur"]
    heavy = f"Parcels heavier than {top} kg" if case["incl"] else f"Parcels of {top} kg or more"
    if case["per_kg"]:
        return (f"{heavy}: the price of the last band plus {m(case['per_kg'], cur)} for every started kilogram above {top} kg; "
                "this is part of the base price.")
    return f"{heavy} are not accepted."


def _discount_name(d) -> str:
    return {None: "Standing discount", "online": "Online booking discount", "account": "Business-account discount"}[d["cond"]]


def _charge_text(case, name, rng) -> str:
    p, cur = case["charges"][name], case["cur"]
    if name == "fuel":
        on = {None: "the base price", True: "the base price after the discount", False: "the base price before any discount"}[p["after"]]
        return rng.choice((f"Fuel surcharge: {pct(p['pct'])} % of {on}.", f"A fuel surcharge of {pct(p['pct'])} % is charged on {on}."))
    if name == "express":
        if p["pct"]:
            on = "the base price before any discount" if case["discount"] and case["discount"]["kind"] == "base" else "the base price"
            return f"Express service: an extra {pct(p['pct'])} % of {on} (standard service has no extra charge)."
        return f"Express service: {m(p['fee'], cur)} extra per parcel; standard service costs nothing extra."
    if name == "oversize":
        if p["incl"]:
            return f"Oversize charge: {m(p['fee'], cur)} if the longest side is {p['side']} cm or more."
        return f"Oversize charge: {m(p['fee'], cur)} if the longest side is more than {p['side']} cm (exactly {p['side']} cm is not oversize)."
    if name == "remote":
        if case["domestic"]:
            pre = p["prefixes"]
            return f"Remote-area surcharge: {m(p['fee'], cur)} for postcodes starting with {', '.join(pre[:-1])} or {pre[-1]}."
        dl = p["dest"]
        return f"Remote-area surcharge: {m(p['fee'], cur)} for deliveries to {', '.join(dl[:-1])} or {dl[-1]}."
    if name == "insurance":
        return f"Insurance, only when requested: {pct(p['pct'])} % of the declared value, at least {m(p['min'], cur)}."
    if name == "peak":
        return f"Peak-season surcharge: {m(p['fee'], cur)} per parcel handed over from {p['start']} to {p['end']}, both dates included."
    return {"saturday": f"Saturday delivery, on request: {m(p['fee'], cur)}.",
            "signature": f"Signature on delivery, on request: {m(p['fee'], cur)}.",
            "lithium": f"Parcels containing lithium batteries: {m(p['fee'], cur)} handling charge.",
            "residential": f"Delivery to a private address: {m(p['fee'], cur)}; business addresses pay nothing extra.",
            "cod": f"Cash on delivery: {m(p['fee'], cur)} collection fee."}[name]


def _discount_text(case) -> str:
    d, cur = case["discount"], case["cur"]
    cond = {None: "for every parcel", "online": "only for parcels booked online",
            "account": "only for senders with a business account"}[d["cond"]]
    if d["kind"] == "base":
        return f"{_discount_name(d)} ({cond}): {pct(d['pct'])} % off the base price; surcharges are not discounted."
    if d["kind"] == "net":
        return f"{_discount_name(d)} ({cond}): {pct(d['pct'])} % off the net amount (base price plus all surcharges)."
    return f"{_discount_name(d)} ({cond}): a credit of {m(d['amount'], cur)} is deducted from the net amount (base price plus all surcharges)."


def _order(case, rng) -> str:
    d = case["discount"]
    steps = ["work out the chargeable weight", "look up the base price"]
    if d and d["kind"] == "base":
        steps.append(f"apply the {_discount_name(d).lower()} to the base price")
    steps.append("add the surcharges")
    if d and d["kind"] != "base":
        steps.append(f"apply the {_discount_name(d).lower()} to the net amount")
    if case.get("minimum"):
        steps.append("apply the minimum charge")
    if case["vat"]:
        steps.append("add VAT")
    steps.append("round")
    if rng.random() < 0.5:
        return "Order of calculation: " + "; then ".join(steps) + "."
    return "Calculate in this order: " + " ".join(f"({i}) {s}" for i, s in enumerate(steps, 1)) + "."


def _rounding(case) -> str:
    r, cur = case["rounding"], case["cur"]
    if r["mode"] == "each":
        return (f"Rounding: every percentage amount (discount, surcharges, insurance, VAT) is rounded to the nearest {m(1, cur)}, "
                "halves up, as soon as it is calculated.")
    if r["mode"] == "final":
        return f"Rounding: keep all intermediate amounts unrounded and round only the final price to the nearest {m(1, cur)}, halves up."
    how = f"to the nearest {m(r['step'], cur)}, halves up" if r["dir"] == "nearest" else f"up to the next full {m(r['step'], cur)}"
    return f"Rounding: no intermediate amount is rounded; only the amount due at the very end is rounded, {how}."


def _shipment_text(case, rng) -> str:
    s, ch, cur = case["shipment"], case["charges"], case["cur"]
    dest = f"postcode {s['dest']}" if case["domestic"] else s["dest"]
    L, W, H = s["dims"]
    frags = [rng.choice((f"destination {dest}", f"to be delivered to {dest}")),
             rng.choice((f"scale weight {weight_text(s['weight'])} kg", f"weighs {weight_text(s['weight'])} kg")),
             rng.choice((f"box of {L} x {W} x {H} cm", f"measures {L} cm by {W} cm by {H} cm")),
             rng.choice((f"declared value {m(s['declared'], cur)}", f"contents declared at {m(s['declared'], cur)}")),
             rng.choice((f"handed over on {s['date']}", f"posted on {s['date']}"))]
    flags = {"express": ("express service", "standard service"), "insured": ("insurance requested", "no insurance requested"),
             "saturday": ("Saturday delivery requested", "no Saturday delivery"),
             "signature": ("signature on delivery requested", "no signature service"),
             "lithium": ("contains lithium batteries", "no lithium batteries"),
             "residential": ("to a private address", "to a business address"),
             "cod": ("cash on delivery", "prepaid, no cash on delivery"),
             "online": ("booked online", "booked at a service counter"),
             "account": ("sender has a business account", "private sender without a business account")}
    needed = {"express": "express" in ch, "insured": "insurance" in ch, "saturday": "saturday" in ch, "signature": "signature" in ch,
              "lithium": "lithium" in ch, "residential": "residential" in ch, "cod": "cod" in ch,
              "online": bool(case["discount"]) and case["discount"]["cond"] == "online",
              "account": bool(case["discount"]) and case["discount"]["cond"] == "account"}
    for f, (yes, no) in flags.items():
        if needed[f] or rng.random() < 0.3:
            frags.append(yes if s[f] else no)
    head = frags[:1]
    rest = frags[1:]
    rng.shuffle(rest)
    lead = rng.choice((f"Shipment: {s['sender']} sends one parcel; ", f"Parcel details ({s['sender']}): ",
                       f"{s['sender']} books one parcel: "))
    return lead + "; ".join(head + rest) + "."


def render(case, rng):
    title = rng.choice(TITLES).format(c=case["carrier"])
    clauses = [_zones(case, rng), _weight(case, rng), _over(case)]
    clauses += [_charge_text(case, n, rng) for n in case["charges"]]
    if case["discount"]:
        clauses.append(_discount_text(case))
    if case.get("minimum"):
        clauses.append(f"Minimum charge: the net amount after any discount is never less than {m(case['minimum'], case['cur'])}; "
                       "a lower amount is raised to it.")
    if case["vat"]:
        clauses.append(f"VAT: {pct(case['vat'])} % is added to the net amount (after any discount and minimum charge).")
    elif rng.random() < 0.5:
        clauses.append("No VAT or other tax is added to these prices.")
    clauses += case["irrelevant"]
    rng.shuffle(clauses)
    table = _table(case, rng)
    clauses.insert(0 if rng.random() < 0.6 else rng.randint(1, len(clauses)), table)
    tail = [_order(case, rng), _rounding(case)]
    rng.shuffle(tail)
    clauses += tail
    style = rng.randrange(3)
    lines = [(f"{i}. {c}", f"- {c}", f"* {c}")[style] for i, c in enumerate(clauses, 1)]
    text = (title + "\n" + "\n".join(lines) + "\n\n" + _shipment_text(case, rng) + "\n\n"
            + rng.choice(QUESTIONS).format(cur=case["cur"], name=case["shipment"]["sender"]))
    return [{"instructions": text, "options": [m(v, case["cur"]) for v in case["options"]]}]


# ------------------------------------------------------------------------------------------------- second solver

def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def _money_in(text: str) -> list[Decimal]:
    return [_dec(a) for _, a in re.findall(MONEY_RE, text)]


def _one(pattern: str, text: str, group: int = 1):
    mt = re.search(pattern, text)
    return mt.group(group) if mt else None


def solve_text(q: dict) -> str:
    """Reads only the rendered question: the tariff clauses, the shipment line, the options. Decimal arithmetic."""
    text = q["instructions"]
    tariff, shipment, _question = text.split("\n\n")
    lines = tariff.splitlines()[1:]
    # ---- price table
    incl = "up to and including" in tariff
    desc_re = (r"(?:up to and including|over [\d.]+ kg, up to and including) ([\d.]+) kg" if incl
               else r"(?:under|[\d.]+ kg to under) ([\d.]+) kg")
    header = None
    table: dict[tuple[str, Decimal], Decimal] = {}
    for ln in lines:
        body = ln.strip()
        if "|" in body:
            cells = [c.strip() for c in body.split("|")]
            if not re.search(MONEY_RE, body):
                header = [re.match(LABEL_RE, c).group(0) for c in cells[1:]]
                continue
            up = Decimal(re.fullmatch(desc_re, cells[0]).group(1))
            for lab, cell in zip(header, cells[1:]):
                table[(lab, up)] = _money_in(cell)[0]
        elif re.match(desc_re, body) and re.search(MONEY_RE, body):
            up = Decimal(re.match(desc_re, body).group(1))
            for lab, _c, amt in re.findall(rf"({LABEL_RE}) {MONEY_RE}", body):
                table[(lab, up)] = _dec(amt)
        elif re.match(rf"({LABEL_RE}): {MONEY_RE}", body):
            lab = re.match(LABEL_RE, body).group(0)
            for _c, amt, dsc in re.findall(rf"{MONEY_RE} \(([^)]*)\)", body):
                table[(lab, Decimal(re.fullmatch(desc_re, dsc).group(1)))] = _dec(amt)
    uppers = sorted({u for _, u in table})
    labels = sorted({lab for lab, _ in table})
    cur = re.search(MONEY_RE, tariff).group(1)
    # ---- zones
    zline = next(ln for ln in lines if all(lab in ln for lab in labels) and "|" not in ln and not re.search(MONEY_RE, ln))
    pieces = re.split(rf"({LABEL_RE})", zline)
    segs = {pieces[i]: pieces[i + 1] for i in range(1, len(pieces) - 1, 2)}
    pc = re.search(r"postcode (\d{5})", shipment)
    if pc:
        code = int(pc.group(1))
        zone = next(lab for lab, sg in segs.items()
                    if any(int(a) <= code <= int(b) for a, b in re.findall(r"postcodes (\d{5}) to (\d{5})", sg)))
        dest = pc.group(1)
    else:
        found = [(lab, d) for lab, sg in segs.items() for d in re.findall(r"[A-Z][A-Za-z]+(?: [A-Z][a-z]+)?", sg)
                 if re.search(rf"\b{re.escape(d)}\b", shipment)]
        zone, dest = found[0]
    # ---- chargeable weight
    actual = Decimal(re.search(r"(?:scale weight|weighs) ([\d.]+) kg", shipment).group(1))
    dims = re.search(r"(\d+) x (\d+) x (\d+) cm|(\d+) cm by (\d+) cm by (\d+) cm", shipment)
    L, W, H = [int(g) for g in dims.groups() if g is not None]
    div = _one(r"(?:\(all in cm\) /|centimetres divided by) (\d{4})", tariff)
    cw = max(actual, Decimal(L * W * H) / Decimal(div)) if div else actual
    if "next half kilogram" in tariff:
        cw = (cw / Decimal("0.5")).to_integral_value(ROUND_CEILING) * Decimal("0.5")
    elif "next full kilogram before the band" in tariff:
        cw = cw.to_integral_value(ROUND_CEILING)
    top = uppers[-1]
    over_m = re.search(rf"plus {MONEY_RE} for every started kilogram above ([\d.]+) kg", tariff)
    for u in uppers:
        if (cw <= u) if incl else (cw < u):
            base = table[(zone, u)]
            break
    else:
        extra = (cw - top).to_integral_value(ROUND_CEILING)
        base = table[(zone, top)] + extra * _dec(over_m.group(2))
    # ---- flags of the shipment
    def flag(yes: str, no: str) -> bool:
        if no in shipment:
            return False
        return yes in shipment
    each = "as soon as it is calculated" in tariff
    R = (lambda x: x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if each else (lambda x: x)
    # ---- discount
    dline = next((ln for ln in lines if re.search(r"discount \((?:for every|only for)", ln)), None)
    dkind = dpct = damt = None
    d_ok = False
    if dline:
        if "only for parcels booked online" in dline:
            d_ok = flag("booked online", "booked at a service counter")
        elif "only for senders with a business account" in dline:
            d_ok = flag("sender has a business account", "private sender without a business account")
        else:
            d_ok = True
        if "% off the base price" in dline:
            dkind, dpct = "base", Decimal(_one(r"([\d.]+) % off the base price", dline)) / 100
        elif "% off the net amount" in dline:
            dkind, dpct = "net", Decimal(_one(r"([\d.]+) % off the net amount", dline)) / 100
        else:
            dkind, damt = "voucher", _dec(_one(rf"a credit of {MONEY_RE}", dline, 2))
    base_after = base - R(base * dpct) if (d_ok and dkind == "base") else base
    # ---- surcharges
    adds = []
    for ln in lines:
        if "Fuel surcharge:" in ln or "A fuel surcharge of" in ln:
            p = Decimal(_one(r"([\d.]+) %", ln)) / 100
            adds.append(R(p * (base_after if "after the discount" in ln else base)))
        elif "Express service:" in ln:
            if flag("express service", "standard service"):
                adds.append(R(Decimal(_one(r"an extra ([\d.]+) %", ln)) / 100 * base) if "an extra" in ln else _money_in(ln)[0])
        elif "Oversize charge:" in ln:
            side = int(_one(r"(\d+) cm", ln))
            if (max(L, W, H) >= side) if "or more" in ln else (max(L, W, H) > side):
                adds.append(_money_in(ln)[0])
        elif "Remote-area surcharge:" in ln:
            if pc:
                hit = dest[:2] in re.findall(r"\b(\d{2})\b", ln.split("starting with", 1)[1])
            else:
                hit = re.search(rf"\b{re.escape(dest)}\b", ln.split("deliveries to", 1)[1]) is not None
            if hit:
                adds.append(_money_in(ln)[0])
        elif "Insurance, only when requested:" in ln:
            if flag("insurance requested", "no insurance requested"):
                p = Decimal(_one(r"([\d.]+) % of the declared value", ln)) / 100
                declared = _money_in(re.search(rf"(?:declared value|declared at) {MONEY_RE}", shipment).group(0))[0]
                adds.append(max(R(p * declared), _money_in(ln)[0]))
        elif "Peak-season surcharge:" in ln:
            a, b = re.findall(r"\d{4}-\d{2}-\d{2}", ln)
            if a <= re.search(r"\d{4}-\d{2}-\d{2}", shipment).group(0) <= b:
                adds.append(_money_in(ln)[0])
        else:
            for key, yes, no in (("Saturday delivery, on request:", "Saturday delivery requested", "no Saturday delivery"),
                                 ("Signature on delivery, on request:", "signature on delivery requested", "no signature service"),
                                 ("lithium batteries:", "contains lithium batteries", "no lithium batteries"),
                                 ("Delivery to a private address:", "to a private address", "to a business address"),
                                 ("Cash on delivery:", "cash on delivery", "prepaid, no cash on delivery")):
                if key in ln and flag(yes, no):
                    adds.append(_money_in(ln)[0])
    net = base_after + sum(adds, Decimal(0))
    if d_ok and dkind == "net":
        net -= R(net * dpct)
    elif d_ok and dkind == "voucher":
        net -= damt
    mn = re.search(rf"never less than {MONEY_RE}", tariff)
    if mn:
        net = max(net, _dec(mn.group(2)))
    vat = _one(r"VAT: ([\d.]+) % is added", tariff)
    total = net + R(net * Decimal(vat) / 100) if vat else net
    coarse = re.search(rf"at the very end is rounded, (to the nearest|up to the next full) {MONEY_RE}", tariff)
    if coarse and not each:
        step = _dec(coarse.group(3))
        mode = ROUND_HALF_UP if coarse.group(1) == "to the nearest" else ROUND_CEILING
        total = (total / step).to_integral_value(mode) * step
    else:
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    want = f"{cur} {total:,.2f}"
    hits = [k for k, v in q["criteria"].items() if v == want]
    if len(hits) != 1:
        raise ValueError(f"computed {want}, not among the options")
    return hits[0]
