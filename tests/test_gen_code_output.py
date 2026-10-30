"""code_output: restricted execution, solver boundaries, named mistakes, option format and the second solver."""

from __future__ import annotations

import ast
import random

import pytest

from tools.gen import code_output as G
from tools.gen.base import Retry, make_row


def case(code, options, mode="print", var=None):
    return {"family": "test", "mode": mode, "code": code, "var": var, "sep": " ", "options": options, "origins": []}


# --------------------------------------------------------------------------------------------- restricted execution

def test_print_output_is_the_line_without_newline():
    assert G.execute("print(1, 'a', [2])", "print") == ("1 a [2]", (1, "a", [2]))
    assert G.execute("print(1, 2, sep=', ')", "print")[0] == "1, 2"


def test_value_mode_is_the_repr_of_the_named_variable():
    assert G.execute("def f(x):\n    return x * 2\n\nr = f('ab')", "value", "r")[0] == "'abab'"


@pytest.mark.parametrize("code", ["while True:\n    pass\nprint(1)",                   # never ends: step limit
                                  "import os\nprint(1)",                            # no imports
                                  "print(1)\nprint(2)",                             # two print calls
                                  "print('a\\nb')",                                 # two lines
                                  "x = 0",                                          # nothing printed
                                  "print(1 // 0)",                                  # runtime error
                                  "print(open('/etc/passwd'))"])                    # builtin not whitelisted
def test_unusable_programs_abort(code):
    with pytest.raises(G.Abort):
        G.execute(code, "print")


def test_step_limit_is_a_count_not_a_clock():
    loop = "t = 0\nfor i in range({n}):\n    t += 1\nprint(t)"
    assert G.execute(loop.format(n=1000), "print")[0] == "1000"
    with pytest.raises(G.Abort, match="step limit"):
        G.execute(loop.format(n=G.STEP_LIMIT), "print")


# ------------------------------------------------------------------------------------------------------ solve

def test_solve_returns_the_index_of_the_executed_output_at_any_position():
    code = "s = 0\nfor i in range(1, 5):\n    s += i\nprint(s)"
    assert G.solve(case(code, ["10", "9", "11"])) == [0]
    assert G.solve(case(code, ["9", "11", "15", "10"])) == [3]


def test_solve_value_mode_uses_repr():
    code = "def f(w):\n    return w[::-1]\n\nout = f('abc')"
    assert G.solve(case(code, ["cba", "'cba'", "'abc'"], mode="value", var="out")) == [1]


def test_solve_raises_retry_when_output_is_missing_or_unusable():
    with pytest.raises(Retry):
        G.solve(case("print(3)", ["4", "5"]))
    with pytest.raises(Retry):
        G.solve(case("while True:\n    pass", ["1", "2"]))


def test_off_by_one_boundaries_of_range_and_comparisons_are_executed_exactly():
    assert G.execute("print(list(range(2, 6)))", "print")[0] == "[2, 3, 4, 5]"
    assert G.execute("print(len([i for i in range(10) if i < 4]), len([i for i in range(10) if i <= 4]))", "print")[0] == "4 5"
    assert G.execute("print(-7 // 2, -7 % 3, 7 // -2)", "print")[0] == "-4 2 -4"


# --------------------------------------------------------------------------------------------------- named mistakes

def mistake_outputs(code, mode="print", var=None):
    out = {}
    for name, t in G.mutants(ast.parse(code)):
        try:
            out.setdefault(name, set()).add(G.execute(t, mode, var)[0])
        except G.Abort:
            pass
    return out


def test_loop_bound_mistakes():
    m = mistake_outputs("t = 0\nfor i in range(1, 4):\n    t += i\nprint(t)")
    assert {"10", "3", "5"} <= m["off-by-one loop bound"]       # range(1, 5), range(1, 3), range(2, 4)


def test_precedence_and_division_mistakes():
    m = mistake_outputs("a = 2 + 3 * 4\nb = -7 // 2\nc = -7 % 3\nprint(a, b, c)")
    assert "20 -4 2" in m["operator precedence read left to right"]
    assert "14 -3 2" in m["truncating instead of floor division"]
    assert "14 -4 -1" in m["C-style remainder"]


def test_alias_copy_and_string_number_mistakes():
    assert "[1]" in mistake_outputs("a = [1]\nb = a\nb.append(2)\nprint(a)")["copy vs alias"]
    assert "[1, 2]" in mistake_outputs("a = [1]\nb = a[:]\nb.append(2)\nprint(a)")["copy vs alias"]
    assert "7" in mistake_outputs("x = '3'\ny = x + str(4)\nprint(y)")["string vs number"]


def test_mutable_default_and_tuple_assignment_mistakes():
    code = "def add(v, bag=[]):\n    bag.append(v)\n    return len(bag)\n\nprint(add(1), add(2))"
    assert G.execute(code, "print")[0] == "1 2"
    assert "1 1" in mistake_outputs(code)["mutable default read as fresh"]
    assert "2 4" in mistake_outputs("a, b = 1, 2\na, b = b, a + b\nprint(a, b)")["tuple assignment done one by one"]


def test_combined_mistakes_apply_together():
    tree = ast.parse("t = 0\nfor i in range(3):\n    t += 1 + i * 2\nprint(t)")
    sites = G.mistake_sites(tree)
    rng_i = next(m for m in sites if G.MUTATORS[m[0]][0] == "off-by-one loop bound" and m[2] == 0)
    prec = next(m for m in sites if G.MUTATORS[m[0]][0] == "operator precedence read left to right")
    assert G.execute(G.apply_mistakes(tree, [rng_i]), "print")[0] == "16"
    assert G.execute(G.apply_mistakes(tree, [prec]), "print")[0] == "12"            # (1 + i) * 2 over 0..2
    assert G.execute(G.apply_mistakes(tree, [rng_i, prec]), "print")[0] == "20"     # both: (1 + i) * 2 over 0..3


# ------------------------------------------------------------------------------------------------- option format

def test_compatible_keeps_one_format():
    assert G.compatible(3, 5) and not G.compatible(3, "3") and not G.compatible(3, True) and not G.compatible(3, 3.0)
    assert G.compatible((1, "a"), (2, "b")) and not G.compatible((1, "a"), (1, "a", 2))
    assert G.compatible([1, 2], [3]) and not G.compatible([1, 2], ["x"])
    assert not G.compatible(12, 10 ** 6)                       # an exploded number is not a plausible option


def test_print_options_never_hide_whitespace():
    assert not G.text_ok(" 1", "print") and not G.text_ok("a  b", "print") and G.text_ok("'a  b'", "value")


# --------------------------------------------------------------------------------------------------- end to end

def rows(n=150, seed="t"):
    out = []
    for i in range(n):
        for a in range(20):
            rng = random.Random(f"{seed}|{i}|{a}")
            try:
                c = G.draw(rng)
                ans = G.solve(c)
                out.append((c, make_row(G, "train", i, G.render(c, rng), ans, rng)))
                break
            except Retry:
                continue
    return out


def test_second_solver_agrees_and_options_are_well_formed():
    rs = rows()
    assert len(rs) == 150
    counts, positions = set(), set()
    for c, r in rs:
        q = r["questions"][0]
        assert G.solve_text(q) == q["expected"]
        assert 2 <= len(q["criteria"]) <= 10 and len(set(q["criteria"].values())) == len(q["criteria"])
        assert "import" not in c["code"] and "random" not in c["code"]
        counts.add(len(q["criteria"]))
        positions.add(list(q["criteria"]).index(q["expected"]))
    assert counts == set(range(2, 11)) and len(positions) >= 8


def test_draws_are_deterministic():
    a = [(c["code"], c["options"]) for c, _ in rows(20, "d")]
    b = [(c["code"], c["options"]) for c, _ in rows(20, "d")]
    assert a == b
