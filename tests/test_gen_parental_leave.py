"""#24 parental_leave: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

import random

from tools.gen import parental_leave as G
from tools.gen.base import make_row


def case(**kw):
    c = {"tenure": 12, "hours": 20, "hours_inclusive": True, "notice": 30, "fixed_ok": True, "fixed_months": 6, "irrelevant": []}
    c.update(kw)
    return c


def emp(**kw):
    e = {"name": "Elif", "permanent": True, "tenure": 12, "hours": 20, "notice": 30}
    e.update(kw)
    return e


def test_every_limit_is_inclusive_exactly_at_the_threshold():
    assert G.eligible(case(), emp())
    assert not G.eligible(case(), emp(tenure=11))
    assert not G.eligible(case(), emp(notice=29))
    assert not G.eligible(case(), emp(hours=19))


def test_exclusive_hours_reject_exactly_the_threshold():
    assert not G.eligible(case(hours_inclusive=False), emp(hours=20))
    assert G.eligible(case(hours_inclusive=False), emp(hours=21))


def test_fixed_term_contracts():
    assert G.eligible(case(), emp(permanent=False, months_left=6))
    assert not G.eligible(case(), emp(permanent=False, months_left=5))
    assert not G.eligible(case(fixed_ok=False, fixed_months=None), emp(permanent=False, months_left=24))


def test_second_solver_agrees_and_yes_share_is_balanced():
    yes = total = 0
    for i in range(400):
        rng = random.Random(f"t|{i}")
        try:
            c = G.draw(rng)
        except Exception:
            continue
        answers = G.solve(c)
        row = make_row(G, "train", i, G.render(c, rng), answers, rng)
        for q, a in zip(row["questions"], answers):
            assert G.solve_text(q) == ("yes" if a else "no")
            yes += a
            total += 1
    assert 0.40 <= yes / total <= 0.60
