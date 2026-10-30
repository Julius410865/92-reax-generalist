"""arith_word_10: a multi-step arithmetic word problem (3-6 steps, stated rounding rule) -> its whole-number answer among
10 options. The generator, solver, renderer and second solver live in tools/gen/_arith.py (shared with arith_word_4);
the distractors are named mistakes (dropped / swapped steps, wrong direction, wrong base, complement, off by one,
rounding at the wrong step or in the wrong direction), then near values."""

from __future__ import annotations

from tools.gen import _arith as A

TASK = "arith_word_10"
PART, AREA, GOLD, HALF, COMPONENT = "T", "knowledge", False, "hf", None
N_OPTIONS = 10


def draw(rng):
    return A.draw(rng, N_OPTIONS)


solve = A.solve
render = A.render
solve_text = A.solve_text
