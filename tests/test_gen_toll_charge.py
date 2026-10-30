"""toll_charge: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

from tools.gen import toll_charge as G

def case(**kw):
    c = {"segments": ["10.0", "20.0"], "rates": {"car": "0.100", "van": "0.200", "truck with 2 axles": "0.300", "truck with 3 or more axles": "0.400"},
         "vclass": "car", "wrong_class": "van", "peak": 20, "tag": 10, "has_tag": True, "peaks": [("07:00", "09:30")], "entry": "09:30",
         "flat": "2.50", "minimum": "1.00"}
    c.update(kw)
    return c


def test_window_end_is_exclusive_and_flat_fee_is_not_discounted():
    assert G.toll(case()) == round(30 * 0.1 * 0.9 + 2.5, 2)          # 09:30 is outside the window
    assert G.toll(case(entry="07:00")) == round(30 * 0.1 * 1.2 * 0.9 + 2.5, 2)
    assert G.toll(case(minimum="9.00")) == 9.0


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
