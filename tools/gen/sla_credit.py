"""Service credits: a hosting provider's SLA + one month of downtime for 2-3 services -> the total credit.

Rules: monthly uptime % per service = (minutes in the month - counted downtime) / minutes in the month x 100, not rounded
before the comparison; scheduled maintenance announced at least H hours in advance is not counted; credit tiers by
uptime (below 99.9 %, below 99.0 %, below 95.0 %) as a percent of that service's monthly fee; the total credit is capped
at a percent of the total monthly fees. Exact arithmetic, rounded to cents (halves up). Distractors are the results with
one rule misapplied (tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import calendar
import re
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from tools.gen import _options as O
from tools.gen.base import Retry, money, pick

TASK = "sla_credit"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CHF", "CAD", "SGD")
SERVICES = ("Compute", "Object storage", "Managed database", "Load balancer", "DNS", "Message queue", "CDN", "Backup")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
TITLES = ("SERVICE LEVEL AGREEMENT - CREDITS", "Uptime commitment and service credits", "SLA: how credits are calculated",
          "Service credits for missed uptime", "Availability SLA")
QUESTIONS = ("What is the total service credit for this month?", "How much credit does the customer receive for this month?",
             "What credit is due under the SLA for this month?", "What is the customer's total credit for the month?",
             "What service credit does the customer get?")
D = lambda x: Decimal(str(x))
THRESH = (Fraction(999, 10), Fraction(99), Fraction(95))


def credit(case, *, err=None) -> float:
    days = 30 if err == "thirty_days" else calendar.monthrange(case["year"], case["month"])[1]
    minutes = days * 24 * 60
    total = Decimal(0)
    for s in case["services"]:
        down = sum(m for m, notice in s["outages"] if notice is None or notice < case["notice"] or err == "count_maintenance")
        up = Fraction(minutes - down, minutes) * 100
        pct = 0
        for th, p in zip(THRESH, case["tiers"]):
            if up < th or (err == "boundary" and up <= th):
                pct = p
        if err == "one_tier_up":
            idx = [p for th, p in zip(THRESH, case["tiers"]) if up < th]
            pct = case["tiers"][min(len(idx), 2)] if idx else 0
        total += D(s["fee"]) * pct / 100
    fees = sum(D(s["fee"]) for s in case["services"])
    if err != "no_cap":
        total = min(total, fees * D(case["cap"]) / 100)
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def draw(rng):
    case = {"cur": rng.choice(CURS), "year": 2026, "month": rng.randint(1, 9), "notice": rng.choice([24, 48, 72]),
            "tiers": rng.choice([(10, 25, 50), (5, 15, 30), (10, 30, 100), (10, 20, 40)]), "cap": rng.choice([30, 50, 100])}
    days = calendar.monthrange(2026, case["month"])[1]
    minutes = days * 24 * 60
    services = []
    for name in pick(rng, SERVICES, rng.randint(2, 3)):
        target = rng.choice([99.95, 99.9, 99.5, 99.0, 98.0, 95.0, 93.0])
        budget = int(round(minutes * (100 - target) / 100)) + rng.choice([-1, 0, 0, 1, 25])
        outages, left = [], max(0, budget)
        while left > 0 and len(outages) < 3:
            m = left if len(outages) == 2 else rng.randint(1, left)
            outages.append((m, None))
            left -= m
        if rng.random() < 0.6:
            outages.append((rng.randint(30, 600), case["notice"] + rng.choice([-24, -1, 0, 0, 12, 48])))
        if not outages:
            outages = [(rng.randint(5, 40), None)]
        services.append({"name": name, "fee": f"{rng.randrange(5000, 400000) / 100:.2f}", "outages": outages})
    case["services"] = services
    gold = credit(case)
    errors = [credit(case, err=e) for e in ("thirty_days", "count_maintenance", "boundary", "one_tier_up", "no_cap")]
    errors.append(float(sum(D(s["fee"]) for s in services) * D(case["tiers"][0]) / 100))
    if gold == 0 and all(e == 0 for e in errors):
        raise Retry("no credit anywhere")
    if gold == 0:
        raise Retry("zero credit is not an amount option")
    case["options"] = O.options(rng, gold, errors, 5, lambda v: money(v, case["cur"]))
    return case


def solve(case):
    return [case["options"].index(money(credit(case), case["cur"]))]


def render(case, rng):
    cur = case["cur"]
    t1, t2, t3 = case["tiers"]
    rules = [f"Monthly uptime of a service = (minutes in the calendar month - counted downtime minutes) / minutes in the calendar month x 100; it is not rounded before it is compared with the tiers.",
             f"Scheduled maintenance announced at least {case['notice']} hours in advance is not counted as downtime; all other downtime counts.",
             f"Credit tiers (percent of that service's monthly fee): uptime below 99.9 % -> {t1} %; below 99.0 % -> {t2} %; below 95.0 % -> {t3} % (only the lowest tier reached applies).",
             f"Cap: the total credit for a month is at most {case['cap']} % of the total monthly fees of all services."]
    lines = []
    for s in case["services"]:
        parts = []
        for m, notice in s["outages"]:
            parts.append(f"{m} min unplanned" if notice is None else f"{m} min scheduled maintenance announced {notice} hours ahead")
        lines.append(f"- {s['name']}: monthly fee {money(D(s['fee']), cur)}; downtime: " + ", ".join(parts))
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
            + "\nThe credit is rounded to cents at the end.\n\n"
            + f"Month: {MONTHS[case['month'] - 1]} {case['year']}.\n" + "\n".join(lines) + "\n\n" + rng.choice(QUESTIONS))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer comparisons (1000 x up-minutes vs 999 x minutes) and cents x 100."""
    t = q["instructions"]
    cents = lambda s: int(s.replace(",", "").replace(".", ""))
    cur = re.search(r"([A-Z]{3}) [\d,]+\.\d{2}", t).group(1)
    mname, year = re.search(r"Month: (\w+) (\d{4})\.", t).groups()
    days = calendar.monthrange(int(year), MONTHS.index(mname) + 1)[1]
    mins = days * 1440
    notice = int(re.search(r"announced at least (\d+) hours", t).group(1))
    tiers = [int(x) for x in re.search(r"below 99\.9 % -> (\d+) %; below 99\.0 % -> (\d+) %; below 95\.0 % -> (\d+) %", t).groups()]
    cap = int(re.search(r"at most (\d+) % of the total monthly fees", t).group(1))
    total, fees = 0, 0
    for fee, down in re.findall(r"- .+?: monthly fee [A-Z]{3} ([\d,]+\.\d{2}); downtime: (.+)", t):
        counted = 0
        for part in down.split(", "):
            m = int(part.split(" min")[0])
            a = re.search(r"announced (-?\d+) hours ahead", part)
            if a is None or int(a.group(1)) < notice:
                counted += m
        up_num = mins - counted                                        # uptime % = 100 * up_num / mins
        pct = 0
        if 1000 * up_num < 999 * mins:
            pct = tiers[0]
        if 100 * up_num < 99 * mins:
            pct = tiers[1]
        if 100 * up_num < 95 * mins:
            pct = tiers[2]
        total += cents(fee) * pct                                      # cents x 100
        fees += cents(fee)
    total = min(total, fees * cap)
    c_tot = (total + 50) // 100
    want = f"{cur} {c_tot // 100:,}.{c_tot % 100:02d}"
    return next(k for k, v in q["criteria"].items() if v == want)
