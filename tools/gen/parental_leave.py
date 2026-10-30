"""#24 Parental-leave eligibility: a policy with per-item thresholds + 3-6 employees -> yes / no for each employee.

Rules drawn per item: minimum continuous employment (months, inclusive), weekly contract hours (inclusive "at least" or
exclusive "more than", always stated), notice period (days, inclusive), and whether fixed-term contracts qualify (then the
months the contract must still run, inclusive). 1-3 provisions that do not affect eligibility are mixed into the list.
Employee values sit close to each threshold and are drawn independently per employee (no forced mix of answers).
"""

from __future__ import annotations

import re

from tools.gen.base import NAMES, Retry, pick

TASK = "parental_leave"
PART, AREA, GOLD, HALF, COMPONENT = "N", "knowledge", False, "hf", None

IRRELEVANT = (
    "Leave is paid at {pay} % of the regular salary for the first {weeks} weeks.",
    "Requests are submitted through the HR portal, not by e-mail.",
    "The leave may be split into at most {blocks} separate blocks.",
    "HR may ask for a birth or adoption certificate after the leave has started.",
    "Unused leave does not carry over to the next calendar year.",
    "Company car arrangements continue unchanged during the leave.",
    "Employees on leave keep access to the staff canteen.",
)
TITLES = ("PARENTAL LEAVE POLICY", "Parental leave: eligibility rules", "Company policy on parental leave",
          "Who may take parental leave", "Eligibility for parental leave")
CLOSINGS = ("An employee qualifies only if every eligibility condition in this policy is met.",
            "All eligibility conditions must be met at the same time; the other provisions do not affect eligibility.",
            "Missing a single eligibility condition is enough for a request to be refused.",
            "To qualify, an employee must satisfy each eligibility condition listed.",
            "Each eligibility condition must be met; the remaining provisions are for information only.")
HEADERS = ("Requests received:", "Employees who asked for leave:", "Open requests:", "Applications this month:",
           "Leave requests to decide:")
QUESTIONS = ("Question: Does {name} qualify for parental leave under this policy?",
             "Question: Is {name} eligible for parental leave?",
             "Question: Under these rules, may {name} take parental leave?",
             "Question: Should the request of {name} be granted under the eligibility rules?",
             "Question: Does {name} meet every eligibility condition for parental leave?")


def draw(rng):
    case = {"tenure": rng.choice([3, 6, 9, 12, 18, 24]), "hours": rng.choice([10, 15, 16, 20, 24, 30]),
            "hours_inclusive": rng.random() < 0.5, "notice": rng.choice([14, 21, 28, 30, 45, 60]),
            "fixed_ok": rng.random() < 0.5}
    case["fixed_months"] = rng.choice([3, 6, 9]) if case["fixed_ok"] else None
    case["irrelevant"] = [t.format(pay=rng.choice([60, 70, 80, 90, 100]), weeks=rng.choice([4, 6, 8, 12]),
                                   blocks=rng.choice([2, 3, 4]))
                          for t in pick(rng, IRRELEVANT, rng.randint(1, 3))]
    emps = []
    for name in pick(rng, NAMES, rng.randint(3, 6)):
        e = {"name": name, "permanent": rng.random() < 0.72,
             "tenure": max(0, case["tenure"] + rng.choice([-2, 0, 0, 1, 3, 6, 12, 24])),
             "hours": max(1, case["hours"] + rng.choice([-4, 0, 0, 2, 5, 10])),
             "notice": max(0, case["notice"] + rng.choice([-5, 0, 3, 7, 14, 30]))}
        if not e["permanent"]:
            m = case["fixed_months"] or rng.choice([3, 6, 9])
            e["months_left"] = max(1, m + rng.choice([-1, 0, 2, 12]))
        emps.append(e)
    case["employees"] = emps
    if len({e["name"] for e in emps}) != len(emps):
        raise Retry("duplicate names")
    return case


def eligible(case, e) -> bool:
    hours_ok = e["hours"] >= case["hours"] if case["hours_inclusive"] else e["hours"] > case["hours"]
    contract_ok = e["permanent"] or (case["fixed_ok"] and e["months_left"] >= case["fixed_months"])
    return e["tenure"] >= case["tenure"] and hours_ok and e["notice"] >= case["notice"] and contract_ok


def solve(case):
    return [eligible(case, e) for e in case["employees"]]


def _rules(case, rng):
    t, h, n = case["tenure"], case["hours"], case["notice"]
    rules = [rng.choice((f"Eligibility: the employee has been employed for at least {t} months without interruption on the first day of leave.",
                         f"Eligibility: continuous employment of {t} months or more, counted up to the first day of leave, is required.")),
             rng.choice((f"Eligibility: the employment contract is for at least {h} hours per week.",
                         f"Eligibility: contracts of {h} hours per week or more qualify; fewer hours do not."))
             if case["hours_inclusive"] else
             rng.choice((f"Eligibility: the employment contract is for more than {h} hours per week ({h} hours exactly is not enough).",
                         f"Eligibility: only contracts above {h} hours per week qualify; a contract of exactly {h} hours does not.")),
             rng.choice((f"Eligibility: the written request reaches HR at least {n} days before the first day of leave.",
                         f"Eligibility: requests must be submitted {n} days or more before the leave starts."))]
    if case["fixed_ok"]:
        m = case["fixed_months"]
        rules.append(rng.choice((f"Eligibility: a fixed-term contract qualifies only if it still runs for at least {m} months after the first day of leave; permanent contracts always meet this condition.",
                                 f"Eligibility: a fixed-term contract qualifies if it continues for {m} months or more after the leave starts; permanent contracts meet this condition.")))
    else:
        rules.append(rng.choice(("Eligibility: only employees on a permanent contract qualify; fixed-term contracts are excluded.",
                                 "Eligibility: fixed-term contracts never qualify; the employee must hold a permanent contract.")))
    rules += [f"Other provision: {x}" for x in case["irrelevant"]]
    rng.shuffle(rules)
    return rules


def _employee_line(e, rng):
    contract = ("permanent contract" if e["permanent"] else
                f"fixed-term contract that ends {e['months_left']} months after the first day of leave")
    return rng.choice((f"{e['name']}: {contract}, {e['hours']} hours per week, employed for {e['tenure']} months on the first day of leave, request submitted {e['notice']} days before the leave starts.",
                       f"{e['name']} - {contract}; contract hours {e['hours']} per week; continuous employment {e['tenure']} months when the leave starts; request received {e['notice']} days in advance."))


def render(case, rng):
    rules = _rules(case, rng)
    head = rng.choice(TITLES) + "\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n" + rng.choice(CLOSINGS)
    body = rng.choice(HEADERS) + "\n" + "\n".join(_employee_line(e, rng) for e in case["employees"])
    qtpl = rng.choice(QUESTIONS)
    return [{"instructions": f"{head}\n\n{body}\n\n{qtpl.format(name=e['name'])}", "options": None} for e in case["employees"]]


# ------------------------------------------------------------------------------------------------- second solver

def _int(pattern: str, text: str) -> int:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"not found: {pattern}")
    return int(next(g for g in m.groups() if g is not None))


def solve_text(q: dict) -> str:
    """Reads only the rendered question: the thresholds from the rule sentences, then the named employee's line."""
    text = q["instructions"]
    policy, _, rest = text.partition("\n\n")
    body, _, question = rest.rpartition("\n\n")
    rules = [ln for ln in policy.splitlines() if "Eligibility:" in ln]
    joined = " ".join(rules)
    tenure = _int(r"at least (\d+) months without interruption|employment of (\d+) months or more", joined)
    if re.search(r"more than (\d+) hours per week|above (\d+) hours per week", joined):
        hours, inclusive = _int(r"more than (\d+) hours per week|above (\d+) hours per week", joined), False
    else:
        hours, inclusive = _int(r"for at least (\d+) hours per week|contracts of (\d+) hours per week or more", joined), True
    notice = _int(r"at least (\d+) days before|submitted (\d+) days or more", joined)
    fixed = re.search(r"fixed-term contract qualifies (?:only )?if it (?:still runs for at least|continues for) (\d+) months", joined)
    name = re.search(r"(?:Does|Is|may|request of) ([A-Z][a-z]+)", question).group(1)
    line = next(ln for ln in body.splitlines() if ln.startswith(name + ":") or ln.startswith(name + " -"))
    e_hours = _int(r", (\d+) hours per week|contract hours (\d+) per week", line)
    e_tenure = _int(r"employed for (\d+) months|continuous employment (\d+) months", line)
    e_notice = _int(r"submitted (\d+) days before|received (\d+) days in advance", line)
    if "permanent contract" in line:
        contract_ok = True
    else:
        contract_ok = fixed is not None and _int(r"ends (\d+) months after", line) >= int(fixed.group(1))
    hours_ok = e_hours >= hours if inclusive else e_hours > hours
    return "yes" if (e_tenure >= tenure and hours_ok and e_notice >= notice and contract_ok) else "no"
