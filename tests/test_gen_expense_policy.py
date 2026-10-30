"""#22 expense_policy: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

import collections
import random

from tools.gen import expense_policy as G
from tools.gen.base import Retry, make_row

SUB = "2026-10-01"


def case(cats=None, **gen):
    g = {"receipt": None, "approval": None, "deadline": None, "unlisted": None}
    g.update(gen)
    return {"cur": "EUR", "company": "Saffron Labs", "cats": cats or {}, "general": g, "people": False,
            "submitter": "Rosa", "submitted": SUB, "irrelevant": [], "claims": []}


def line(cat, **kw):
    c = {"cat": cat, "amount": 1000, "date": "2026-09-20", "receipt": True, "approved": False}
    c.update(kw)
    return c


def ok(c, ln):
    return G.line_ok(c, ln)


MEAL_IN = {"meal": {"cap": 4500, "incl": True, "alcohol": "never"}}
MEAL_EX = {"meal": {"cap": 4500, "incl": False, "alcohol": "client"}}


def test_meal_cap_per_person_inclusive_and_exclusive():
    m = dict(persons=2, alcohol=False, client=False)
    assert ok(case(MEAL_IN), line("meal", amount=9000, **m))           # 45.00 per person, inclusive
    assert not ok(case(MEAL_IN), line("meal", amount=9002, **m))
    assert not ok(case(MEAL_EX), line("meal", amount=9000, **m))       # 45.00 itself is too much
    assert ok(case(MEAL_EX), line("meal", amount=8998, **m))


def test_alcohol_rules():
    assert not ok(case(MEAL_IN), line("meal", amount=3000, persons=1, alcohol=True, client=True))
    assert ok(case(MEAL_EX), line("meal", amount=3000, persons=1, alcohol=True, client=True))
    assert not ok(case(MEAL_EX), line("meal", amount=3000, persons=1, alcohol=True, client=False))


def test_receipt_and_approval_thresholds():
    r_in = case(MEAL_IN, receipt={"amount": 2500, "incl": True})
    r_ex = case(MEAL_IN, receipt={"amount": 2500, "incl": False})
    m = dict(persons=1, alcohol=False, client=False, receipt=False)
    assert not ok(r_in, line("meal", amount=2500, **m))                # 25.00 or more needs a receipt
    assert ok(r_ex, line("meal", amount=2500, **m))                    # only above 25.00
    assert not ok(r_ex, line("meal", amount=2501, **m))
    a_in = case({"phone": {"cap": 90000}}, approval={"amount": 50000, "incl": True})
    a_ex = case({"phone": {"cap": 90000}}, approval={"amount": 50000, "incl": False})
    assert not ok(a_in, line("phone", amount=50000, month="July"))
    assert ok(a_ex, line("phone", amount=50000, month="July"))
    assert ok(a_in, line("phone", amount=50000, month="July", approved=True))


def test_mileage_needs_no_receipt_only_when_the_policy_says_so():
    car = {"mileage": {"rate": 30, "max_km": 300, "incl": True}}
    r = {"amount": 1000, "incl": True}
    assert ok(case(car, receipt=r), line("mileage", km=100, amount=3000, receipt=False))
    # private car not named: an unnamed type under the general rules -> the receipt rule applies
    assert not ok(case(MEAL_IN, receipt=r, unlisted="general"), line("mileage", km=100, amount=3000, receipt=False))


def test_mileage_km_limit_and_amount():
    inc = case({"mileage": {"rate": 32, "max_km": 300, "incl": True}})
    exc = case({"mileage": {"rate": 32, "max_km": 300, "incl": False}})
    assert ok(inc, line("mileage", km=300, amount=9600))
    assert not ok(exc, line("mileage", km=300, amount=9600))
    assert ok(exc, line("mileage", km=299, amount=9568))
    assert not ok(inc, line("mileage", km=250, amount=8001))           # 250 x 0.32 = 80.00
    assert ok(inc, line("mileage", km=250, amount=7900))


def test_deadline_day_n_is_in_time():
    c = case(MEAL_IN, deadline={"days": 30})
    m = dict(persons=1, alcohol=False, client=False)
    assert ok(c, line("meal", date="2026-09-01", **m))                 # day 30
    assert not ok(c, line("meal", date="2026-08-31", **m))             # day 31
    p = line("meal", date="2026-08-31", submitted="2026-09-30", **m)   # own submission date (people style)
    assert ok(c, p)


def test_hotel_city_caps():
    h = {"hotel": {"cap": 12000, "incl": True, "high": {"cities": ["Geneva", "Tokyo"], "cap": 18000}}}
    assert ok(case(h), line("hotel", city="Geneva", nights=2, rate=18000, amount=36000))
    assert not ok(case(h), line("hotel", city="Lyon", nights=2, rate=15000, amount=30000))
    assert ok(case(h), line("hotel", city="Lyon", nights=1, rate=12000, amount=12000))
    h["hotel"]["incl"] = False
    assert not ok(case(h), line("hotel", city="Lyon", nights=1, rate=12000, amount=12000))


def test_taxi_time_window_and_airport():
    t = {"taxi": {"cap": 5000, "incl": True, "window": {"start": 22, "end": 6, "airport": True}}}
    assert ok(case(t), line("taxi", time=22 * 60, airport=False))      # 22:00 is in the window
    assert ok(case(t), line("taxi", time=5 * 60 + 59, airport=False))
    assert not ok(case(t), line("taxi", time=6 * 60, airport=False))   # 06:00 is not "before 06:00"
    assert ok(case(t), line("taxi", time=12 * 60, airport=True))
    t["taxi"]["window"]["airport"] = False
    assert not ok(case(t), line("taxi", time=12 * 60, airport=True))
    assert not ok(case(t), line("taxi", time=23 * 60, airport=False, amount=5001))


def test_flight_class_and_booking_lead():
    f_in = case({"flight": {"hours": 6, "incl": True, "lead": 14}})
    f_ex = case({"flight": {"hours": 6, "incl": False, "lead": None}})
    fl = dict(amount=80000, date="2026-09-01")
    assert ok(f_in, line("flight", business=True, minutes=360, depart="2026-09-15", **fl))    # exactly 6 h, 14 days
    assert not ok(f_in, line("flight", business=True, minutes=355, depart="2026-09-15", **fl))
    assert not ok(f_in, line("flight", business=False, minutes=90, depart="2026-09-14", **fl))  # 13 days
    assert not ok(f_ex, line("flight", business=True, minutes=360, depart="2026-09-02", **fl))
    assert ok(f_ex, line("flight", business=True, minutes=365, depart="2026-09-02", **fl))


def test_conference_equipment_gift_parking_phone():
    assert not ok(case({"conference": {"cap": None}}), line("conference", event="x", amount=100))
    assert ok(case({"conference": {"cap": 50000}}), line("conference", event="x", amount=50000, approved=True))
    assert not ok(case({"conference": {"cap": 50000}}), line("conference", event="x", amount=50001, approved=True))
    e_in = case({"equipment": {"limit": 20000, "incl": True}})
    e_ex = case({"equipment": {"limit": 20000, "incl": False}})
    assert ok(e_in, line("equipment", item="a headset", amount=20000))           # up to 200.00 without approval
    assert not ok(e_ex, line("equipment", item="a headset", amount=20000))       # 200.00 or more needs approval
    assert ok(e_ex, line("equipment", item="a headset", amount=20000, approved=True))
    g = case({"gift": {"cap": 3000, "incl": True}})
    assert ok(g, line("gift", item="a book", recipients=3, amount=9000))
    assert not ok(g, line("gift", item="a book", recipients=3, amount=9003))
    assert not ok(g, line("gift", item=G.VOUCHER, recipients=1, amount=1000))
    assert ok(case({"parking": {"cap": 2000}}), line("parking", days=3, amount=6000))
    assert not ok(case({"parking": {"cap": 2000}}), line("parking", days=3, amount=6050))
    assert ok(case({"phone": {"cap": 6000}}), line("phone", month="July", amount=6000))


def test_unnamed_expense_types():
    assert not ok(case(MEAL_IN, unlisted="never"), line("other", item="Courier service"))
    assert ok(case(MEAL_IN, unlisted="general"), line("other", item="Courier service"))
    assert not ok(case(MEAL_IN, unlisted="general", receipt={"amount": 500, "incl": True}),
                  line("other", item="Courier service", receipt=False))
    assert not ok(case(MEAL_IN, unlisted="never"), line("parking", days=1, amount=500))   # parking not named here


def test_second_solver_agrees_yes_share_and_independent_answers():
    yes = total = items = 0
    mixes = collections.Counter()
    for i in range(500):
        rng = random.Random(f"t|{i}")
        try:
            c = G.draw(rng)
        except Retry:
            continue
        answers = G.solve(c)
        row = make_row(G, "train", i, G.render(c, rng), answers, rng)
        assert len(row["questions"]) == G.N_LINES
        for q, a in zip(row["questions"], answers):
            assert list(q["criteria"]) == ["yes", "no"]
            assert G.solve_text(q) == ("yes" if a else "no")
        yes += sum(answers)
        total += len(answers)
        items += 1
        mixes[sum(answers)] += 1
    assert items > 480
    assert 0.45 <= yes / total <= 0.55
    # independent draws: all-yes and all-no items occur (about 1/32 each), no forced mix
    assert mixes[0] > 0 and mixes[G.N_LINES] > 0


def test_draw_is_deterministic():
    def rows(seed):
        out = []
        for i in range(20):
            rng = random.Random(f"{seed}|{i}")
            c = G.draw(rng)
            out.append(make_row(G, "train", i, G.render(c, rng), G.solve(c), rng))
        return out
    assert rows("d") == rows("d")
