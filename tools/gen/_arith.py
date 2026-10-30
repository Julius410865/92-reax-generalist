"""Shared generator of arith_word_4 / arith_word_10: multi-step arithmetic word problems with one integer answer.

Not a task module (the leading underscore keeps it out of gen_generalist's registry); arith_word_4.py and arith_word_10.py
bind it to 4 and 10 options.

A case is a starting quantity plus a chain of 3-6 operations, drawn per item:
* item counts: add, add full boxes, remove, double / triple / quadruple, remove a fraction (half, a third, ...), remove or
  add a percentage, split equally (between partners or into parts) and keep one share, a daily rate for a number of days
  (plain or an ISO date range with both dates included);
* a sale that turns the remaining items into money (price per item), then money steps of the same kinds;
* or a chain on money only.
Every item states one rounding rule: the direction (down / up / nearest with halves up) and where it applies (after every
step, or only on the final answer with exact fractions carried before). The gold value comes from ``solve``; the
distractors are named mistakes first (a dropped step, two adjacent steps swapped, a removal read as an addition, the
percentage of the wrong quantity, the complement of a percentage or fraction, a split that forgets to count the person,
a date range counted without one end, rounding at the wrong step or in the wrong direction), then near values.
"""

from __future__ import annotations

import datetime
import math
import re
from fractions import Fraction as F

from tools.gen.base import Retry

NAMES = ("Aiko", "Bastian", "Chiara", "Elif", "Farah", "Goran", "Hana", "Ilse", "Jonas", "Kalani", "Lucia", "Mateo",
         "Nadia", "Oskar", "Priya", "Quentin", "Rosa", "Sven", "Tamar", "Umar", "Vera", "Wendell", "Zofia", "Amara",
         "Bruno", "Cyrus", "Dalia", "Emeka", "Freya", "Gideon", "Hiro", "Ines", "Jamal", "Anouk", "Benedikt", "Carmen",
         "Desmond", "Esther", "Fintan", "Greta", "Henrik", "Isolde", "Joaquin", "Katya", "Leopold", "Marisol", "Niamh",
         "Orla", "Pavel", "Rania", "Stellan", "Tove", "Ulla", "Viktor", "Wanjiru", "Yara", "Zeno", "Albin", "Beatriz",
         "Clemens", "Dorota", "Eamon", "Fiona", "Gustav", "Helga", "Jorunn", "Kwame", "Lavinia", "Malik", "Nora",
         "Ottilie", "Petra", "Ruben", "Siobhan", "Teodor", "Una", "Vilma", "Wiebke", "Xaver", "Yasmin", "Zuzana")

# (place, article, item singular, item plural, container singular, container plural)
SETTINGS = (
    ("bakery", "a", "bread roll", "bread rolls", "tray", "trays"),
    ("seed nursery", "a", "seed packet", "seed packets", "carton", "cartons"),
    ("bicycle workshop", "a", "inner tube", "inner tubes", "box", "boxes"),
    ("second-hand bookshop", "a", "paperback", "paperbacks", "crate", "crates"),
    ("apiary", "an", "jar of honey", "jars of honey", "crate", "crates"),
    ("hardware store", "a", "padlock", "padlocks", "carton", "cartons"),
    ("toy shop", "a", "jigsaw puzzle", "jigsaw puzzles", "carton", "cartons"),
    ("flower stall", "a", "tulip bulb", "tulip bulbs", "bag", "bags"),
    ("tea merchant's shop", "a", "tin of tea", "tins of tea", "case", "cases"),
    ("farm shop", "a", "egg", "eggs", "tray", "trays"),
    ("tennis club", "a", "tennis ball", "tennis balls", "tub", "tubs"),
    ("museum gift shop", "a", "postcard", "postcards", "pack", "packs"),
    ("candle workshop", "a", "beeswax candle", "beeswax candles", "box", "boxes"),
    ("soap workshop", "a", "bar of soap", "bars of soap", "carton", "cartons"),
    ("music shop", "a", "set of guitar strings", "sets of guitar strings", "box", "boxes"),
    ("stationery shop", "a", "notebook", "notebooks", "box", "boxes"),
    ("garden centre", "a", "flower pot", "flower pots", "pallet", "pallets"),
    ("orchard shop", "an", "pear", "pears", "crate", "crates"),
    ("knitting shop", "a", "pair of socks", "pairs of socks", "bag", "bags"),
    ("phone repair shop", "a", "phone charger", "phone chargers", "box", "boxes"),
    ("coffee bar", "a", "muffin", "muffins", "tray", "trays"),
    ("school canteen", "a", "juice carton", "juice cartons", "crate", "crates"),
    ("pharmacy", "a", "first-aid kit", "first-aid kits", "box", "boxes"),
    ("hobby shop", "a", "model kit", "model kits", "carton", "cartons"),
    ("fishmonger's shop", "a", "tin of sardines", "tins of sardines", "case", "cases"),
    ("sports shop", "a", "football", "footballs", "net bag", "net bags"),
    ("pet shop", "a", "bag of bird seed", "bags of bird seed", "sack", "sacks"),
    ("ice-cream parlour", "an", "tub of ice cream", "tubs of ice cream", "freezer box", "freezer boxes"),
    ("fruit stall", "a", "lemon", "lemons", "crate", "crates"),
    ("plant nursery", "a", "tomato seedling", "tomato seedlings", "tray", "trays"),
    ("charity shop", "a", "knitted jumper", "knitted jumpers", "bag", "bags"),
    ("cycle courier depot", "a", "parcel", "parcels", "cage", "cages"),
)
CURRENCIES = ("EUR", "GBP", "USD", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK")
SALE_POTS = ("cash box", "cash tin", "money pouch", "till drawer", "envelope")
MONEY_POTS = ("cash box", "club fund", "travel fund", "repair fund", "savings account", "holiday fund", "tip jar")
FRACTIONS = {(1, 2): "half", (1, 3): "a third", (1, 4): "a quarter", (1, 5): "a fifth", (2, 3): "two thirds",
             (3, 4): "three quarters"}
MUL_VERB = {2: "doubles", 3: "triples", 4: "quadruples"}
MUL_ADV = {2: "twice", 3: "three times", 4: "four times"}
MUL_PASSIVE = {2: "doubled", 3: "tripled"}
PCT_OFF = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 65, 70, 75, 80, 90)
PCT_ON = (5, 10, 12, 15, 20, 25, 30, 40, 50, 60, 75, 100)
HOW = {"down": "down to a whole number", "up": "up to a whole number",
       "half_up": "to the nearest whole number, with halves rounded up"}
ITEM_CAP, MONEY_CAP = 6000, 30000
ITEM_OPS = (("add", 3), ("add_boxes", 1), ("sub", 3), ("mul", 1.5), ("frac_off", 1.5), ("pct_off", 2), ("pct_on", 1),
            ("split", 1.5), ("rate", 2))
MONEY_OPS = (("add", 2), ("sub", 3), ("mul", 1), ("pct_off", 2.5), ("pct_on", 1.5), ("split", 1.5), ("rate", 2))


# ------------------------------------------------------------------------------------------------------------ solver

def days_of(st: dict) -> int:
    """Days of a rate step: the stated number, or an ISO date range with both dates included."""
    if st.get("dates"):
        a, b = (datetime.date.fromisoformat(x) for x in st["dates"])
        return (b - a).days + 1
    return st["d"]


def round_to(x: F, mode: str) -> int:
    if mode == "down":
        return math.floor(x)
    if mode == "up":
        return math.ceil(x)
    if mode == "half_up":
        return math.floor(x + F(1, 2))
    raise ValueError(mode)


def apply(v: F, st: dict, base: F) -> F:
    """One step on the running value ``v``; ``base`` is the value at the start of the current stage (items or money),
    used only by the wrong-base mistake (``_base``)."""
    op = st["op"]
    of = base if st.get("_base") else v
    if op == "add":
        return v + st["k"]
    if op == "add_boxes":
        return v + st["g"] * st["s"]
    if op == "sub":
        return v - st["k"]
    if op == "mul":
        return v * st["f"]
    if op == "frac_off":
        return v - of * F(st["num"], st["den"])
    if op == "pct_off":
        return v - of * F(st["p"], 100)
    if op == "pct_on":
        return v + of * F(st["p"], 100)
    if op == "split":
        return v / st.get("_m", st["m"])
    if op == "rate":
        return v + st["sign"] * st["r"] * (days_of(st) + st.get("_days_off", 0))
    if op == "sale":
        return v * st["price"]
    raise ValueError(op)


def run(start: int, steps: list[dict], mode: str, scope: str) -> int | None:
    """The chain's final whole number, or None if a running value drops to zero or below (an impossible chain)."""
    v = base = F(start)
    for st in steps:
        v = apply(v, st, base)
        if scope == "step":
            v = F(round_to(v, mode))
        if v <= 0:
            return None
        if st["op"] == "sale":
            base = v
    out = round_to(v, mode)
    return out if out > 0 else None


def start_value(case: dict) -> int:
    s = case["start"]
    return s["g"] * s["s"] if "g" in s else s["k"]


def gold_value(case: dict) -> int:
    v = run(start_value(case), case["steps"], case["round"]["mode"], case["round"]["scope"])
    if v is None:
        raise ValueError("impossible chain")
    return v


def solve(case: dict) -> list[int]:
    return [case["options"].index(str(gold_value(case)))]


# -------------------------------------------------------------------------------------------------- named mistakes

def mistakes(case: dict) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """(name, value) of every named mistake that gives a usable whole number: the single mistakes, and the compound ones
    (a single chain mistake made together with a rounding mistake). Gold and duplicates are removed by make_options."""
    start, steps = start_value(case), case["steps"]
    mode, scope = case["round"]["mode"], case["round"]["scope"]
    other_scope = "end" if scope == "step" else "step"
    chains: list[tuple[str, list[dict]]] = []

    def var(i: int, **kw) -> list[dict]:
        s = [dict(x) for x in steps]
        s[i].update(kw)
        return s

    for i in range(len(steps)):
        chains.append((f"step {i + 1} dropped", steps[:i] + steps[i + 1:]))
    for i in range(len(steps) - 1):
        sw = list(steps)
        sw[i], sw[i + 1] = sw[i + 1], sw[i]
        chains.append((f"steps {i + 1} and {i + 2} swapped", sw))
    for i, st in enumerate(steps):
        op = st["op"]
        if op in ("add", "sub"):
            chains.append((f"step {i + 1} direction", var(i, op="sub" if op == "add" else "add")))
        elif op == "add_boxes":
            chains.append((f"step {i + 1} boxes counted instead of items", var(i, op="add", k=st["g"])))
        elif op == "rate":
            chains.append((f"step {i + 1} direction", var(i, sign=-st["sign"])))
            if st.get("dates"):
                chains.append((f"step {i + 1} date range off by one", var(i, _days_off=-1)))
        elif op in ("pct_off", "pct_on"):
            chains.append((f"step {i + 1} direction", var(i, op="pct_on" if op == "pct_off" else "pct_off")))
            chains.append((f"step {i + 1} percentage of the wrong quantity", var(i, _base=True)))
            if op == "pct_off":
                chains.append((f"step {i + 1} kept and removed share swapped", var(i, p=100 - st["p"])))
        elif op == "frac_off":
            chains.append((f"step {i + 1} kept and removed share swapped", var(i, num=st["den"] - st["num"])))
            chains.append((f"step {i + 1} fraction of the wrong quantity", var(i, _base=True)))
        elif op == "split" and st["style"] == "partners":
            chains.append((f"step {i + 1} split without counting the person", var(i, _m=st["m"] - 1)))
        elif op == "split":
            chains.append((f"step {i + 1} split one part too many", var(i, _m=st["m"] + 1)))
    wrong_rounding = [("rounding at the wrong step", mode, other_scope)] + [
        (f"rounding {m2} instead of {mode}", m2, scope) for m2 in sorted(HOW) if m2 != mode]
    single = [(n, run(start, ch, mode, scope)) for n, ch in chains]
    single += [(n, run(start, steps, m2, sc2)) for n, m2, sc2 in wrong_rounding]
    compound = [(f"{n}, {rn}", run(start, ch, m2, sc2)) for n, ch in chains for rn, m2, sc2 in wrong_rounding]
    ok = lambda lst: [(n, v) for n, v in lst if v is not None and 0 < v < 10 ** 7]  # noqa: E731
    return ok(single), ok(compound)


def make_options(rng, gold: int, named: tuple[list[tuple[str, int]], list[tuple[str, int]]], n_opts: int) -> list[str]:
    """Gold first, then the distractors. The gold's rank among the option values is drawn uniformly first (so neither
    the middle nor an extreme value is a cue); each side is filled with named-mistake values from that side (single
    mistakes, sometimes a compound one), then with near values on that side, anchored on the gold or an option already
    chosen there."""
    single, compound = named
    s_vals = sorted({v for _, v in single if v != gold})
    c_vals = sorted({v for _, v in compound if v != gold} - set(s_vals))
    src = {}
    for sd, keep in (("below", lambda v: v < gold), ("above", lambda v: v > gold)):
        a, b = [v for v in s_vals if keep(v)], [v for v in c_vals if keep(v)]
        rng.shuffle(a)
        rng.shuffle(b)
        src[sd] = (a, b)
    n_below = min(rng.randrange(n_opts), gold - 1)
    want = {"below": n_below, "above": n_opts - 1 - n_below}
    n_near = rng.choice((0, 0, 1)) if n_opts <= 4 else rng.choice((1, 2, 3))
    quota = n_opts - 1 - n_near
    side = {"below": [], "above": []}
    order = ["below"] * want["below"] + ["above"] * want["above"]
    rng.shuffle(order)
    for sd in order:
        a, b = src[sd]
        if not quota or len(side[sd]) >= want[sd]:
            continue
        lst = b if b and (not a or rng.random() < 0.3) else a
        if lst:
            side[sd].append(lst.pop())
            quota -= 1
    used = {gold, *side["below"], *side["above"]}
    for sd in ("below", "above"):
        tries = 0
        while len(side[sd]) < want[sd]:
            tries += 1
            if tries > 400:
                raise Retry("no near values")
            a = rng.choice([gold] + side[sd])
            if rng.random() < 0.5:
                d = rng.choice((1, 2, 3, 4, 5, 6, 8, 10))
            else:
                d = max(1, round(a * rng.choice((0.04, 0.08, 0.12, 0.2, 0.3))))
            x = a - d if sd == "below" else a + d
            if (0 < x < gold if sd == "below" else x > gold) and x not in used:
                used.add(x)
                side[sd].append(x)
    vals = [gold] + side["below"] + side["above"]
    return [str(v) for v in vals]


# ------------------------------------------------------------------------------------------------------------- draw

def _wchoice(rng, table):
    names = [n for n, _ in table]
    return rng.choices(names, weights=[w for _, w in table], k=1)[0]


def _dates(rng, n_days: int, cal: tuple[int, int, int] | None) -> list[str] | None:
    """An ISO date range of n_days (both ends included) inside one month; a later range of the same item starts after
    the previous one ends (cal = year, month, first free day), or None if it no longer fits in that month."""
    if cal is None:
        y, m = rng.choice((2026, 2027)), rng.randint(1, 12)
        d1 = rng.randint(1, 28 - n_days)
    else:
        y, m, first = cal
        if first > 28 - n_days:
            return None
        d1 = rng.randint(first, 28 - n_days)
    return [datetime.date(y, m, d1).isoformat(), datetime.date(y, m, d1 + n_days - 1).isoformat()]


def _draw_step(rng, op: str, v: F, stage: str, exact: bool, cal=None) -> dict | None:
    """Parameters for one step on the running value v (None if the op does not fit v)."""
    iv = math.floor(v)
    money = stage == "money"
    if op == "add":
        return {"op": "add", "k": rng.randint(3, max(30, min(400 if money else 250, iv)))}
    if op == "add_boxes":
        return {"op": "add_boxes", "g": rng.randint(2, 12), "s": rng.randint(4, 36)}
    if op == "sub":
        if iv < 8:
            return None
        return {"op": "sub", "k": rng.randint(2, max(2, int(iv * 0.6)))}
    if op == "mul":
        f = rng.choice((2, 3) if money else (2, 2, 3, 4))
        return {"op": "mul", "f": f}
    if op == "frac_off":
        fr = [k for k in FRACTIONS if not exact or v.denominator == 1 and iv % k[1] == 0]
        if not fr or iv < 4:
            return None
        num, den = rng.choice(fr)
        return {"op": "frac_off", "num": num, "den": den}
    if op in ("pct_off", "pct_on"):
        table = PCT_OFF if op == "pct_off" else PCT_ON
        ps = [p for p in table if not exact or v.denominator == 1 and (iv * p) % 100 == 0]
        if not ps or iv < 5:
            return None
        return {"op": op, "p": rng.choice(ps)}
    if op == "split":
        ms = [m for m in range(2, 7) if not exact or v.denominator == 1 and iv % m == 0]
        if not ms or iv < 6:
            return None
        return {"op": "split", "m": rng.choice(ms), "style": rng.choice(("partners", "parts"))}
    if op == "rate":
        sign = rng.choice((1, -1))
        n_days = rng.randint(2, 10)
        dates = _dates(rng, n_days, cal) if rng.random() < 0.5 else None
        hi = (90 if money else 40) if sign > 0 else min(90 if money else 40, (iv - 1) // n_days)
        if hi < 2:
            return None
        st = {"op": "rate", "sign": sign, "r": rng.randint(2, hi), "d": None if dates else n_days, "dates": dates}
        return st
    raise ValueError(op)


def draw(rng, n_opts: int) -> dict:
    kind = rng.choices(("count", "sale", "money"), weights=(0.45, 0.35, 0.2), k=1)[0]
    n_steps = rng.choice((3, 4, 4, 5, 5, 6))
    mode = rng.choice(("down", "up", "half_up"))
    scope = "step" if rng.random() < 0.7 else "end"
    name, other = rng.sample(NAMES, 2)
    case = {"kind": kind, "name": name, "other": other, "setting": list(rng.choice(SETTINGS)),
            "cur": rng.choice(CURRENCIES), "pot": rng.choice(MONEY_POTS if kind == "money" else SALE_POTS),
            "round": {"mode": mode, "scope": scope}}
    if kind == "money":
        case["start"] = {"k": rng.randint(80, 3000)}
    elif rng.random() < 0.35:
        case["start"] = {"g": rng.randint(3, 15), "s": rng.randint(6, 40)}
    else:
        case["start"] = {"k": rng.randint(20, 600)}
    sale_at = rng.randint(1, n_steps - 2) if kind == "sale" else None
    steps: list[dict] = []
    v = F(start_value(case))
    stage = "money" if kind == "money" else "items"
    cal = None
    for i in range(n_steps):
        st = None
        if i == sale_at:
            st = {"op": "sale", "price": rng.randint(2, 25)}
            nv = v * st["price"]
        else:
            for _ in range(30):
                op = _wchoice(rng, MONEY_OPS if stage == "money" else ITEM_OPS)
                cand = _draw_step(rng, op, v, stage, exact=rng.random() < 0.5, cal=cal)
                if cand is None:
                    continue
                nv = apply(v, cand, v)
                if scope == "step":
                    nv = F(round_to(nv, mode))
                if 1 <= nv <= (MONEY_CAP if stage == "money" else ITEM_CAP):
                    st = cand
                    break
            if st is None:
                raise Retry("no usable step")
        if scope == "step":
            nv = F(round_to(nv, mode))
        if not 1 <= nv <= MONEY_CAP:
            raise Retry("value out of range")
        steps.append(st)
        if st.get("dates"):
            end = datetime.date.fromisoformat(st["dates"][1])
            cal = (end.year, end.month, end.day + 1)
        v = nv
        if st["op"] == "sale":
            stage = "money"
    case["steps"] = steps
    case["irrelevant"] = _irrelevant(rng, case)
    gold = gold_value(case)
    if gold < 1:
        raise Retry("no positive answer")
    case["options"] = make_options(rng, gold, mistakes(case), n_opts)
    return case


def _irrelevant(rng, case: dict) -> list[str]:
    n, o, it = case["name"], case["other"], case["setting"][3]
    if case["kind"] == "money":
        pool = (f"{o} keeps {case['cur']} {rng.randint(50, 2000)} in a separate account, which is not part of the {case['pot']}.",
                f"{n} has looked after the {case['pot']} for {rng.randint(2, 15)} years.",
                f"The nearest bank branch is {rng.randint(2, 30)} km away.",
                f"{o} offers advice but adds no money.",
                f"Last year, {n} counted {rng.randint(20, 900)} {it} at a friend's shop; that number plays no part here.")
    else:
        pool = (f"{o}, a friend of {n}, keeps {rng.randint(5, 300)} {it} at home, but none of them are part of this count.",
                f"The {case['setting'][0]} opens at {rng.randint(6, 10)}:00 on weekdays.",
                f"{n} has worked there for {rng.randint(2, 25)} years.",
                f"The storeroom is {rng.randint(3, 12)} metres long and {rng.randint(2, 8)} metres wide.",
                f"Last year, {n} counted {rng.randint(20, 900)} {it} at this time of year; that number plays no part here.",
                f"{o} stops by to say hello and buys nothing.")
    return rng.sample(list(pool), rng.choice((1, 1, 2, 2, 3)))


# ----------------------------------------------------------------------------------------------------------- render

def _cap(s: str) -> str:
    return s[0].upper() + s[1:]


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _step_text(st: dict, stage: str, c: dict, rng) -> str:
    n, cur, pot = c["name"], c["cur"], c["pot"]
    place, art, it1, it, bx1, bx = c["setting"]
    op = st["op"]
    if op == "sale":
        p = st["price"]
        return rng.choice((f"{n} sells all of the {it} for {cur} {p} each and puts the money into an empty {pot}.",
                           f"Every remaining {it1} is sold at {cur} {p} apiece, and the money goes into an empty {pot}.",
                           f"All of the {it} are sold at {cur} {p} per {it1}; the money is put into an empty {pot}.",
                           f"{n} sells the whole stock at {cur} {p} per {it1} and keeps the money in an empty {pot}."))
    if stage == "items":
        if op == "add":
            k = st["k"]
            return rng.choice((f"A supplier delivers {k} more {it}.",
                               f"{n} brings {k} {it} up from the back room and adds them to the stock.",
                               f"A customer returns {k} {it}, and they go back into stock.",
                               f"Another {k} {it} arrive with the morning delivery.",
                               f"{n} collects {k} extra {it} from the wholesaler."))
        if op == "add_boxes":
            g, s = st["g"], st["s"]
            return rng.choice((f"A delivery of {g} {bx} arrives, with {s} {it} in each {bx1}.",
                               f"{n} unpacks {g} more {bx}, each containing {s} {it}.",
                               f"{g} {bx} of {s} {it} each are added to the stock."))
        if op == "sub":
            k = st["k"]
            return rng.choice((f"{n} sells {k} {it} during the morning.",
                               f"{k} of the {it} turn out to be damaged and are thrown away.",
                               f"{n} donates {k} {it} to a local school.",
                               f"A neighbouring business buys {k} of the {it}.",
                               f"{k} {it} are packed for a customer's order and leave the stock."))
        if op == "mul":
            f = st["f"]
            return rng.choice((f"A bulk delivery {MUL_VERB[f]} the number of {it}.",
                               f"After a busy production run, there are {MUL_ADV[f]} as many {it} as before.",
                               f"{n} {MUL_VERB[f]} the stock of {it} with items from another branch."))
        if op == "frac_off":
            fr = FRACTIONS[(st["num"], st["den"])]
            return rng.choice((f"{n} sells {fr} of the {it}.",
                               f"{_cap(fr)} of the {it} are sent to another shop.",
                               f"{n} gives {fr} of the {it} to a charity sale."))
        if op == "pct_off":
            p = st["p"]
            return rng.choice((f"{n} sells {p}% of the {it} at a weekend fair.",
                               f"{p}% of the {it} are damaged by a leaking roof and thrown away.",
                               f"{n} hands out {p}% of the {it} as free samples.",
                               f"The number of {it} falls by {p}% over a busy afternoon."))
        if op == "pct_on":
            p = st["p"]
            return rng.choice((f"A new batch raises the number of {it} by {p}%.",
                               f"The stock of {it} grows by {p}% when the next shipment is unpacked.",
                               f"{n} increases the number of {it} by {p}%."))
        if op == "split":
            m = st["m"]
            if st["style"] == "partners":
                q = m - 1
                return rng.choice((f"{n} and {_plural(q, 'partner', 'partners')} split the {it} equally, and {n} keeps one share.",
                                   f"The {it} are shared equally between {n} and {_plural(q, 'other seller', 'other sellers')}, and {n} keeps one share."))
            return rng.choice((f"{n} divides the {it} equally into {m} {bx} and keeps only one {bx1}.",
                               f"The {it} are split into {m} equal parts, and only one part stays with {n}."))
        if op == "rate":
            r = st["r"]
            if st["sign"] < 0:
                if st["dates"]:
                    d1, d2 = st["dates"]
                    return rng.choice((f"Every day from {d1} to {d2}, both dates included, {n} sells {r} {it}.",
                                       f"From {d1} to {d2}, counting both dates, {r} {it} per day are sold."))
                return f"For {st['d']} days, {n} sells {r} {it} each day."
            if st["dates"]:
                d1, d2 = st["dates"]
                return f"On each day from {d1} to {d2} (both dates included), {n} adds {r} {it} to the stock."
            return f"Over the next {st['d']} days, {r} new {it} arrive each day."
    else:
        if op == "add":
            k = st["k"]
            return rng.choice((f"A sponsor adds {cur} {k} to the {pot}.",
                               f"{n} puts another {cur} {k} into the {pot}.",
                               f"A late payment of {cur} {k} comes in and goes into the {pot}."))
        if op == "sub":
            k = st["k"]
            return rng.choice((f"{n} pays {cur} {k} out of the {pot} for a stall permit.",
                               f"A repair bill of {cur} {k} is paid from the {pot}.",
                               f"{n} takes {cur} {k} out of the {pot} to buy supplies."))
        if op == "mul":
            f = st["f"]
            return rng.choice((f"A matching grant {MUL_VERB[f]} the money in the {pot}.",
                               f"The money in the {pot} is {MUL_PASSIVE[f]} by a generous donor."))
        if op == "pct_off":
            p = st["p"]
            return rng.choice((f"A fee of {p}% of the money in the {pot} is deducted.",
                               f"{n} pays {p}% of the money in the {pot} as commission to the organisers.",
                               f"{p}% of the money in the {pot} goes to tax."))
        if op == "pct_on":
            p = st["p"]
            return rng.choice((f"A bonus raises the money in the {pot} by {p}%.",
                               f"The money in the {pot} grows by {p}% thanks to a grant.",
                               f"A prize adds {p}% to the money in the {pot}."))
        if op == "split":
            m = st["m"]
            if st["style"] == "partners":
                return (f"{n} and {_plural(m - 1, 'partner', 'partners')} split the money in the {pot} equally, "
                        f"and only {n}'s share stays in the {pot}.")
            return f"The money in the {pot} is divided into {m} equal parts, and only one part stays in the {pot}."
        if op == "rate":
            r = st["r"]
            if st["sign"] > 0:
                if st["dates"]:
                    d1, d2 = st["dates"]
                    return f"From {d1} to {d2}, both dates included, {n} earns {cur} {r} a day and puts it into the {pot}."
                return f"{n} earns {cur} {r} per day for {st['d']} days and puts the earnings into the {pot}."
            if st["dates"]:
                d1, d2 = st["dates"]
                return f"Every day from {d1} to {d2} (both dates included), {n} pays {cur} {r} out of the {pot} for parking."
            return f"For {st['d']} days, a fee of {cur} {r} per day is paid from the {pot}."
    raise ValueError(op)


LEADS = ("Solve the word problem below.", "Read the story and work out the final figure.",
         "Work through the steps in the order given.", "Apply the steps of the story in the order they are told.",
         "Answer the question at the end of this short story.")
INTROS = ("{n} runs {a} {p}.", "{n} looks after the stock at {a} {p}.", "{n} works behind the counter of {a} {p}.",
          "{n} keeps the stock records for {a} {p}.", "{n} has just taken over {a} {p}.")
MONEY_INTROS = ("{n} is in charge of the {pot}.", "{n} looks after the {pot}.", "{n} keeps track of the {pot}.")
SEQ = ("Then", "Next,", "After that,", "Later,", "Afterwards,")
STEP_ROUND = ("Rounding rule: after every step, and before the next one, round the running figure {how}.",
              "Whenever a step does not give a whole number, round the result of that step straight away, {how}.",
              "Work in whole numbers: before you continue, the result of each step is rounded {how}.",
              "Round after each step: every intermediate result is rounded {how}.",
              "At each step, the result of that step is rounded {how}.")
END_ROUND = ("Rounding rule: keep exact values, fractions included, through every step and round only the final answer {how}.",
             "Do not round along the way; only the final result is rounded {how}.",
             "Carry exact fractions through all the steps and round once, at the very end, {how}.",
             "Intermediate results stay exact (no rounding); the final answer alone is rounded {how}.",
             "Only the final answer is rounded, {how}; every earlier step keeps its exact value.")
COUNT_Q = ("How many {it} does {n} have at the end?", "After the last step, how many {it} are left?",
           "What is the final number of {it}?", "How many {it} does {n} hold once everything above has happened?",
           "Once all of this is done, how many {it} remain?")
MONEY_Q = ("How much money, in {cur}, is in the {pot} at the end?", "After the last step, how many {cur} are in the {pot}?",
           "What is the final amount in the {pot}, in {cur}?", "How much does the {pot} hold at the end, in {cur}?",
           "Once all of this is done, what amount in {cur} is left in the {pot}?")


def _start_text(c: dict, rng) -> str:
    n, s, cur, pot = c["name"], c["start"], c["cur"], c["pot"]
    place, art, it1, it, bx1, bx = c["setting"]
    if c["kind"] == "money":
        k = s["k"]
        return rng.choice((f"{n} has {cur} {k} in the {pot} at the start.", f"The {pot} holds {cur} {k} at the beginning.",
                           f"At the start, the {pot} contains {cur} {k}."))
    if "g" in s:
        return rng.choice((f"{n} begins with {s['g']} full {bx}, each containing {s['s']} {it}.",
                           f"The first stock count shows {s['g']} {bx} of {s['s']} {it} each."))
    k = s["k"]
    return rng.choice((f"At the start, {n} has {k} {it}.", f"{n} begins with {k} {it} in stock.",
                       f"There are {k} {it} in the storeroom when {n} opens up."))


def _with_seq(sentence: str, word: str, name: str) -> str:
    first = sentence.split(" ", 1)[0]
    if first == name or first[0].isdigit():
        return f"{word} {sentence}"
    return f"{word} {sentence[0].lower()}{sentence[1:]}"


def render(case: dict, rng) -> list[dict]:
    c = case
    n = c["name"]
    place, art, it1, it, bx1, bx = c["setting"]
    stage = "money" if c["kind"] == "money" else "items"
    step_lines = []
    seq_style = rng.choice(("none", "some", "ordered"))
    for i, st in enumerate(c["steps"]):
        s = _step_text(st, stage, c, rng)
        if seq_style == "ordered":
            word = "First," if i == 0 else ("Finally," if i == len(c["steps"]) - 1 else rng.choice(SEQ))
            s = _with_seq(s, word, n)
        elif seq_style == "some" and i > 0 and rng.random() < 0.5:
            s = _with_seq(s, rng.choice(SEQ), n)
        step_lines.append(s)
        if st["op"] == "sale":
            stage = "money"
    body = list(step_lines)
    for irr in c["irrelevant"]:
        body.insert(rng.randint(0, len(body)), irr)
    intro = (rng.choice(MONEY_INTROS).format(n=n, pot=c["pot"]) if c["kind"] == "money"
             else rng.choice(INTROS).format(n=n, a=art, p=place))
    story = [intro, _start_text(c, rng)] + body
    rnd = rng.choice(STEP_ROUND if c["round"]["scope"] == "step" else END_ROUND).format(how=HOW[c["round"]["mode"]])
    qt = rng.choice(MONEY_Q if c["kind"] != "count" else COUNT_Q).format(it=it, n=n, cur=c["cur"], pot=c["pot"])
    layout = rng.randint(0, 4)
    lead = rng.choice(LEADS) + "\n" if rng.random() < 0.35 else ""
    if layout == 0:          # one paragraph, rounding right after the start
        text = " ".join(story[:2] + [rnd] + story[2:] + [qt])
    elif layout == 1:        # one paragraph, rounding just before the question
        text = " ".join(story + [rnd, qt])
    elif layout == 2:        # story, then rounding and question
        text = " ".join(story) + "\n\n" + rnd + " " + qt
    elif layout == 3:        # rounding line first, story, then the question on its own
        text = rnd + "\n" + " ".join(story) + "\n\nQuestion: " + qt
    else:                    # story, rounding on its own line, question
        text = " ".join(story) + "\n" + rnd + "\n\nQuestion: " + qt
    return [{"instructions": lead + text, "options": list(c["options"])}]


# ------------------------------------------------------------------------------------------------- second solver

_D = r"(\d{4}-\d{2}-\d{2})"
_FR = r"(half|a third|a quarter|a fifth|two thirds|three quarters)"
_FRV = {"half": (1, 2), "a third": (1, 3), "a quarter": (1, 4), "a fifth": (1, 5), "two thirds": (2, 3),
        "three quarters": (3, 4)}
_MULV = {"doubles": 2, "triples": 3, "quadruples": 4, "twice": 2, "three times": 3, "four times": 4, "doubled": 2,
         "tripled": 3}


def _ndays(a: str, b: str) -> int:
    ya, ma, da = (int(x) for x in a.split("-"))
    yb, mb, db = (int(x) for x in b.split("-"))
    if (ya, ma) != (yb, mb):
        raise ValueError("date range across months")
    return db - da + 1


# (pattern, kind, function of the match groups -> (operation, value)); the operation is applied to the running value
_TEXT_OPS = [
    # starting values
    (r"At the start, (\w+) has (\d+) (.+)", "start", lambda g: int(g[1])),
    (r"(\w+) begins with (\d+) (.+) in stock", "start", lambda g: int(g[1])),
    (r"(\w+) begins with (\d+) full (.+?), each containing (\d+) (.+)", "start", lambda g: int(g[1]) * int(g[3])),
    (r"There are (\d+) (.+) in the storeroom when (\w+) opens up", "start", lambda g: int(g[0])),
    (r"The first stock count shows (\d+) (.+?) of (\d+) (.+) each", "start", lambda g: int(g[0]) * int(g[2])),
    (r"(\w+) has ([A-Z]{3}) (\d+) in the (.+) at the start", "mstart", lambda g: int(g[2])),
    (r"The (.+) holds ([A-Z]{3}) (\d+) at the beginning", "mstart", lambda g: int(g[2])),
    (r"At the start, the (.+) contains ([A-Z]{3}) (\d+)", "mstart", lambda g: int(g[2])),
    # items
    (r"A supplier delivers (\d+) more (.+)", "plus", lambda g: int(g[0])),
    (r"(\w+) brings (\d+) (.+) up from the back room and adds them to the stock", "plus", lambda g: int(g[1])),
    (r"A customer returns (\d+) (.+), and they go back into stock", "plus", lambda g: int(g[0])),
    (r"Another (\d+) (.+) arrive with the morning delivery", "plus", lambda g: int(g[0])),
    (r"(\w+) collects (\d+) extra (.+) from the wholesaler", "plus", lambda g: int(g[1])),
    (r"A delivery of (\d+) (.+?) arrives, with (\d+) (.+) in each (.+)", "plus", lambda g: int(g[0]) * int(g[2])),
    (r"(\w+) unpacks (\d+) more (.+?), each containing (\d+) (.+)", "plus", lambda g: int(g[1]) * int(g[3])),
    (r"(\d+) (.+?) of (\d+) (.+) each are added to the stock", "plus", lambda g: int(g[0]) * int(g[2])),
    (r"(\w+) sells (\d+) (.+) during the morning", "minus", lambda g: int(g[1])),
    (r"(\d+) of the (.+) turn out to be damaged and are thrown away", "minus", lambda g: int(g[0])),
    (r"(\w+) donates (\d+) (.+) to a local school", "minus", lambda g: int(g[1])),
    (r"A neighbouring business buys (\d+) of the (.+)", "minus", lambda g: int(g[0])),
    (r"(\d+) (.+) are packed for a customer's order and leave the stock", "minus", lambda g: int(g[0])),
    (r"A bulk delivery (doubles|triples|quadruples) the number of (.+)", "times", lambda g: _MULV[g[0].lower()]),
    (r"After a busy production run, there are (twice|three times|four times) as many (.+) as before", "times",
     lambda g: _MULV[g[0].lower()]),
    (r"(\w+) (doubles|triples|quadruples) the stock of (.+) with items from another branch", "times",
     lambda g: _MULV[g[1].lower()]),
    (r"(\w+) sells " + _FR + r" of the (.+)", "keep", lambda g: 1 - F(*_FRV[g[1].lower()])),
    (_FR + r" of the (.+) are sent to another shop", "keep", lambda g: 1 - F(*_FRV[g[0].lower()])),
    (r"(\w+) gives " + _FR + r" of the (.+) to a charity sale", "keep", lambda g: 1 - F(*_FRV[g[1].lower()])),
    (r"(\w+) sells (\d+)% of the (.+) at a weekend fair", "keep", lambda g: 1 - F(int(g[1]), 100)),
    (r"(\d+)% of the (.+) are damaged by a leaking roof and thrown away", "keep", lambda g: 1 - F(int(g[0]), 100)),
    (r"(\w+) hands out (\d+)% of the (.+) as free samples", "keep", lambda g: 1 - F(int(g[1]), 100)),
    (r"The number of (.+) falls by (\d+)% over a busy afternoon", "keep", lambda g: 1 - F(int(g[1]), 100)),
    (r"A new batch raises the number of (.+) by (\d+)%", "keep", lambda g: 1 + F(int(g[1]), 100)),
    (r"The stock of (.+) grows by (\d+)% when the next shipment is unpacked", "keep", lambda g: 1 + F(int(g[1]), 100)),
    (r"(\w+) increases the number of (.+) by (\d+)%", "keep", lambda g: 1 + F(int(g[2]), 100)),
    (r"(\w+) and (\d+) partners? split the (.+) equally, and (\w+) keeps one share", "keep", lambda g: F(1, int(g[1]) + 1)),
    (r"The (.+) are shared equally between (\w+) and (\d+) other sellers?, and (\w+) keeps one share", "keep",
     lambda g: F(1, int(g[2]) + 1)),
    (r"(\w+) divides the (.+) equally into (\d+) (.+) and keeps only one (.+)", "keep", lambda g: F(1, int(g[2]))),
    (r"The (.+) are split into (\d+) equal parts, and only one part stays with (\w+)", "keep", lambda g: F(1, int(g[1]))),
    (r"For (\d+) days, (\w+) sells (\d+) (.+) each day", "minus", lambda g: int(g[0]) * int(g[2])),
    (r"Every day from " + _D + " to " + _D + r", both dates included, (\w+) sells (\d+) (.+)", "minus",
     lambda g: _ndays(g[0], g[1]) * int(g[3])),
    (r"From " + _D + " to " + _D + r", counting both dates, (\d+) (.+) per day are sold", "minus",
     lambda g: _ndays(g[0], g[1]) * int(g[2])),
    (r"Over the next (\d+) days, (\d+) new (.+) arrive each day", "plus", lambda g: int(g[0]) * int(g[1])),
    (r"On each day from " + _D + " to " + _D + r" \(both dates included\), (\w+) adds (\d+) (.+) to the stock", "plus",
     lambda g: _ndays(g[0], g[1]) * int(g[3])),
    # the sale
    (r"(\w+) sells all of the (.+) for ([A-Z]{3}) (\d+) each and puts the money into an empty (.+)", "sale",
     lambda g: int(g[3])),
    (r"Every remaining (.+) is sold at ([A-Z]{3}) (\d+) apiece, and the money goes into an empty (.+)", "sale",
     lambda g: int(g[2])),
    (r"All of the (.+) are sold at ([A-Z]{3}) (\d+) per (.+); the money is put into an empty (.+)", "sale",
     lambda g: int(g[2])),
    (r"(\w+) sells the whole stock at ([A-Z]{3}) (\d+) per (.+) and keeps the money in an empty (.+)", "sale",
     lambda g: int(g[2])),
    # money
    (r"A sponsor adds ([A-Z]{3}) (\d+) to the (.+)", "plus", lambda g: int(g[1])),
    (r"(\w+) puts another ([A-Z]{3}) (\d+) into the (.+)", "plus", lambda g: int(g[2])),
    (r"A late payment of ([A-Z]{3}) (\d+) comes in and goes into the (.+)", "plus", lambda g: int(g[1])),
    (r"(\w+) pays ([A-Z]{3}) (\d+) out of the (.+) for a stall permit", "minus", lambda g: int(g[2])),
    (r"A repair bill of ([A-Z]{3}) (\d+) is paid from the (.+)", "minus", lambda g: int(g[1])),
    (r"(\w+) takes ([A-Z]{3}) (\d+) out of the (.+) to buy supplies", "minus", lambda g: int(g[2])),
    (r"A matching grant (doubles|triples) the money in the (.+)", "times", lambda g: _MULV[g[0].lower()]),
    (r"The money in the (.+) is (doubled|tripled) by a generous donor", "times", lambda g: _MULV[g[1].lower()]),
    (r"A fee of (\d+)% of the money in the (.+) is deducted", "keep", lambda g: 1 - F(int(g[0]), 100)),
    (r"(\w+) pays (\d+)% of the money in the (.+) as commission to the organisers", "keep", lambda g: 1 - F(int(g[1]), 100)),
    (r"(\d+)% of the money in the (.+) goes to tax", "keep", lambda g: 1 - F(int(g[0]), 100)),
    (r"A bonus raises the money in the (.+) by (\d+)%", "keep", lambda g: 1 + F(int(g[1]), 100)),
    (r"The money in the (.+) grows by (\d+)% thanks to a grant", "keep", lambda g: 1 + F(int(g[1]), 100)),
    (r"A prize adds (\d+)% to the money in the (.+)", "keep", lambda g: 1 + F(int(g[0]), 100)),
    (r"(\w+) and (\d+) partners? split the money in the (.+) equally, and only (\w+)'s share stays in the (.+)", "keep",
     lambda g: F(1, int(g[1]) + 1)),
    (r"The money in the (.+) is divided into (\d+) equal parts, and only one part stays in the (.+)", "keep",
     lambda g: F(1, int(g[1]))),
    (r"(\w+) earns ([A-Z]{3}) (\d+) per day for (\d+) days and puts the earnings into the (.+)", "plus",
     lambda g: int(g[2]) * int(g[3])),
    (r"From " + _D + " to " + _D + r", both dates included, (\w+) earns ([A-Z]{3}) (\d+) a day and puts it into the (.+)",
     "plus", lambda g: _ndays(g[0], g[1]) * int(g[4])),
    (r"For (\d+) days, a fee of ([A-Z]{3}) (\d+) per day is paid from the (.+)", "minus", lambda g: int(g[0]) * int(g[2])),
    (r"Every day from " + _D + " to " + _D + r" \(both dates included\), (\w+) pays ([A-Z]{3}) (\d+) out of the (.+) for parking",
     "minus", lambda g: _ndays(g[0], g[1]) * int(g[4])),
]
_TEXT_OPS = [(re.compile("^" + p + "$", re.I), k, fn) for p, k, fn in _TEXT_OPS]

_IGNORE = [re.compile("^" + p + "$", re.I) for p in (
    r"Solve the word problem below", r"Read the story and work out the final figure",
    r"Work through the steps in the order given", r"Apply the steps of the story in the order they are told",
    r"Answer the question at the end of this short story",
    r"(\w+) runs an? (.+)", r"(\w+) looks after the stock at an? (.+)", r"(\w+) works behind the counter of an? (.+)",
    r"(\w+) keeps the stock records for an? (.+)", r"(\w+) has just taken over an? (.+)",
    r"(\w+) is in charge of the (.+)", r"(\w+) looks after the (.+)", r"(\w+) keeps track of the (.+)",
    r"(\w+), a friend of (\w+), keeps (\d+) (.+) at home, but none of them are part of this count",
    r"The (.+) opens at (\d+):00 on weekdays", r"(\w+) has worked there for (\d+) years",
    r"The storeroom is (\d+) metres long and (\d+) metres wide",
    r"Last year, (\w+) counted (\d+) (.+) at (this time of year|a friend's shop); that number plays no part here",
    r"(\w+) stops by to say hello and buys nothing",
    r"(\w+) keeps ([A-Z]{3}) (\d+) in a separate account, which is not part of the (.+)",
    r"(\w+) has looked after the (.+) for (\d+) years", r"The nearest bank branch is (\d+) km away",
    r"(\w+) offers advice but adds no money")]
_SEQ_RE = re.compile(r"^(First,|Finally,|Then|Next,|After that,|Later,|Afterwards,)\s+(.*)$")


def _rnd(x: F, mode: str) -> int:
    n, d = x.numerator, x.denominator
    if mode == "down":
        return n // d
    if mode == "up":
        return -((-n) // d)
    return (2 * n + d) // (2 * d)


def solve_text(q: dict) -> str:
    """Second solver: reads only the rendered text, rebuilds the chain sentence by sentence (every sentence must be
    recognised), applies the stated rounding rule and returns the key of the option with that number."""
    text = q["instructions"]
    if text.startswith("Question: "):
        text = text[len("Question: "):]
    sents = [s.strip() for s in re.split(r"(?<=[.?])\s+|\n+", text) if s.strip()]
    ops, mode, scope, question = [], None, None, None
    for s in sents:
        if s.startswith("Question: "):
            s = s[len("Question: "):]
        if s.endswith("?"):
            if question is not None:
                raise ValueError("two questions")
            question = s
            continue
        s = s.rstrip(".")
        if re.search(r"\bround", s, re.I):
            if scope is not None:
                raise ValueError("two rounding rules")
            if re.search(r"only the final|final answer alone|at the very end", s, re.I):
                scope = "end"
            elif re.search(r"after every step|of that step|of each step|after each step|at each step", s, re.I):
                scope = "step"
            if "to the nearest whole number, with halves rounded up" in s:
                mode = "half_up"
            elif "down to a whole number" in s:
                mode = "down"
            elif "up to a whole number" in s:
                mode = "up"
            if mode is None or scope is None:
                raise ValueError(f"rounding rule not understood: {s}")
            continue
        m = _SEQ_RE.match(s)
        if m:
            s = m.group(2)
        hits = [(k, fn(mt.groups())) for rx, k, fn in _TEXT_OPS for mt in [rx.match(s)] if mt]
        if len(hits) > 1:
            raise ValueError(f"ambiguous sentence: {s}")
        if hits:
            ops.append(hits[0])
            continue
        if not any(rx.match(s) for rx in _IGNORE):
            raise ValueError(f"sentence not understood: {s}")
    if question is None or mode is None or not ops or ops[0][0] not in ("start", "mstart"):
        raise ValueError("incomplete problem")
    if any(k in ("start", "mstart") for k, _ in ops[1:]):
        raise ValueError("two starting values")
    money_q = bool(re.search(r"money|amount|how many [A-Z]{3}\b|hold at the end, in", question))
    if money_q != (ops[0][0] == "mstart" or any(k == "sale" for k, _ in ops)):
        raise ValueError("question does not match the chain")
    v = F(ops[0][1])
    for k, x in ops[1:]:
        if k == "plus":
            v = v + x
        elif k == "minus":
            v = v - x
        elif k in ("times", "keep", "sale"):
            v = v * x
        if scope == "step":
            v = F(_rnd(v, mode))
    ans = str(_rnd(v, mode))
    keys = [key for key, val in q["criteria"].items() if val == ans]
    if len(keys) != 1:
        raise ValueError(f"computed {ans}, not exactly one matching option")
    return keys[0]
