"""#23 shipping_rate: solver boundaries (DEV-GUIDELINES.md section 7) and the rendered text's second solver."""

from __future__ import annotations

import collections
import copy
import random

from tools.gen import shipping_rate as G
from tools.gen.base import Retry, make_row


def case(**kw):
    """Zone 1 / Zone 2, bands up to 1 / 5 / 10 kg (inclusive), no surcharges, no VAT, final rounding to 0.01."""
    c = {"cur": "EUR", "carrier": "Corvid Post", "domestic": False,
         "zones": [{"label": "Zone 1", "dest": ["Portugal", "Malta"]}, {"label": "Zone 2", "dest": ["Japan", "Chile"]}],
         "limits": [1000, 5000, 10000], "incl": True, "prices": [[500, 800, 1200], [700, 1100, 1600]],
         "per_kg": None, "divisor": None, "wround": 0, "charges": {}, "discount": None, "minimum": None, "vat": None,
         "rounding": {"mode": "final", "step": 1, "dir": "nearest"}, "irrelevant": [],
         "shipment": {"sender": "Rosa", "dest": "Portugal", "weight": 3000, "dims": [20, 20, 10], "declared": 10000,
                      "express": False, "insured": False, "online": False, "account": False, "saturday": False,
                      "signature": False, "lithium": False, "residential": False, "cod": False, "date": "2026-10-01"}}
    for k, v in kw.items():
        if k in c["shipment"] and k not in c:
            c["shipment"][k] = v
        else:
            c[k] = v
    return c


def price(c):
    return G._price(c)


def test_inclusive_band_limit_belongs_to_the_lower_band():
    assert price(case(weight=1000)) == 500
    assert price(case(weight=1010)) == 800
    assert price(case(weight=5000)) == 800
    assert price(case(weight=10000)) == 1200


def test_exclusive_band_limit_belongs_to_the_next_band():
    assert price(case(weight=1000, incl=False)) == 800
    assert price(case(weight=990, incl=False)) == 500
    assert price(case(weight=5000, incl=False)) == 1200


def test_zone_lookup():
    assert price(case(dest="Chile")) == 1100
    d = case(domestic=True, zones=[{"label": "Zone 1", "ranges": [[10000, 49999]]},
                                   {"label": "Zone 2", "ranges": [[50000, 59999], [70000, 99999]]},
                                   {"label": "Zone 3", "ranges": [[60000, 69999]]}],
             prices=[[500, 800, 1200], [700, 1100, 1600], [900, 1300, 1900]], dest=49999)
    assert price(d) == 800
    d["shipment"]["dest"] = 50000
    assert price(d) == 1100
    d["shipment"]["dest"] = 69999
    assert price(d) == 1300


def test_volumetric_weight_wins_when_larger_and_rounding_up_moves_the_band():
    # 50 x 40 x 30 / 5000 = 12 kg > top band: refused unless per kg; use 40 x 25 x 25 / 5000 = 5.0 kg exactly
    assert price(case(weight=2000, dims=[40, 25, 25], divisor=5000)) == 800
    assert price(case(weight=2000, dims=[40, 25, 26], divisor=5000)) == 1200          # 5.2 kg
    assert price(case(weight=5200, dims=[10, 10, 10], divisor=5000)) == 1200          # actual weight wins
    assert price(case(weight=1100, wround=1000)) == 800                               # 1.1 -> 2 kg
    assert price(case(weight=4600, wround=500)) == 800                                # 4.6 -> 5.0 kg (inclusive)
    assert price(case(weight=4600, wround=500, incl=False)) == 1200                   # 5.0 kg in the next band up
    assert price(case(weight=900, wround=1000)) == 500                                # 0.9 -> 1 kg, inclusive


def test_started_kilograms_above_the_top_band():
    c = case(per_kg=150)
    for grams, extra in ((10000, 0), (10100, 1), (11000, 1), (11010, 2)):
        c["shipment"]["weight"] = grams
        assert price(c) == 1200 + 150 * extra
    c["incl"] = False
    c["shipment"]["weight"] = 10000               # "10 kg or more": the last band plus 0 started kg
    assert price(c) == 1200


def test_surcharge_limits_inclusive_and_exclusive():
    over_in = {"oversize": {"side": 100, "incl": True, "fee": 900}}
    over_ex = {"oversize": {"side": 100, "incl": False, "fee": 900}}
    assert price(case(charges=over_in, dims=[100, 20, 10])) == 800 + 900
    assert price(case(charges=over_ex, dims=[100, 20, 10])) == 800
    assert price(case(charges=over_ex, dims=[20, 101, 10])) == 800 + 900
    peak = {"peak": {"start": "2026-11-20", "end": "2026-12-24", "fee": 300}}
    for d, fee in (("2026-11-19", 0), ("2026-11-20", 300), ("2026-12-24", 300), ("2026-12-25", 0)):
        assert price(case(charges=peak, date=d)) == 800 + fee


def test_flat_surcharges_apply_only_when_requested():
    ch = {"saturday": {"fee": 450}, "signature": {"fee": 200}, "remote": {"prefixes": None, "dest": ["Malta"], "fee": 600}}
    assert price(case(charges=copy.deepcopy(ch))) == 800
    assert price(case(charges=copy.deepcopy(ch), saturday=True, dest="Malta")) == 800 + 450 + 600
    ins = {"insurance": {"pct": 15, "min": 300}}
    assert price(case(charges=ins, insured=True, declared=10000)) == 800 + 300         # 1.5 % of 100.00 = 1.50 < 3.00
    assert price(case(charges=ins, insured=True, declared=30000)) == 800 + 450


def test_rounding_halves_up_at_the_stated_step():
    # 8.10 x 2.5 % = 0.2025 and 8.10 x 2.5 % again: "each" rounds both to 0.20; "final" adds 0.405 -> 0.41 at the end
    ch = {"fuel": {"pct": 25, "after": None}, "express": {"pct": 25, "fee": None}}
    base = {"prices": [[500, 810, 1200], [700, 1100, 1600]], "charges": ch, "express": True}
    assert price(case(**copy.deepcopy(base), rounding={"mode": "each", "step": 1, "dir": "nearest"})) == 810 + 20 + 20
    assert price(case(**copy.deepcopy(base), rounding={"mode": "final", "step": 1, "dir": "nearest"})) == 810 + 41
    # exactly half a cent rounds up: 9.00 x 0.5 % = 0.045 -> 0.05 (each), 9.045 -> 9.05 (final)
    assert price(case(prices=[[500, 900, 1200], [700, 1100, 1600]], charges={"fuel": {"pct": 5, "after": None}},
                      rounding={"mode": "each", "step": 1, "dir": "nearest"})) == 905
    assert price(case(prices=[[500, 900, 1200], [700, 1100, 1600]], charges={"fuel": {"pct": 5, "after": None}},
                      rounding={"mode": "final", "step": 1, "dir": "nearest"})) == 905
    # coarse: 8.25 -> nearest 0.50 is 8.50 (halves up), 8.24 -> 8.00; up to the next 0.10: 8.01 -> 8.10
    for p, want in ((825, 850), (824, 800)):
        assert price(case(prices=[[500, p, 1200], [700, 1100, 1600]], rounding={"mode": "coarse", "step": 50, "dir": "nearest"})) == want
    assert price(case(prices=[[500, 801, 1200], [700, 1100, 1600]], rounding={"mode": "coarse", "step": 10, "dir": "up"})) == 810
    assert price(case(prices=[[500, 800, 1200], [700, 1100, 1600]], rounding={"mode": "coarse", "step": 10, "dir": "up"})) == 800


def test_discount_order_condition_minimum_and_vat():
    ch = {"fuel": {"pct": 100, "after": True}}
    d = {"kind": "base", "cond": None, "pct": 100, "amount": None}
    assert price(case(charges=copy.deepcopy(ch), discount=d)) == 720 + 72                # fuel on the discounted base
    ch["fuel"]["after"] = False
    assert price(case(charges=copy.deepcopy(ch), discount=d)) == 720 + 80
    net = {"kind": "net", "cond": "online", "pct": 100, "amount": None}
    assert price(case(charges={"saturday": {"fee": 200}}, saturday=True, discount=net, online=True)) == 900
    assert price(case(charges={"saturday": {"fee": 200}}, saturday=True, discount=net, online=False)) == 1000
    v = {"kind": "voucher", "cond": "account", "pct": None, "amount": 300}
    assert price(case(discount=v, account=True, vat=200)) == 600                         # (8.00 - 3.00) x 1.2
    assert price(case(discount=v, account=True, vat=200, minimum=600)) == 720            # raised to 6.00, then VAT
    assert price(case(discount=v, account=False, vat=200, minimum=600)) == 960


def test_named_mistakes_differ_from_the_gold():
    c = case(charges={"saturday": {"fee": 450}}, saturday=True, vat=200,
             discount={"kind": "voucher", "cond": None, "pct": None, "amount": 300})
    gold = price(c)
    assert G._price(c, {"drop": "saturday"}) == gold - 540
    assert G._price(c, {"double": "saturday"}) == gold + 540
    assert G._price(c, {"vat_order": True}) == gold + 60                                  # discount after VAT
    assert G._price(c, {"no_vat": True}) == 950


def _rows(n, seed="t"):
    out = []
    for i in range(n):
        rng = random.Random(f"{seed}|{i}")
        try:
            c = G.draw(rng)
        except Retry:
            continue
        answers = G.solve(c)
        out.append((c, make_row(G, "train", i, G.render(c, rng), answers, rng)))
    return out


def test_second_solver_agrees_and_options_are_uniform():
    rows = _rows(600)
    assert len(rows) > 550
    ranks = collections.Counter()
    for c, row in rows:
        q = row["questions"][0]
        assert G.solve_text(q) == q["expected"]
        texts = list(q["criteria"].values())
        assert len(texts) in (4, 5) and len(set(texts)) == len(texts)
        assert all(t.startswith(c["cur"] + " ") and t.count(".") == 1 and len(t.rsplit(".", 1)[1]) == 2 for t in texts)
        vals = sorted(c["options"])
        ranks[vals.index(c["options"][G.solve(c)[0]]) / (len(vals) - 1)] += 1
    # the gold is the lowest / highest value about as often as any other rank
    lo, hi = ranks[0.0] / len(rows), ranks[1.0] / len(rows)
    assert 0.12 < lo < 0.30 and 0.12 < hi < 0.30


def test_draw_is_deterministic():
    a = [r for _, r in _rows(30, "d")]
    b = [r for _, r in _rows(30, "d")]
    assert a == b
