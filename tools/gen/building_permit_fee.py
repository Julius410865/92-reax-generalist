"""Building permit fees: a municipality's fee schedule + one application -> the total permit fee.

Rules: a base fee by project type; a floor-area fee in marginal bands (the first A1 m2 at r1 per m2, the next A2 m2 at
r2, every m2 above A1 + A2 at r3); a plan-review fee as a percent of (base fee + area fee); a flat heritage-zone fee;
an expedited-processing surcharge as a percent of everything before it (only if requested); a minimum total. Exact
decimal arithmetic, rounded to cents (halves up) at the end. Distractors are the results with one rule misapplied
(tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from tools.gen import _options as O
from tools.gen.base import money

TASK = "building_permit_fee"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CAD", "AUD", "NZD", "CHF")
PROJECTS = ("new detached house", "house extension", "garage", "loft conversion", "commercial fit-out", "conservatory")
TITLES = ("BUILDING PERMIT FEE SCHEDULE", "Planning department: permit fees", "How the building permit fee is calculated",
          "Permit fees for construction work", "Municipal building permit charges")
QUESTIONS = ("What is the total permit fee for this application?", "How much does the applicant pay for the permit?",
             "What permit fee is due for this application?", "What does this building permit cost in total?",
             "What is the fee for this permit application?")
D = lambda x: Decimal(str(x))


def area_fee(case, area, *, flat_rate=False) -> Decimal:
    a1, a2 = case["bands"]
    r1, r2, r3 = (D(r) for r in case["rates"])
    if flat_rate:                                   # the whole area at the rate of the band it reaches
        r = r1 if area <= a1 else r2 if area <= a1 + a2 else r3
        return D(area) * r
    first = min(area, a1)
    second = min(max(area - a1, 0), a2)
    third = max(area - a1 - a2, 0)
    return D(first) * r1 + D(second) * r2 + D(third) * r3


def fee(case, *, err=None) -> float:
    base = D(case["base"][case["project"]])
    af = area_fee(case, case["area"], flat_rate=(err == "flat_rate"))
    review_base = base + af + (D(case["heritage"]) if case["in_heritage"] and err == "review_on_all" else 0)
    review = Decimal(0) if err == "no_review" else review_base * D(case["review"]) / 100
    tot = base + af + review + (D(case["heritage"]) if case["in_heritage"] and err != "no_heritage" else 0)
    if case["expedited"]:
        tot = tot + (base + af) * D(case["exp"]) / 100 if err == "exp_on_base" else tot * (1 + D(case["exp"]) / 100)
    if err != "no_minimum":
        tot = max(tot, D(case["minimum"]))
    return float(tot.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def draw(rng):
    case = {"cur": rng.choice(CURS), "base": {p: rng.choice(["150.00", "250.00", "400.00", "600.00", "900.00"]) for p in PROJECTS},
            "bands": (rng.choice([50, 80, 100]), rng.choice([100, 150, 200])),
            "rates": tuple(f"{r:.2f}" for r in sorted((rng.uniform(1.5, 9) for _ in range(3)), reverse=rng.random() < 0.5)),
            "review": rng.choice([10, 15, 20, 25]), "heritage": rng.choice(["75.00", "120.00", "180.00"]), "in_heritage": rng.random() < 0.4,
            "exp": rng.choice([25, 40, 50]), "expedited": rng.random() < 0.4, "project": rng.choice(PROJECTS)}
    case["area"] = rng.choice([rng.randint(15, case["bands"][0]), rng.randint(case["bands"][0] + 1, sum(case["bands"])),
                               rng.randint(sum(case["bands"]) + 1, sum(case["bands"]) + 400)])
    rough = float(D(case["base"][case["project"]]) + area_fee(case, case["area"]))
    case["minimum"] = f"{max(200, round(rough * rng.choice([0.5, 0.8, 1.15, 1.4]) / 10) * 10):.2f}"
    gold = fee(case)
    errors = [fee(case, err=e) for e in ("flat_rate", "review_on_all", "no_review", "no_heritage", "exp_on_base", "no_minimum")]
    case["options"] = O.options(rng, gold, errors, 5, lambda v: money(v, case["cur"]))
    return case


def solve(case):
    return [case["options"].index(money(fee(case), case["cur"]))]


def render(case, rng):
    cur = case["cur"]
    (a1, a2), (r1, r2, r3) = case["bands"], case["rates"]
    rules = ["Base fee by project type: " + "; ".join(f"{p} {money(D(v), cur)}" for p, v in case["base"].items()) + ".",
             f"Floor-area fee: the first {a1} m2 at {money(D(r1), cur)} per m2, the next {a2} m2 at {money(D(r2), cur)} per m2, "
             f"and every m2 above {a1 + a2} m2 at {money(D(r3), cur)} per m2 (each band is charged only for the area inside it).",
             f"Plan review: {case['review']} % of the base fee plus the floor-area fee.",
             f"Heritage zone: a flat {money(D(case['heritage']), cur)} for sites in a heritage zone.",
             f"Expedited processing (on request): {case['exp']} % added to the total of all fees above.",
             f"Minimum: the total permit fee is at least {money(D(case['minimum']), cur)}."]
    site = "inside a heritage zone" if case["in_heritage"] else "outside any heritage zone"
    exp = "expedited processing requested" if case["expedited"] else "standard processing"
    app = f"Application: {case['project']} with {case['area']} m2 of floor area, site {site}, {exp}."
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
            + "\nThe total is rounded to cents at the end.\n\n" + app + "\n\n" + rng.choice(QUESTIONS))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer cents x 10,000 (percent of percent)."""
    t = q["instructions"]
    cents = lambda s: int(s.replace(",", "").replace(".", ""))
    cur = re.search(r"([A-Z]{3}) [\d,]+\.\d{2}", t).group(1)
    app = t.split("\n\nApplication: ")[1]
    project = re.match(r"(.+?) with (\d+) m2", app)
    proj, area = project.group(1), int(project.group(2))
    base = cents(re.search(re.escape(proj) + r" [A-Z]{3} ([\d,]+\.\d{2})", t).group(1))
    m = re.search(r"the first (\d+) m2 at [A-Z]{3} ([\d,]+\.\d{2}) per m2, the next (\d+) m2 at [A-Z]{3} ([\d,]+\.\d{2}) per m2, "
                  r"and every m2 above \d+ m2 at [A-Z]{3} ([\d,]+\.\d{2})", t)
    a1, r1, a2, r2, r3 = int(m.group(1)), cents(m.group(2)), int(m.group(3)), cents(m.group(4)), cents(m.group(5))
    af = min(area, a1) * r1 + min(max(area - a1, 0), a2) * r2 + max(area - a1 - a2, 0) * r3
    review = int(re.search(r"Plan review: (\d+) %", t).group(1))
    tot = (base + af) * (100 + review) * 100                       # cents x 10,000
    if "inside a heritage zone" in app:
        tot += cents(re.search(r"Heritage zone: a flat [A-Z]{3} ([\d,]+\.\d{2})", t).group(1)) * 10000
    if "expedited processing requested" in app:
        tot = tot * (100 + int(re.search(r"\(on request\): (\d+) %", t).group(1)))      # cents x 1e6
    else:
        tot *= 100
    tot = max(tot, cents(re.search(r"is at least [A-Z]{3} ([\d,]+\.\d{2})", t).group(1)) * 10 ** 6)
    c_tot = (tot + 500000) // 10 ** 6
    want = f"{cur} {c_tot // 100:,}.{c_tot % 100:02d}"
    return next(k for k, v in q["criteria"].items() if v == want)
