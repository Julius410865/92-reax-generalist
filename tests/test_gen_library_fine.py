"""library_fine: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import library_fine as G

import datetime as dt


def case(**kw):
    c = {"rates": {"book": "0.25", "DVD": "1.00"}, "caps": {"book": "5.00", "DVD": "10.00"}, "grace": 2, "fee": "5.00", "lost_days": 0,
         "loans": [{"type": "book", "due": dt.date(2026, 3, 1), "returned": dt.date(2026, 3, 11), "lost": False, "replacement": "12.00"},
                   {"type": "DVD", "due": dt.date(2026, 3, 1), "returned": dt.date(2026, 4, 30), "lost": False, "replacement": "20.00"}]}
    c.update(kw)
    return c


def test_grace_cap_and_lost_items():
    assert G.owed(case()) == 0.25 * 8 + 10.0                    # book 10 days late - 2 free = 8; DVD capped at 10
    lost = case(loans=[{"type": "book", "due": dt.date(2026, 3, 1), "returned": dt.date(2026, 3, 2), "lost": True, "replacement": "12.00"}])
    assert G.owed(lost) == 17.0
    assert G.owed(case(grace=10)) == 10.0


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
