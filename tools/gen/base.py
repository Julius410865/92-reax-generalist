"""Shared pieces of the generated task types (DEV-GUIDELINES.md section 3).

A task module (tools/gen/<task>.py) defines:

    TASK, PART ("N" or "T"), AREA, GOLD (bool), HALF ("hf" or "aa"), COMPONENT (None or the aa component)
    draw(rng) -> case        a structured instance as plain data (lists / dicts / numbers / strings); all randomness from
                             the rng passed in, never a set iterated, raise Retry for an unusable draw
    solve(case) -> answers   pure, no randomness, no text: one answer per question (True / False for yes/no questions,
                             else the index of the gold option in the case's option list)
    render(case, rng) -> list of questions (same order as solve's answers), each {"instructions": str, "options":
                             [str, ...] or None for a yes/no question}; at least 5 instruction templates per task,
                             limits / units / rounding / order of operations always stated. The gold always comes from
                             solve(), never from the rendered text.
    solve_text(question_dict) -> the gold key   the SECOND SOLVER: reads only the rendered question (instructions and
                             criteria) and must reach the same answer on 100 % of the rows (check_generalist.py)

``make_row`` turns a rendered question list into an eval-v5.1 mirror row (position codes A.. with the gold position
shuffled by ``mc``, yes/no keys exactly yes / no, no IDK key, no state).
"""

from __future__ import annotations

import random
import string
from typing import Any, Sequence

GEN_VERSION = "gen-1"
LETTERS = string.ascii_uppercase
SCOPE = {"T": "same_skill", "N": "new_domain"}


class Retry(Exception):
    """An unusable draw: the generator moves to the next attempt of the same seed (never loops inside a generator)."""


def mc(rng: random.Random, options: Sequence[str], gold_index: int) -> tuple[dict[str, str], str]:
    """Options shuffled (gold position uniform), keyed by position codes A, B, ...; returns (criteria, gold key)."""
    from reax_subnet.spec import v5
    opts = list(options)
    if len(set(opts)) != len(opts):
        raise Retry("duplicate option texts")
    order = list(range(len(opts)))
    rng.shuffle(order)
    keys = v5.option_codes(len(opts))
    crit = {k: opts[j] for k, j in zip(keys, order)}
    return crit, keys[order.index(gold_index)]


def yesno(answer: bool) -> tuple[dict[str, str], str]:
    return {"yes": "Yes", "no": "No"}, "yes" if answer else "no"


def make_row(mod: Any, split: str, index: int, rendered: list[dict], answers: list[Any], rng: random.Random) -> dict:
    if len(rendered) != len(answers):
        raise ValueError(f"{mod.TASK}: render gave {len(rendered)} questions, solve {len(answers)} answers")
    qs = []
    for q, ans in zip(rendered, answers):
        if q["options"] is None:
            if not isinstance(ans, bool):
                raise ValueError(f"{mod.TASK}: a yes/no question needs a bool answer")
            crit, exp = yesno(ans)
        else:
            crit, exp = mc(rng, q["options"], int(ans))
        qs.append({"instructions": q["instructions"], "criteria": crit, "expected": exp})
    row = {"id": f"gen-{mod.TASK}-{split}-{index}", "tier": "mirror", "half": getattr(mod, "HALF", "hf"),
           "area": mod.AREA, "scope": SCOPE[mod.PART], "part": mod.PART, "task_type": mod.TASK, "gold": bool(mod.GOLD),
           "source": f"procgen_{mod.TASK}_{GEN_VERSION}", "source_id": f"tools/gen/{mod.TASK}.py@{GEN_VERSION}",
           "collected": "2026-10-27", "collected_utc": "2026-10-27T00:00:00Z", "public": False, "fresh": True,
           "idk": False, "split": split, "questions": qs}
    if getattr(mod, "COMPONENT", None):
        row["component"] = mod.COMPONENT
    return row


# --------------------------------------------------------------------------------------------- text helpers for tasks

def money(x: float, cur: str = "EUR") -> str:
    """Fixed money format: currency code, two decimals, comma thousands (the same format in rules and options)."""
    return f"{cur} {x:,.2f}"


def round_half_up(x: float, step: float = 0.01) -> float:
    """Round to the nearest ``step``, halves up, on the decimal value (no binary floating-point surprises)."""
    from decimal import ROUND_HALF_UP, Decimal
    q = Decimal(str(step))
    return float((Decimal(str(x)) / q).quantize(Decimal(1), rounding=ROUND_HALF_UP) * q)


def pick(rng: random.Random, seq: Sequence[Any], k: int) -> list[Any]:
    """k distinct elements in a random order (seq must be a list / tuple: never a set)."""
    return rng.sample(list(seq), k)


NAMES = ("Aiko", "Bastian", "Chiara", "Dmitri", "Elif", "Farah", "Goran", "Hana", "Ilse", "Jonas", "Kalani", "Lucia",
         "Mateo", "Nadia", "Oskar", "Priya", "Quentin", "Rosa", "Sven", "Tamar", "Umar", "Vera", "Wendell", "Ximena",
         "Yusuf", "Zofia", "Amara", "Bruno", "Cyrus", "Dalia", "Emeka", "Freya", "Gideon", "Hiro", "Ines", "Jamal")
