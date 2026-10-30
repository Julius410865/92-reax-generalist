"""warranty_claim: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import warranty_claim as G

import datetime as dt


def case(**kw):
    c = {"months": 12, "extra": 6, "deadline": 30, "excluded": ["water damage"]}
    c.update(kw)
    return c


def claim(**kw):
    e = {"bought": dt.date(2025, 3, 15), "registered": False, "defect": dt.date(2026, 3, 15), "filed": dt.date(2026, 4, 14),
         "cause": "a motor fault", "receipt": True}
    e.update(kw)
    return e


def test_end_day_and_deadline_are_inclusive():
    assert G.covered(case(), claim())
    assert not G.covered(case(), claim(defect=dt.date(2026, 3, 16), filed=dt.date(2026, 3, 20)))
    assert not G.covered(case(), claim(filed=dt.date(2026, 4, 15)))


def test_registration_extends_cover_and_counts_as_proof():
    assert G.covered(case(), claim(registered=True, receipt=False, defect=dt.date(2026, 9, 15), filed=dt.date(2026, 9, 20)))
    assert not G.covered(case(), claim(receipt=False))
    assert not G.covered(case(), claim(cause="water damage"))


def test_second_solver_agrees_and_answers_are_balanced():
    import random, re, statistics
    from tools.gen.base import Retry, make_row
    ranks, yes, total, near_mean, mc = [0] * 6, 0, 0, 0, 0
    for i in range(400):
        rng = random.Random(f"t|{i}")
        try:
            c = G.draw(rng)
        except Retry:
            continue
        answers = G.solve(c)
        row = make_row(G, "train", i, G.render(c, rng), answers, rng)
        for q in row["questions"]:
            assert G.solve_text(q) == q["expected"]
            total += 1
            if set(q["criteria"]) == {"yes", "no"}:
                yes += q["expected"] == "yes"
            else:
                v = {k: float(re.findall(r"[\d,]+\.\d+", s)[-1].replace(",", "")) for k, s in q["criteria"].items()}
                ranks[sorted(v, key=v.get).index(q["expected"]) + 1] += 1
                m = statistics.mean(v.values())
                near_mean += min(v, key=lambda k: abs(v[k] - m)) == q["expected"]
                mc += 1
    assert total > 300
    if mc:   # the gold's value rank spread like the eval's (18/36/32/9/5 %), no "closest to the mean" shortcut
        assert 0.10 <= ranks[1] / mc <= 0.26 and 0.27 <= ranks[2] / mc <= 0.45 and 0.23 <= ranks[3] / mc <= 0.41
        assert near_mean / mc <= 0.40
    else:
        assert 0.40 <= yes / total <= 0.60
