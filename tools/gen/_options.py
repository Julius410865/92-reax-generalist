"""Numeric answer options with the gold's value rank spread like the eval's (no "pick the 4th cheapest" shortcut).

The dev set's shipping_rate items put the correct total at these ranks among the options sorted by value (1 = smallest):
18 / 36 / 32 / 9 / 5 % (22 items). A generator passes its plausible wrong results (``errors``: the value a solver gets
with one rule missed or misapplied); ``options`` picks the gold's rank from that distribution, takes distractors from
the errors below / above the gold, and only when one side has too few it mirrors an error across the gold
(2 x gold - e) or uses a near miss (gold x (1 -/+ f)). The gold is option 0 of the returned list (``base.mc`` shuffles
the letters).
"""

from __future__ import annotations

from tools.gen.base import Retry, round_half_up

DEV_RANK = (0.18, 0.36, 0.32, 0.09, 0.05)
NEAR = (0.04, 0.07, 0.1, 0.13, 0.16, 0.2, 0.25)


def _weights(n: int) -> list[float]:
    w = list(DEV_RANK[:n])
    s = sum(w)
    return [x / s for x in w]


def options(rng, gold: float, errors, n: int, fmt) -> list[str]:
    g = round_half_up(gold)
    if g <= 0:
        raise Retry("gold must be positive")
    seen = {fmt(g)}
    below, above = [], []
    for e in errors:
        v = round_half_up(e)
        if v > 0 and fmt(v) not in seen:
            seen.add(fmt(v))
            (below if v < g else above).append(v)
    k = rng.choices(range(n), weights=_weights(n))[0]          # gold's 0-based rank among the n sorted values
    need_b, need_a = k, n - 1 - k

    def fill(side, other, need, sign):
        side = rng.sample(side, min(need, len(side)))
        pool = [round_half_up(2 * g - v) for v in other] + [round_half_up(g * (1 + sign * f)) for f in rng.sample(NEAR, len(NEAR))]
        for v in pool:
            if len(side) >= need:
                break
            if v > 0 and (v < g if sign < 0 else v > g) and fmt(v) not in seen:
                seen.add(fmt(v))
                side.append(v)
        if len(side) < need:
            raise Retry("not enough distinct distractors")
        return side

    lo = fill(below, above, need_b, -1)
    hi = fill(above, below, need_a, +1)
    return [fmt(g)] + [fmt(v) for v in lo + hi]


def rank_of_gold(criteria: dict, expected: str, parse) -> int:
    """1-based rank of the gold among the options sorted by value (for the checks)."""
    vals = sorted(criteria, key=lambda k: parse(criteria[k]))
    return vals.index(expected) + 1
