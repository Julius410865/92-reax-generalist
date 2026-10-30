"""Coupon stacking: a shop's coupon rules + a cart -> the amount the customer pays.

Rules: two percentage coupons for two categories, of which at most one may be used (the one that saves more); a fixed
coupon that needs the subtotal BEFORE any coupon to reach a threshold; a member discount on the amount after the
coupons; a shipping fee waived when the amount after all discounts reaches a threshold. Exact decimal arithmetic, the
total rounded to cents (halves up) at the end. Distractors are the results with one rule misapplied
(tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from tools.gen import _options as O
from tools.gen.base import Retry, money, pick

TASK = "coupon_stacking"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CHF", "CAD", "AUD", "SGD")
GOODS = {"shoes": ("running shoes", "sandals", "hiking boots", "sneakers"), "kitchen": ("frying pan", "knife set", "kettle", "toaster"),
         "books": ("cookbook", "novel", "atlas", "art book"), "toys": ("puzzle", "board game", "toy train", "building set"),
         "garden": ("hose", "planter", "pruning shears", "garden lamp"), "sports": ("yoga mat", "tennis racket", "dumbbells", "football")}
TITLES = ("ONLINE SHOP - COUPON RULES", "How coupons and discounts are combined", "Checkout rules", "Discount policy",
          "Coupons, member discount and shipping")
QUESTIONS = ("What does the customer pay in total?", "What is the final amount charged for this order?",
             "How much does this order cost after all coupons, discounts and shipping?", "What is the order total?",
             "What amount is charged at checkout?")
D = lambda x: Decimal(str(x))
CENT = Decimal("0.01")


def total(case, *, err=None) -> float:
    lines = [(it["cat"], D(it["price"]) * it["qty"]) for it in case["items"]]
    sub = sum(v for _, v in lines)
    saves = []
    for cat, pct in case["pcts"]:
        base = sub if err == "pct_whole_cart" else sum(v for c, v in lines if c == cat)
        saves.append(base * D(pct) / 100)
    if err == "both_pct":
        pct_save = sum(saves)
    elif err == "smaller_pct":
        pct_save = min(saves)
    else:
        pct_save = max(saves)
    after_pct = sub - pct_save
    thr_base = after_pct if err == "fixed_on_discounted" else sub
    fixed = D(case["fixed"]) if thr_base >= D(case["fixed_min"]) else Decimal(0)
    m = D(case["member"]) / 100
    if err == "member_first":
        after = after_pct * (1 - m) - fixed
    elif err == "no_member":
        after = after_pct - fixed
    else:
        after = (after_pct - fixed) * (1 - m)
    after = max(Decimal(0), after)
    ship_base = sub if err == "ship_on_subtotal" else after
    ship = Decimal(0) if (ship_base >= D(case["free_min"]) or err == "no_ship") else D(case["ship"])
    return float((after + ship).quantize(CENT, rounding=ROUND_HALF_UP))


def draw(rng):
    cats = pick(rng, list(GOODS), rng.randint(3, 4))
    items = []
    for c in cats:
        for g in pick(rng, GOODS[c], rng.randint(1, 2)):
            items.append({"cat": c, "what": g, "price": float(D(rng.randrange(399, 15999)) / 100), "qty": rng.choice([1, 1, 1, 2, 3])})
    if len(items) > 5:
        items = items[:5]
    sub = sum(D(i["price"]) * i["qty"] for i in items)
    p1, p2 = pick(rng, sorted({i["cat"] for i in items}), 2) if len({i["cat"] for i in items}) >= 2 else (None, None)
    if p1 is None:
        raise Retry("one category")
    case = {"cur": rng.choice(CURS), "items": items, "pcts": [(p1, rng.choice([10, 15, 20, 25, 30])), (p2, rng.choice([10, 15, 20, 25, 30, 40]))],
            "fixed": rng.choice([5, 10, 15, 20]), "member": rng.choice([3, 5, 10]), "ship": rng.choice([4.95, 5.90, 6.50, 7.99])}
    near = float((sub * D(rng.choice([0.85, 0.95, 1.0, 1.05, 1.2]))).quantize(Decimal(1)))
    case["fixed_min"] = max(20, int(round(near / 10.0)) * 10)
    case["free_min"] = max(30, int(round(float(sub) * rng.choice([0.6, 0.75, 0.9, 1.1]) / 10.0)) * 10)
    gold = total(case)
    errors = [total(case, err=e) for e in ("pct_whole_cart", "both_pct", "smaller_pct", "fixed_on_discounted", "member_first",
                                           "no_member", "ship_on_subtotal", "no_ship")]
    case["options"] = O.options(rng, gold, errors, 5, lambda v: money(v, case["cur"]))
    return case


def solve(case):
    return [case["options"].index(money(total(case), case["cur"]))]


def render(case, rng):
    cur = case["cur"]
    (c1, p1), (c2, p2) = case["pcts"]
    rules = [f"Coupon A: {p1} % off all items in the category '{c1}'.",
             f"Coupon B: {p2} % off all items in the category '{c2}'.",
             "Only one of coupons A and B can be used per order; the one that saves the customer more is applied.",
             f"Coupon C: {money(case['fixed'], cur)} off the order, valid only if the subtotal before any coupon is at least {money(case['fixed_min'], cur)}.",
             f"Member discount: {case['member']} % off the amount left after the coupons.",
             f"Shipping: {money(case['ship'], cur)}, free when the amount after all coupons and discounts is at least {money(case['free_min'], cur)}."]
    order = rng.choice(("Apply the percentage coupon first, then coupon C, then the member discount, then add shipping; round the total to cents at the end.",
                        "Order of calculation: percentage coupon, coupon C, member discount, shipping; the total is rounded to cents only at the end."))
    lines = [f"- {it['qty']} x {it['what']} (category '{it['cat']}') at {money(it['price'], cur)} each" for it in case["items"]]
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n" + order + "\n\nCart:\n"
            + "\n".join(lines) + "\n\n" + rng.choice(QUESTIONS))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

MON = r"[A-Z]{3} ([\d,]+\.\d{2})"


def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer arithmetic in hundredths of a cent."""
    t = q["instructions"]
    cur = re.search(r"([A-Z]{3}) [\d,]+\.\d{2}", t).group(1)
    c = lambda s: int(s.replace(",", "").replace(".", ""))            # cents
    pcts = re.findall(r"Coupon [AB]: (\d+) % off all items in the category '([^']+)'", t)
    fixed = c(re.search(r"Coupon C: " + MON, t).group(1))
    fixed_min = c(re.search(r"subtotal before any coupon is at least " + MON, t).group(1))
    member = int(re.search(r"Member discount: (\d+) %", t).group(1))
    ship = c(re.search(r"Shipping: " + MON, t).group(1))
    free_min = c(re.search(r"discounts is at least " + MON, t).group(1))
    lines = [(int(n), cat, c(p)) for n, cat, p in re.findall(r"- (\d+) x .+? \(category '([^']+)'\) at " + MON + " each", t)]
    sub = sum(n * p for n, _, p in lines) * 100                     # hundredths of a cent from here on
    best = max(sum(n * p for n, cc, p in lines if cc == cat) * int(pct) for pct, cat in pcts)   # = save x 100
    after = sub - best
    if sub >= fixed_min * 100:
        after -= fixed * 100
    after = after * (100 - member)                                   # x 100 again
    after = max(0, after)
    shipping = 0 if after >= free_min * 10000 else ship * 10000
    tot = after + shipping                                           # in 1e-6 currency units
    cents_total = (tot + 5000) // 10000                              # halves up
    want = f"{cur} {cents_total // 100:,}.{cents_total % 100:02d}"
    return next(k for k, v in q["criteria"].items() if v == want)
