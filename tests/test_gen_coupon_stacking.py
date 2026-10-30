"""coupon_stacking: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import coupon_stacking as G

def case(**kw):
    c = {"items": [{"cat": "shoes", "price": 100.0, "qty": 1}, {"cat": "books", "price": 50.0, "qty": 2}],
         "pcts": [("shoes", 20), ("books", 30)], "fixed": 10, "fixed_min": 200, "member": 10, "ship": 5.0, "free_min": 150}
    c.update(kw)
    return c


def test_better_coupon_threshold_on_subtotal_member_then_shipping():
    # subtotal 200; shoes 20 % saves 20, books 30 % saves 30 -> books; 170 - 10 (subtotal 200 >= 200) = 160; x 0.9 = 144; < 150 -> + 5
    assert G.total(case()) == 149.0
    assert G.total(case(fixed_min=201)) == 153.0               # no coupon C: 170 x 0.9 = 153 >= 150, free shipping


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
