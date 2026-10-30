"""insurance_payout: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import insurance_payout as G

def case(**kw):
    c = {"deductible": 200.0, "share": 80, "capped": "jewellery", "cap": 1000.0, "excluded": "clothing", "limit": 1e5,
         "items": [{"cat": "jewellery", "amount": 1500.0}, {"cat": "clothing", "amount": 400.0}, {"cat": "furniture", "amount": 700.0}]}
    c.update(kw)
    return c


def test_cap_exclusion_deductible_share_and_limit():
    assert G.payout(case()) == (1000 + 700 - 200) * 0.8          # 1,200.00
    assert G.payout(case(limit=1000.0)) == 1000.0
    assert G.payout(case(deductible=5000.0)) == 0.0


def test_half_cent_rounds_up():
    assert G.payout(case(items=[{"cat": "furniture", "amount": 200.05}], deductible=0.0, share=90)) == 180.05  # 180.045 -> .05


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
