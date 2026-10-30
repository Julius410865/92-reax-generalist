"""Library fines: a library's fine schedule + one member's 2-4 late or lost loans -> the total the member owes.

Rules: a daily fine per item type for each day after the due date (the day of return counts, the due date does not),
the first G overdue days free (G per item, 0-3), a cap per item type, and a lost item charged its replacement cost plus
a processing fee instead of any fine. Exact decimal arithmetic. Distractors are the results with one rule misapplied
(tools/gen/_options.py places the gold's value rank).
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from tools.gen import _options as O
from tools.gen.base import Retry, money, pick

TASK = "library_fine"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CAD", "AUD", "NZD")
TYPES = {"book": ("0.20", "0.25", "0.30", "0.50"), "DVD": ("0.75", "1.00", "1.50"), "magazine": ("0.10", "0.15", "0.20"),
         "audiobook": ("0.40", "0.50", "0.60"), "board game": ("0.50", "1.00"), "laptop": ("2.00", "3.00", "5.00")}
CAPS = {"book": ("5.00", "8.00", "10.00"), "DVD": ("10.00", "15.00"), "magazine": ("2.00", "3.00"), "audiobook": ("6.00", "8.00"),
        "board game": ("8.00", "12.00"), "laptop": ("40.00", "60.00")}
TITLES = ("LIBRARY FINES AND CHARGES", "Late returns: fine schedule", "Public library - overdue items", "Fines for late or lost items",
          "Borrowing rules: fines")
QUESTIONS = ("How much does {name} owe in total?", "What is the total amount {name} has to pay?",
             "What does {name} owe the library for these loans?", "What is {name}'s total charge?",
             "How much is {name} charged altogether?")
D = lambda x: Decimal(str(x))
art = lambda t: "an" if t[0] in "aeiou" else "a"


def owed(case, *, err=None) -> float:
    tot = Decimal(0)
    grace = 0 if err == "no_grace" else case["grace"]
    for ln in case["loans"]:
        if ln["lost"] and err != "lost_as_late":
            tot += D(ln["replacement"]) + (0 if err == "no_fee" else D(case["fee"]))
            continue
        days = (ln["returned"] - ln["due"]).days + (1 if err == "count_due_day" else 0)
        if ln["lost"]:
            days = case["lost_days"]
        charged = max(0, days - grace)
        fine = D(case["rates"][ln["type"]]) * charged
        if err != "no_cap":
            fine = min(fine, D(case["caps"][ln["type"]]))
        tot += fine
    return float(tot)


def draw(rng):
    types = pick(rng, list(TYPES), rng.randint(2, 4))
    case = {"cur": rng.choice(CURS), "rates": {t: rng.choice(TYPES[t]) for t in types}, "caps": {t: rng.choice(CAPS[t]) for t in types},
            "grace": rng.choice([0, 1, 2, 3]), "fee": rng.choice(["5.00", "7.50", "10.00"]), "lost_days": 0}
    loans = []
    for t in pick(rng, types, rng.randint(2, len(types))):
        due = dt.date(2026, rng.randint(1, 9), rng.randint(1, 28))
        lost = rng.random() < 0.2
        late = rng.choice([1, 2, 3, 4, 6, 9, 14, 21, 35, 60])
        loans.append({"type": t, "title": f"{t} #{rng.randint(100, 999)}", "due": due, "returned": due + dt.timedelta(days=late),
                      "lost": lost, "replacement": f"{rng.randrange(800, 9000) / 100:.2f}" if t != "laptop" else f"{rng.randrange(30000, 90000) / 100:.2f}"})
    case["loans"] = loans
    case["name"] = rng.choice(("Ms Okafor", "Mr Lindqvist", "Ms Ferreira", "Mr Nakamura", "Ms Novak", "Mr Haddad", "Ms Brennan", "Mr Costa"))
    gold = owed(case)
    if gold <= 0:
        raise Retry("nothing owed")
    case["lost_days"] = max(l2["returned"].toordinal() - l2["due"].toordinal() for l2 in loans)    # only for the lost_as_late error
    errors = [owed(case, err=e) for e in ("no_grace", "no_cap", "count_due_day", "no_fee", "lost_as_late")]
    errors.append(float(D(gold) - sum(D(case["rates"][l2["type"]]) for l2 in loans if not l2["lost"])))
    case["options"] = O.options(rng, gold, errors, 5, lambda v: money(v, case["cur"]))
    return case


def solve(case):
    return [case["options"].index(money(owed(case), case["cur"]))]


def render(case, rng):
    cur = case["cur"]
    rules = [f"Daily fine for {art(t)} {t}: {money(D(r), cur)} for each day after the due date (the day of return counts, the due date itself does not)."
             for t, r in case["rates"].items()]
    rules.append(f"Grace period: the first {case['grace']} overdue day(s) of each item are not charged." if case["grace"]
                 else "Grace period: none; every overdue day is charged.")
    rules += [f"Cap: the fine for one {t} is at most {money(D(c), cur)}." for t, c in case["caps"].items()]
    rules.append(f"Lost items: instead of any fine, a lost item is charged its replacement cost plus a processing fee of {money(D(case['fee']), cur)}.")
    lines = []
    for ln in case["loans"]:
        if ln["lost"]:
            lines.append(f"- {ln['title']} ({art(ln['type'])} {ln['type']}): due {ln['due'].isoformat()}, reported lost; replacement cost {money(D(ln['replacement']), cur)}")
        else:
            lines.append(f"- {ln['title']} ({art(ln['type'])} {ln['type']}): due {ln['due'].isoformat()}, returned {ln['returned'].isoformat()}")
    text = (rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n\n"
            + f"Loans of {case['name']}:\n" + "\n".join(lines) + "\n\n" + rng.choice(QUESTIONS).format(name=case["name"]))
    return [{"instructions": text, "options": case["options"]}]


# ------------------------------------------------------------------------------------------------- second solver

MON = r"[A-Z]{3} ([\d,]+\.\d{2})"


def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer cents and ordinal day numbers."""
    t = q["instructions"]
    cur = re.search(r"([A-Z]{3}) [\d,]+\.\d{2}", t).group(1)
    c = lambda s: int(s.replace(",", "").replace(".", ""))
    rate = {k: c(v) for k, v in re.findall(r"Daily fine for an? (.+?): " + MON, t)}
    cap = {k: c(v) for k, v in re.findall(r"the fine for one (.+?) is at most " + MON, t)}
    g = re.search(r"the first (\d+) overdue day", t)
    grace = int(g.group(1)) if g else 0
    fee = c(re.search(r"processing fee of " + MON, t).group(1))
    tot = 0
    for typ, due, rest in re.findall(r"\(an? (.+?)\): due (\d{4}-\d{2}-\d{2}), (.+)", t):
        if rest.startswith("reported lost"):
            tot += c(re.search(MON, rest).group(1)) + fee
        else:
            days = dt.date.fromisoformat(rest.split()[1]).toordinal() - dt.date.fromisoformat(due).toordinal()
            tot += min(cap[typ], rate[typ] * max(0, days - grace))
    want = f"{cur} {tot // 100:,}.{tot % 100:02d}"
    return next(k for k, v in q["criteria"].items() if v == want)
