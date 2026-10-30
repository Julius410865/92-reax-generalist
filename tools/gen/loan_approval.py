"""Loan approval: a lender's criteria + 3-5 applicants -> yes / no for each applicant.

Criteria drawn per item: minimum credit score (inclusive), maximum debt-to-income ratio in % (existing monthly debt
payments plus the new loan's monthly payment, divided by gross monthly income = annual income / 12; a ratio exactly at
the limit is allowed), minimum months in the current job (inclusive), maximum loan = a multiple of annual income
(inclusive). One or two provisions that do not affect the decision are mixed in. Each applicant's answer is drawn first
(yes with probability 1/2) and the values are drawn to match it, close to the limits.
"""

from __future__ import annotations

import re
from fractions import Fraction

from tools.gen.base import NAMES, Retry, pick

TASK = "loan_approval"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

CURS = ("EUR", "USD", "GBP", "CHF", "CAD", "AUD")
IRRELEVANT = ("Applications are processed within {d} business days.", "A valuation fee is charged only after approval.",
              "Applicants may add a co-borrower in a separate application.", "Approval letters are valid for {m} months.",
              "Early repayment is allowed without penalty after {y} years.")
TITLES = ("PERSONAL LOAN - APPROVAL CRITERIA", "Lending policy: when a loan is approved", "Credit policy for personal loans",
          "Loan approval rules", "Underwriting criteria (personal loans)")
CLOSINGS = ("An application is approved only if it meets every criterion above.",
            "All criteria must be met at the same time; the other provisions do not affect approval.",
            "Failing a single criterion is enough for an application to be declined.",
            "Approve an application exactly when it satisfies each criterion.",
            "Each criterion must be met; the remaining provisions are for information only.")
HEADERS = ("Applications:", "Applicants this week:", "Open applications:", "Applications to decide:", "Loan requests:")
QUESTIONS = ("Question: Is the application of {name} approved under these criteria?",
             "Question: Does {name} qualify for the loan?",
             "Question: Under this policy, should the loan for {name} be approved?",
             "Question: Is {name} approved?",
             "Question: Does the application of {name} meet every criterion?")


def ratio(e) -> Fraction:
    """Debt-to-income in percent, exact."""
    return Fraction(e["debt"] + e["payment"]) * 100 / (Fraction(e["income"]) / 12)


def approved(case, e) -> bool:
    return (e["score"] >= case["score"] and ratio(e) <= case["dti"] and e["months"] >= case["months"]
            and e["loan"] <= case["multiple"] * e["income"])


def _applicant(rng, case, name, want: bool):
    for _ in range(60):
        income = rng.randrange(24, 160) * 1000
        e = {"name": name, "income": income,
             "score": case["score"] + rng.choice([-40, -10, -1, 0, 0, 5, 20, 60]),
             "months": max(0, case["months"] + rng.choice([-6, -1, 0, 0, 2, 12, 36])),
             "loan": rng.randrange(2, 60) * 1000}
        e["payment"] = max(50, round(e["loan"] / rng.choice([36, 48, 60, 72])))
        # existing debt chosen so that the ratio lands near the limit on either side
        target = Fraction(case["dti"] + rng.choice([-8, -3, -1, 0, 0, 1, 4]), 100) * Fraction(income, 12)
        e["debt"] = max(0, int(target) - e["payment"])
        if want:
            e["score"] = max(e["score"], case["score"])
            e["months"] = max(e["months"], case["months"])
            e["loan"] = min(e["loan"], case["multiple"] * income // 1000 * 1000)
            while ratio(e) > case["dti"] and e["debt"] > 0:
                e["debt"] = max(0, e["debt"] - 25)
        if approved(case, e) == want:
            return e
    raise Retry("no applicant with the wanted answer")


def draw(rng):
    case = {"cur": rng.choice(CURS), "score": rng.choice([580, 620, 650, 680, 700, 720]),
            "dti": rng.choice([35, 36, 40, 43, 45, 50]), "months": rng.choice([6, 12, 18, 24]),
            "multiple": rng.choice([1, 2, 3])}
    case["irrelevant"] = [t.format(d=rng.choice([3, 5, 10]), m=rng.choice([2, 3, 6]), y=rng.choice([1, 2, 3]))
                          for t in pick(rng, IRRELEVANT, rng.randint(1, 2))]
    case["applicants"] = [_applicant(rng, case, n, rng.random() < 0.5) for n in pick(rng, NAMES, rng.randint(3, 5))]
    return case


def solve(case):
    return [approved(case, e) for e in case["applicants"]]


def _fmt(x, cur):
    return f"{cur} {x:,}"


def render(case, rng):
    cur = case["cur"]
    rules = [rng.choice((f"Criterion: a credit score of at least {case['score']}.",
                         f"Criterion: the credit score is {case['score']} or higher.")),
             rng.choice((f"Criterion: the debt-to-income ratio is at most {case['dti']} %: existing monthly debt payments plus the new loan's monthly payment, divided by the gross monthly income (annual income / 12); a ratio exactly at {case['dti']} % is allowed.",
                         f"Criterion: (existing monthly debt payments + the new monthly loan payment) / (gross annual income / 12) must not exceed {case['dti']} %; exactly {case['dti']} % is allowed.")),
             rng.choice((f"Criterion: at least {case['months']} months in the current job.",
                         f"Criterion: the applicant has been in the current job for {case['months']} months or more.")),
             rng.choice((f"Criterion: the loan amount is at most {case['multiple']} times the gross annual income.",
                         f"Criterion: the requested amount does not exceed {case['multiple']} x the gross annual income."))]
    rules += [f"Other provision: {x}" for x in case["irrelevant"]]
    rng.shuffle(rules)
    head = rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n" + rng.choice(CLOSINGS)
    lines = [rng.choice((f"{e['name']}: credit score {e['score']}; gross annual income {_fmt(e['income'], cur)}; existing debt payments {_fmt(e['debt'], cur)} per month; loan requested {_fmt(e['loan'], cur)} with a monthly payment of {_fmt(e['payment'], cur)}; {e['months']} months in the current job.",
                         f"{e['name']} - score {e['score']}, income {_fmt(e['income'], cur)} per year, current debt payments {_fmt(e['debt'], cur)} a month, asks for {_fmt(e['loan'], cur)} (monthly payment {_fmt(e['payment'], cur)}), {e['months']} months in the job."))
             for e in case["applicants"]]
    body = rng.choice(HEADERS) + "\n" + "\n".join(lines)
    qtpl = rng.choice(QUESTIONS)
    return [{"instructions": f"{head}\n\n{body}\n\n{qtpl.format(name=e['name'])}", "options": None} for e in case["applicants"]]


# ------------------------------------------------------------------------------------------------- second solver

def _int(pattern: str, text: str) -> int:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"not found: {pattern}")
    return int(next(g for g in m.groups() if g is not None).replace(",", ""))


def solve_text(q: dict) -> str:
    """Reads only the rendered text; integer arithmetic: 100 x 12 x (debt + payment) <= limit x income."""
    text = q["instructions"]
    policy, _, rest = text.partition("\n\n")
    body, _, question = rest.rpartition("\n\n")
    score = _int(r"credit score of at least (\d+)|credit score is (\d+) or higher", policy)
    dti = _int(r"ratio is at most (\d+) %|must not exceed (\d+) %", policy)
    months = _int(r"at least (\d+) months in the current job|current job for (\d+) months or more", policy)
    mult = _int(r"at most (\d+) times the gross|exceed (\d+) x the gross", policy)
    name = re.search(r"(?:of|Does|for|Is) ([A-Z][a-z]+)(?: | approved| qualify| meet)", question).group(1)
    line = next(ln for ln in body.splitlines() if ln.startswith(name + ":") or ln.startswith(name + " -"))
    n = r"([\d,]+)"
    e_score = _int(r"credit score (\d+);|score (\d+),", line)
    income = _int(r"annual income [A-Z]{3} " + n + "|income [A-Z]{3} " + n + " per year", line)
    debt = _int(r"debt payments [A-Z]{3} " + n + " per month|debt payments [A-Z]{3} " + n + " a month", line)
    loan = _int(r"loan requested [A-Z]{3} " + n + "|asks for [A-Z]{3} " + n, line)
    pay = _int(r"monthly payment of [A-Z]{3} " + n + "|monthly payment [A-Z]{3} " + n, line)
    e_months = _int(r"(\d+) months in the", line)
    ok = e_score >= score and 100 * 12 * (debt + pay) <= dti * income and e_months >= months and loan <= mult * income
    return "yes" if ok else "no"
