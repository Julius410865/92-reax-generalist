"""sla_credit: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import sla_credit as G

def case(**kw):
    c = {"year": 2026, "month": 4, "notice": 48, "tiers": (10, 25, 50), "cap": 100,
         "services": [{"fee": "100.00", "outages": [(43, None)]}, {"fee": "200.00", "outages": [(500, 48), (10, None)]}]}
    c.update(kw)
    return c


def test_tiers_are_strict_and_announced_maintenance_is_free():
    # April: 43,200 min. 43 min down -> 99.9005 % (no credit); 43.2 would be exactly 99.9 % -> no credit either
    assert G.credit(case()) == 0.0
    assert G.credit(case(services=[{"fee": "100.00", "outages": [(44, None)]}])) == 10.0
    assert G.credit(case(services=[{"fee": "100.00", "outages": [(500, 47)]}])) == 25.0        # announced too late: 98.84 %


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
