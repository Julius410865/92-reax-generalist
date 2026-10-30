"""Insurance payout: a contents policy (deductible, co-insurance share, one per-item category cap, one excluded category,
a per-claim limit) + a claim of 2-5 damaged items -> the amount the insurer pays.

    covered  = sum over items not in the excluded category of min(amount, cap) for the capped category, else amount
    payout   = min(limit, (covered - deductible, at least 0) x share), rounded to cents (halves up)

Distractors are the results with one rule missed or misapplied (tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import re

from tools.gen import _options as O
from tools.gen.base import Retry, money, pick, round_half_up

TASK = "insurance_payout"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CHF", "CAD", "AUD", "SGD", "NZD")
CATS = {"electronics": ("laptop", "television", "camera", "games console", "tablet", "speaker system"),
        "jewellery": ("watch", "necklace", "ring", "bracelet", "pair of earrings"),
        "furniture": ("sofa", "dining table", "wardrobe", "office chair", "bookcase"),
        "clothing": ("winter coat", "suit", "pair of boots", "leather jacket"),
        "bicycles": ("road bike", "e-bike", "mountain bike", "cargo bike"),
        "tools": ("drill set", "lawn mower", "circular saw", "pressure washer"),
        "musical instruments": ("guitar", "keyboard", "violin", "drum kit")}
TITLES = ("HOME CONTENTS POLICY - CLAIM SETTLEMENT RULES", "Contents insurance: how a claim is paid",
          "Policy schedule: contents cover", "Claim settlement terms (home contents)", "CONTENTS COVER - PAYOUT RULES")
QUESTIONS = ("What does the insurer pay for this claim?", "How much is paid out on this claim?",
             "What is the settlement amount for this claim?", "Under these terms, what amount does the insurer pay?",
             "What payout does this claim receive?")
HEADERS = ("Claim:", "Damaged items reported:", "Items in this claim:", "Claim details:", "Loss report:")


def payout(case, *, skip=None) -> float:
    """Exact decimal arithmetic (amounts are whole cents), rounded to cents halves up at the end."""
    from decimal import ROUND_HALF_UP, Decimal
    D = lambda x: Decimal(str(x))
    covered = Decimal(0)
    for it in case["items"]:
        if it["cat"] == case["excluded"] and skip != "exclusion":
            continue
        amt = D(it["amount"])
        if it["cat"] == case["capped"] and skip != "cap":
            amt = min(amt, D(case["cap"]))
        covered += amt
    ded = Decimal(0) if skip == "deductible" else D(case["deductible"])
    share = Decimal(1) if skip == "share" else D(case["share"]) / 100
    if skip == "order":                       # share applied before the deductible
        value = max(Decimal(0), covered * share - ded)
    else:
        value = max(Decimal(0), covered - ded) * share
    if skip != "limit":
        value = min(D(case["limit"]), value)
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def draw(rng):
    cur = rng.choice(CURS)
    cats = list(CATS)
    capped, excluded = pick(rng, cats, 2)
    case = {"cur": cur, "deductible": float(rng.choice([100, 150, 200, 250, 300, 500])), "share": rng.choice([70, 75, 80, 85, 90]),
            "capped": capped, "cap": float(rng.choice([500, 750, 1000, 1500, 2000])), "excluded": excluded}
    n = rng.randint(2, 5)
    item_cats = [rng.choice(cats) for _ in range(n)]
    if capped not in item_cats:
        item_cats[rng.randrange(n)] = capped
    if rng.random() < 0.6 and excluded not in item_cats:
        item_cats[rng.randrange(n)] = excluded
    items = []
    for c in item_cats:
        hi = case["cap"] * 2.2 if c == capped else 3000
        items.append({"cat": c, "what": rng.choice(CATS[c]), "amount": round_half_up(rng.uniform(80, hi), 0.01)})
    case["items"] = items
    uncapped = payout(dict(case, limit=1e12))
    case["limit"] = float(rng.choice([round(uncapped * f / 50) * 50 for f in (0.6, 0.8)] if rng.random() < 0.3 else [1e5]))
    case["limit"] = max(case["limit"], 500.0)
    gold = payout(case)
    if gold <= 0:
        raise Retry("nothing paid")
    errors = [payout(case, skip=s) for s in ("exclusion", "cap", "deductible", "share", "order", "limit")]
    errors.append(round_half_up(gold + case["deductible"] * case["share"] / 100))
    fmt = lambda v: money(v, cur)
    case["options"] = O.options(rng, gold, errors, 5, fmt)
    return case


def solve(case):
    return [case["options"].index(money(payout(case), case["cur"]))]


def render(case, rng):
    cur, lim = case["cur"], case["limit"]
    rules = [f"Deductible: the first {money(case['deductible'], cur)} of every claim is borne by the policyholder.",
             f"Co-insurance: after the deductible the insurer pays {case['share']} % of the remaining covered amount.",
             f"Category cap: items in the category '{case['capped']}' are covered up to {money(case['cap'], cur)} each.",
             f"Exclusion: items in the category '{case['excluded']}' are not covered.",
             (f"Claim limit: the insurer pays at most {money(lim, cur)} per claim." if lim < 1e5
              else f"Claim limit: the insurer pays at most {money(lim, cur)} per claim (well above this claim).")]
    order = rng.choice(("Order: apply the exclusion and the category cap to each item, add up, subtract the deductible (never below zero), apply the co-insurance share, then the claim limit; round the result to cents.",
                        "Steps: per item exclusion and cap first, then the total minus the deductible (not below zero), then the co-insurance share, then the claim limit; the payout is rounded to cents."))
    lines = [f"- {it['what'].capitalize()} (category '{it['cat']}'): loss assessed at {money(it['amount'], cur)}" for it in case["items"]]
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n" + order + "\n\n"
            + rng.choice(HEADERS) + "\n" + "\n".join(lines) + "\n\n" + rng.choice(QUESTIONS))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

MONEY = r"([A-Z]{3}) ([\d,]+\.\d{2})"


def _m(s: str) -> float:
    return float(s.replace(",", ""))


def solve_text(q: dict) -> str:
    """Reads only the rendered question and recomputes the payout in integer cents (independent of ``payout``)."""
    from decimal import ROUND_HALF_UP, Decimal
    t = q["instructions"]
    cents = lambda s: int(round(_m(s) * 100))
    cur = re.search(MONEY, t).group(1)
    ded = cents(re.search(r"the first " + MONEY, t).group(2))
    share = Decimal(re.search(r"insurer pays (\d+) % of", t).group(1)) / 100
    capped = re.search(r"items in the category '([^']+)' are covered up to", t).group(1)
    cap = cents(re.search(r"are covered up to " + MONEY, t).group(2))
    excluded = re.search(r"items in the category '([^']+)' are not covered", t).group(1)
    limit = cents(re.search(r"at most " + MONEY + " per claim", t).group(2))
    covered = 0
    for cat, amt in re.findall(r"\(category '([^']+)'\): loss assessed at [A-Z]{3} ([\d,]+\.\d{2})", t):
        if cat != excluded:
            covered += min(cents(amt), cap) if cat == capped else cents(amt)
    pay = min(Decimal(limit), (Decimal(max(0, covered - ded)) * share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    want = f"{cur} {pay / 100:,.2f}"
    return next(k for k, v in q["criteria"].items() if v == want)
