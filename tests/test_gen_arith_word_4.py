"""arith_word_4: solver boundaries (DEV-GUIDELINES.md section 7), the options, and the rendered text's second solver."""

from __future__ import annotations

import random

import pytest

from tools.gen import _arith as A
from tools.gen import arith_word_4 as G
from tools.gen.base import Retry, make_row

N_OPTIONS = 4


def case(steps, start=10, mode="down", scope="step", kind="count", gold_at=0):
    c = {"kind": kind, "name": "Nadia", "other": "Bruno", "setting": list(A.SETTINGS[0]), "cur": "EUR",
         "pot": "cash box", "round": {"mode": mode, "scope": scope}, "start": {"k": start}, "steps": steps,
         "irrelevant": []}
    gold = A.gold_value(c)
    others = [str(gold + 100 + i) for i in range(N_OPTIONS - 1)]
    c["options"] = others[:gold_at] + [str(gold)] + others[gold_at:]
    return c


def gold(c):
    return int(c["options"][G.solve(c)[0]])


def split(m, style="parts"):
    return {"op": "split", "m": m, "style": style}


@pytest.mark.parametrize("start,m,mode,want", [
    (5, 2, "down", 2), (5, 2, "up", 3), (5, 2, "half_up", 3),           # exactly a half
    (9, 4, "down", 2), (9, 4, "up", 3), (9, 4, "half_up", 2),           # 2.25
    (11, 4, "down", 2), (11, 4, "up", 3), (11, 4, "half_up", 3),        # 2.75
    (12, 4, "down", 3), (12, 4, "up", 3), (12, 4, "half_up", 3),        # whole: no rounding
])
def test_rounding_direction_at_the_boundaries(start, m, mode, want):
    assert gold(case([split(m)], start=start, mode=mode)) == want


def test_rounding_scope_every_step_versus_final_answer_only():
    steps = [{"op": "frac_off", "num": 1, "den": 2}, {"op": "mul", "f": 2}]
    assert gold(case(steps, start=5, mode="down", scope="step")) == 4     # 2.5 -> 2, then 4
    assert gold(case(steps, start=5, mode="down", scope="end")) == 5      # 2.5 * 2 = 5 exactly
    assert gold(case(steps, start=5, mode="up", scope="step")) == 6       # 2.5 -> 3, then 6
    assert gold(case(steps, start=5, mode="up", scope="end")) == 5


def test_percentages_and_fractions():
    assert gold(case([{"op": "pct_off", "p": 15}], start=200)) == 170
    assert gold(case([{"op": "pct_on", "p": 15}], start=200)) == 230
    assert gold(case([{"op": "pct_on", "p": 100}], start=37)) == 74
    assert gold(case([{"op": "frac_off", "num": 2, "den": 3}], start=30)) == 10
    assert gold(case([{"op": "pct_off", "p": 25}], start=10, mode="half_up")) == 8     # 7.5 -> 8
    assert gold(case([{"op": "pct_off", "p": 25}], start=10, mode="down")) == 7


def test_date_ranges_count_both_dates():
    one_day = {"op": "rate", "sign": -1, "r": 3, "d": None, "dates": ["2026-03-04", "2026-03-04"]}
    week = {"op": "rate", "sign": -1, "r": 3, "d": None, "dates": ["2026-03-04", "2026-03-10"]}
    assert A.days_of(one_day) == 1 and A.days_of(week) == 7
    assert gold(case([week], start=50)) == 50 - 21
    assert gold(case([{"op": "rate", "sign": 1, "r": 4, "d": 6, "dates": None}], start=50)) == 74


def test_partners_split_counts_the_person_too():
    c = case([split(4, "partners")], start=40)
    assert gold(c) == 10
    rng = random.Random(0)
    text = G.render(c, rng)[0]["instructions"]
    assert "3 partners" in text or "3 other sellers" in text


def test_a_running_value_may_reach_one_but_not_zero():
    assert gold(case([{"op": "sub", "k": 9}], start=10)) == 1
    with pytest.raises(ValueError):
        case([{"op": "sub", "k": 10}], start=10)
    assert A.run(10, [{"op": "sub", "k": 11}, {"op": "add", "k": 50}], "down", "step") is None


def test_sale_turns_items_into_money_and_later_steps_work_on_money():
    steps = [{"op": "sub", "k": 4}, {"op": "sale", "price": 7}, {"op": "pct_off", "p": 10}, {"op": "sub", "k": 3}]
    assert gold(case(steps, start=24, kind="sale")) == 123          # 20 items * 7 = 140, -10 % = 126, -3
    named = dict(A.mistakes(case(steps, start=24, kind="sale"))[0])
    assert named["step 3 percentage of the wrong quantity"] == 123  # the base of the money stage is the sale amount
    assert named["step 1 dropped"] == 148


def test_solve_returns_the_gold_index_wherever_it_is():
    for at in range(N_OPTIONS):
        c = case([{"op": "add", "k": 5}], start=10, gold_at=at)
        assert G.solve(c) == [at]


def draws(n=600):
    out = []
    for i in range(n):
        rng = random.Random(f"test|{G.TASK}|{i}")
        try:
            c = G.draw(rng)
        except Retry:
            continue
        out.append((c, make_row(G, "train", i, G.render(c, rng), G.solve(c), rng)))
    return out


def test_second_solver_agrees_and_options_are_well_formed():
    rows = draws()
    assert len(rows) > 550
    ranks = [0] * N_OPTIONS
    for c, row in rows:
        (q,) = row["questions"]
        assert G.solve_text(q) == q["expected"]
        vals = list(q["criteria"].values())
        assert len(vals) == N_OPTIONS == len(set(vals))
        assert all(v.isdigit() and int(v) > 0 for v in vals)
        assert q["criteria"][q["expected"]] == str(A.gold_value(c))
        assert 3 <= len(c["steps"]) <= 6
        assert "round" in q["instructions"].lower() and q["instructions"].endswith("?")
        ranks[sorted(int(v) for v in vals).index(int(q["criteria"][q["expected"]]))] += 1
    assert all(abs(r / len(rows) - 1 / N_OPTIONS) < 0.06 for r in ranks)   # the gold is not the middle value


def test_named_mistakes_never_include_the_gold_and_drawing_is_deterministic():
    for i in range(50):
        a, b = random.Random(f"det|{i}"), random.Random(f"det|{i}")
        try:
            ca = G.draw(a)
        except Retry:
            continue
        cb = G.draw(b)
        assert ca == cb and G.render(ca, a) == G.render(cb, b)
        assert ca["options"][0] == str(A.gold_value(ca)) and ca["options"].count(ca["options"][0]) == 1


def test_second_solver_rejects_text_it_does_not_understand():
    c = case([{"op": "add", "k": 5}], start=10)
    rng = random.Random(1)
    row = make_row(G, "train", 0, G.render(c, rng), G.solve(c), rng)
    q = dict(row["questions"][0])
    q["instructions"] = q["instructions"].replace("?", "? The moon is made of 7 cheeses.", 1) + " Extra?"
    with pytest.raises(ValueError):
        G.solve_text(q)


def test_date_ranges_of_one_item_share_a_month_and_follow_the_story_order():
    seen = 0
    for c, _ in draws(1500):
        ranges = [st["dates"] for st in c["steps"] if st.get("dates")]
        months = {d[0][:7] for d in ranges} | {d[1][:7] for d in ranges}
        assert len(months) <= 1
        for (a1, a2), (b1, b2) in zip(ranges, ranges[1:]):
            assert a1 <= a2 < b1 <= b2
            seen += 1
    assert seen > 0
