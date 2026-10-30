"""building_permit_fee: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import building_permit_fee as G

def case(**kw):
    c = {"base": {"garage": "200.00"}, "project": "garage", "bands": (100, 100), "rates": ("2.00", "3.00", "5.00"), "area": 250,
         "review": 10, "heritage": "100.00", "in_heritage": True, "exp": 50, "expedited": False, "minimum": "200.00"}
    c.update(kw)
    return c


def test_marginal_bands_review_heritage_expedited_minimum():
    # area fee 100 x 2 + 100 x 3 + 50 x 5 = 750; (200 + 750) x 1.1 = 1045; + 100 heritage = 1145
    assert G.fee(case()) == 1145.0
    assert G.fee(case(expedited=True)) == 1717.5
    assert G.fee(case(area=10, in_heritage=False, minimum="500.00")) == 500.0


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
