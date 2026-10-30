"""Warranty claims: a manufacturer's warranty terms + 3-5 claims -> yes / no (is the claim covered) for each claim.

Terms drawn per item: warranty length in months from the purchase date (the warranty covers defects that appear on or
before the same calendar day that many months later), extra months for products registered online, 1-2 excluded causes,
proof required (a receipt, or the online registration), and a filing deadline in days after the defect appeared
(inclusive). Purchase days are 1-28, so "the same calendar day" always exists. Each claim's answer is drawn first (yes
with probability 1/2) and the claim is drawn to match it, close to the limits.
"""

from __future__ import annotations

import datetime as dt
import re

from tools.gen.base import NAMES, Retry, pick

TASK = "warranty_claim"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

PRODUCTS = ("coffee machine", "vacuum cleaner", "washing machine", "laptop", "smartphone", "electric kettle", "hair dryer",
            "microwave oven", "dishwasher", "blender", "e-reader", "printer", "headphones", "electric toothbrush")
CAUSES = ("a motor fault", "a battery fault", "a display fault", "water damage", "drop damage", "an unauthorised repair",
          "a power-supply fault", "a broken hinge", "cosmetic wear")
EXCLUDABLE = ("water damage", "drop damage", "an unauthorised repair", "cosmetic wear")
TITLES = ("LIMITED WARRANTY - CLAIM CONDITIONS", "Warranty terms: when a repair is covered", "Manufacturer's warranty",
          "Warranty conditions for household appliances", "Product warranty: coverage rules")
CLOSINGS = ("A claim is covered only if it meets every condition above.",
            "All conditions must hold for a claim to be covered.",
            "A claim that fails any single condition is not covered.",
            "Cover applies exactly when each condition is met.",
            "Every condition must be satisfied; otherwise the claim is refused.")
HEADERS = ("Claims received:", "Warranty claims to decide:", "Open claims:", "Claims this month:", "Service requests:")
QUESTIONS = ("Question: Is the claim of {name} covered by the warranty?",
             "Question: Does the warranty cover the claim of {name}?",
             "Question: Under these terms, is {name} entitled to a free repair?",
             "Question: Should the claim of {name} be accepted?",
             "Question: Is {name}'s claim covered?")


def add_months(d: dt.date, m: int) -> dt.date:
    y, mo = divmod(d.month - 1 + m, 12)
    return dt.date(d.year + y, mo + 1, d.day)


def covered(case, c) -> bool:
    months = case["months"] + (case["extra"] if c["registered"] else 0)
    end = add_months(c["bought"], months)
    return (c["defect"] <= end and c["cause"] not in case["excluded"] and (c["receipt"] or c["registered"])
            and (c["filed"] - c["defect"]).days <= case["deadline"])


def _claim(rng, case, name, want):
    for _ in range(80):
        bought = dt.date(rng.choice([2023, 2024, 2025]), rng.randint(1, 12), rng.randint(1, 28))
        registered = rng.random() < 0.5
        months = case["months"] + (case["extra"] if registered else 0)
        end = add_months(bought, months)
        defect = end + dt.timedelta(days=rng.choice([-200, -40, -3, -1, 0, 0, 1, 5, 30]))
        if defect <= bought:
            continue
        c = {"name": name, "product": rng.choice(PRODUCTS), "bought": bought, "registered": registered,
             "defect": defect, "filed": defect + dt.timedelta(days=max(0, case["deadline"] + rng.choice([-20, -2, 0, 0, 1, 10]))),
             "cause": rng.choice(CAUSES), "receipt": rng.random() < 0.75}
        if covered(case, c) == want:
            return c
    raise Retry("no claim with the wanted answer")


def draw(rng):
    case = {"months": rng.choice([12, 18, 24, 36]), "extra": rng.choice([6, 12]), "deadline": rng.choice([14, 30, 60, 90]),
            "excluded": pick(rng, EXCLUDABLE, rng.randint(1, 2))}
    case["claims"] = [_claim(rng, case, n, rng.random() < 0.5) for n in pick(rng, NAMES, rng.randint(3, 5))]
    return case


def solve(case):
    return [covered(case, c) for c in case["claims"]]


def _d(d: dt.date) -> str:
    return d.isoformat()


def render(case, rng):
    ex = " and ".join(case["excluded"])
    rules = [rng.choice((f"Term: the warranty covers defects that appear within {case['months']} months of the purchase date, up to and including the same calendar day {case['months']} months later.",
                         f"Term: defects appearing up to and including the same calendar day {case['months']} months after purchase are covered.")),
             f"Term: products registered online get {case['extra']} extra months of cover (added to the {case['months']} months).",
             f"Term: defects caused by {ex} are excluded.",
             rng.choice(("Term: proof of purchase is required: a receipt, or the online registration of the product.",
                         "Term: a claim needs a receipt or an online product registration as proof of purchase.")),
             rng.choice((f"Term: the claim must be filed within {case['deadline']} days after the defect appeared ({case['deadline']} days exactly is still in time).",
                         f"Term: claims are accepted up to and including {case['deadline']} days after the defect first appeared."))]
    rng.shuffle(rules)
    head = rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n" + rng.choice(CLOSINGS)
    lines = []
    for c in case["claims"]:
        reg = "registered online" if c["registered"] else "not registered"
        rec = "receipt provided" if c["receipt"] else "no receipt"
        lines.append(rng.choice((f"{c['name']}: {c['product']} bought on {_d(c['bought'])}, {reg}; defect appeared on {_d(c['defect'])}, caused by {c['cause']}; claim filed on {_d(c['filed'])}; {rec}.",
                                 f"{c['name']} - {c['product']}, purchased {_d(c['bought'])} ({reg}), {rec}; the defect ({c['cause']}) appeared {_d(c['defect'])} and the claim was filed {_d(c['filed'])}.")))
    body = rng.choice(HEADERS) + "\n" + "\n".join(lines)
    qtpl = rng.choice(QUESTIONS)
    return [{"instructions": f"{head}\n\n{body}\n\n{qtpl.format(name=c['name'])}", "options": None} for c in case["claims"]]


# ------------------------------------------------------------------------------------------------- second solver

def solve_text(q: dict) -> str:
    """Reads only the rendered text; compares (year, month, day) tuples for the warranty end."""
    text = q["instructions"]
    policy, _, rest = text.partition("\n\n")
    body, _, question = rest.rpartition("\n\n")
    months = int(re.search(r"same calendar day (\d+) months", policy).group(1))
    extra = int(re.search(r"get (\d+) extra months", policy).group(1))
    excl = re.search(r"defects caused by (.+?) are excluded", policy).group(1).split(" and ")
    deadline = int(next(g for g in re.search(r"within (\d+) days after the defect|including (\d+) days after the defect", policy).groups() if g))
    line = next(ln for ln in body.splitlines()[1:] if re.search(r"\b" + re.split(r":| - ", ln)[0] + r"\b", question))
    dates = re.findall(r"(\d{4})-(\d{2})-(\d{2})", line)
    (by, bm, bd), (dy, dm, dd), (fy, fm, fd) = [tuple(map(int, x)) for x in dates]
    m = months + (extra if "registered online" in line else 0)
    ey, em = divmod(bm - 1 + m, 12)
    end = (by + ey, em + 1, bd)
    cause = re.search(r"caused by (.+?); claim filed|the defect \((.+?)\) appeared", line)
    cause = cause.group(1) or cause.group(2)
    days = (dt.date(fy, fm, fd) - dt.date(dy, dm, dd)).days
    proof = "receipt provided" in line or "registered online" in line
    ok = (dy, dm, dd) <= end and cause not in excl and proof and days <= deadline
    return "yes" if ok else "no"
