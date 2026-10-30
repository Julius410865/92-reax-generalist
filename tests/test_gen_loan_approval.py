"""loan_approval: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import loan_approval as G

def case(**kw):
    c = {"score": 650, "dti": 40, "months": 12, "multiple": 2}
    c.update(kw)
    return c


def app(**kw):
    e = {"name": "Elif", "score": 650, "months": 12, "income": 60000, "debt": 1500, "payment": 500, "loan": 120000}
    e.update(kw)
    return e


def test_every_limit_is_inclusive():
    assert G.approved(case(), app())                       # ratio = 2000 / 5000 = exactly 40 %
    assert not G.approved(case(), app(debt=1501))
    assert not G.approved(case(), app(score=649))
    assert not G.approved(case(), app(months=11))
    assert not G.approved(case(), app(loan=120001))


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
