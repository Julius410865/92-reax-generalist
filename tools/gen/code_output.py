"""code_output: a short random Python 3 program -> which option is its output.

Two presentations, both a single question with 2-10 options (as the dev items):
* ``print``: the program ends with one ``print(...)`` call (executed exactly once, one line); the options are the exact
  printed text without the trailing newline.
* ``value``: the program defines a function and stores one call in a named variable; the options are ``repr()`` of that
  variable's value.

The program comes from one of ~20 families (loops, conditionals, string / list / dict operations, integer arithmetic,
simple functions, recursion, aliasing ...), with random names, literals and structure. No imports, no input, no
randomness, no floats. The gold is the output of actually executing the program in a restricted namespace (no
``__import__``, a short builtin whitelist, a deterministic step limit): ``solve`` runs it; a draw whose program errors,
loops past the step limit, prints more than once or prints a float raises Retry.

Distractors are the outputs of the same program with one named mistake applied to its syntax tree (off-by-one loop bound,
boundary ``<`` vs ``<=``, operator precedence read left to right, truncating instead of floor division, C-style
remainder, copy vs alias, ``+=`` vs rebinding, append vs extend, prepend vs append, elif read as if, ignored break /
continue / ``not`` / ``reverse`` / filter, misread indentation, ``**`` vs ``*``, ``%`` vs ``//``, 1-based indexing,
inclusive slice end, ``sorted()`` read as in-place, tuple assignment done one by one, string vs number concatenation,
mutable default read as fresh, string method read as in-place or ignored, list-multiplied rows read as copies), then
pairs of mistakes, then near values of the gold or of a mistake value. Every option has the gold's format (the same
type structure, the same print layout).

``solve_text`` reads only the rendered question: it extracts the code block, runs it the same restricted way and returns
the key of the option equal to the output.
"""

from __future__ import annotations

import ast
import builtins
import copy
import io
import re
import sys

from tools.gen.base import Retry

TASK = "code_output"
PART, AREA, GOLD, HALF, COMPONENT = "T", "knowledge", False, "hf", None

STEP_LIMIT = 20000          # trace events (line / call / return) per run: deterministic, no clock
MAX_LINES = 26
MAX_OPTION_CHARS = 90
N_OPTIONS = (2, 3, 4, 5, 6, 7, 8, 9, 10)
N_WEIGHTS = (15, 5, 11, 7, 7, 8, 12, 17, 18)

# --------------------------------------------------------------------------------------------------- restricted run

_SAFE = ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "int", "isinstance", "len", "list", "map",
         "max", "min", "range", "repr", "reversed", "sorted", "str", "sum", "tuple", "zip", "chr", "ord")


class Abort(Exception):
    """The program (or a mutant of it) is unusable: error, step limit, wrong print count, bad output."""


def execute(code, mode: str, var: str | None = None) -> tuple[str, tuple]:
    """Run ``code`` (source text or an ast.Module) in a restricted namespace.

    Returns (output text, values): for ``print`` the printed line without its newline and the print arguments; for
    ``value`` the repr of ``var`` and (value,). Raises Abort on any error, on more than STEP_LIMIT trace events, or when
    a print program does not print exactly one line with exactly one print call.
    """
    buf = io.StringIO()
    calls: list[tuple] = []

    def _print(*args, sep=" ", end="\n"):
        calls.append(args)
        if len(calls) > 1:
            raise Abort("print called more than once")
        builtins.print(*args, sep=sep, end=end, file=buf)

    env = {"__builtins__": {**{k: getattr(builtins, k) for k in _SAFE}, "print": _print}, "__name__": "__main__"}
    steps = [0]

    def tracer(frame, event, arg):
        steps[0] += 1
        if steps[0] > STEP_LIMIT:
            raise Abort("step limit")
        return tracer

    try:
        compiled = compile(code, "<program>", "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise Abort(f"does not compile: {exc}") from None
    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        exec(compiled, env)
    except Abort:
        raise
    except BaseException as exc:          # noqa: BLE001 - any failure of a generated program is just an unusable draw
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise Abort(f"{type(exc).__name__}: {exc}") from None
    finally:
        sys.settrace(old)
    if mode == "print":
        text = buf.getvalue()
        if len(calls) != 1 or not text.endswith("\n") or "\n" in text[:-1]:
            raise Abort("not exactly one printed line")
        return text[:-1], calls[0]
    if var not in env:
        raise Abort(f"{var} not set")
    return repr(env[var]), (env[var],)


# ----------------------------------------------------------------------------------------------- value formats

def _has_float(v) -> bool:
    if isinstance(v, float):
        return True
    if isinstance(v, (list, tuple)):
        return any(_has_float(e) for e in v)
    if isinstance(v, dict):
        return any(_has_float(k) or _has_float(e) for k, e in v.items())
    return not isinstance(v, (int, str, type(None)))      # sets, functions, objects: not a fixed format


def _kind(v) -> str:
    return "bool" if isinstance(v, bool) else type(v).__name__


def compatible(g, d) -> bool:
    """d has the same format as g: same type, same tuple length, element / key / value types within g's."""
    if _kind(g) != _kind(d) or _has_float(d):
        return False
    if isinstance(g, tuple):
        return len(g) == len(d) and all(compatible(a, b) for a, b in zip(g, d))
    if isinstance(g, list):
        if not g or not d:
            return True
        return all(any(compatible(a, b) for a in g[:4]) for b in d)
    if isinstance(g, dict):
        if not g or not d:
            return True
        gk, gv = list(g)[:4], list(g.values())[:4]
        return all(any(compatible(a, b) for a in gk) for b in d) and all(any(compatible(a, b) for a in gv) for b in d.values())
    if isinstance(g, int) and not isinstance(g, bool):
        return abs(d) <= 10 * max(abs(g), 20)          # no absurd outliers (a mistake that explodes a number)
    return True


def text_ok(text: str, mode: str) -> bool:
    if not text or len(text) > MAX_OPTION_CHARS:
        return False
    if mode == "print" and (text != text.strip() or "  " in text):
        return False                      # invisible whitespace would make two options look alike
    return True


def fmt(values: tuple, mode: str, sep: str) -> str:
    return repr(values[0]) if mode == "value" else sep.join(str(a) for a in values)


# ------------------------------------------------------------------------------------------------- name pools

LIST_NAMES = ("nums", "vals", "data", "items", "xs", "seq", "arr", "values", "pool", "stack", "marks", "scores",
              "points", "levels", "row", "bag", "batch", "parts", "cells", "heap", "lst", "buf", "queue", "trail")
INT_NAMES = ("total", "acc", "count", "res", "n", "m", "t", "score", "level", "limit", "base", "cur", "best", "low",
             "high", "carry", "tally", "steps", "z", "q", "u", "w", "r", "hits", "run", "gap", "span", "mark")
STR_NAMES = ("s", "word", "text", "name", "tag", "code", "label", "token", "msg", "key", "src", "line", "phrase", "chunk")
DICT_NAMES = ("counts", "freq", "seen", "table", "index", "groups", "book", "lookup", "bins", "tally_map", "registry")
LOOP_NAMES = ("i", "j", "k", "idx", "pos", "step_no", "a1", "b1")
ELEM_NAMES = ("v", "x", "e", "item", "c", "y", "el", "p")
FUNC_NAMES = ("f", "g", "h", "calc", "walk", "fold", "mix", "crunch", "combine", "scan", "build", "churn", "twist",
              "process", "transform", "reduce_all", "evaluate", "trace_it", "work", "digest")
RESULT_NAMES = ("result", "out", "answer", "value", "final", "outcome", "got", "ret")
WORDS = ("amber", "basil", "cedar", "delta", "ember", "fjord", "glyph", "heron", "indigo", "jasper", "lumen", "mosaic",
         "nectar", "orbit", "pepper", "quiver", "raven", "sable", "tundra", "umber", "velvet", "willow", "xenon",
         "yarrow", "zephyr", "bramble", "cinder", "dapple", "falcon", "garnet", "hollow", "ivory", "juniper", "kelp",
         "lagoon", "meadow", "nimbus", "otter", "prism", "ripple", "saffron", "thistle", "vortex", "walnut", "acorn",
         "badger", "comet", "dune", "echo", "flint", "gecko", "hazel", "iris", "jungle", "koala", "lemon", "mango",
         "noodle", "olive", "parrot", "quail", "rocket", "salmon", "tiger", "urchin", "violet", "wombat", "yeti")
SHORT = ("ox", "elk", "yak", "emu", "owl", "bee", "ant", "cod", "eel", "fox", "gnu", "hen", "jay", "koi", "ram", "asp",
         "bat", "cat", "dog", "pig", "rat", "ape", "kit", "orca")
NOUNS = ("fig", "kiwi", "plum", "date", "lime", "pear", "sage", "mint", "corn", "bean", "rice", "oat", "rye", "yam",
         "leek", "kale", "taro", "okra", "chia", "nut")


class Names:
    """Distinct identifiers for one program (membership only, never iterated)."""

    def __init__(self, rng):
        self.rng, self.used = rng, set()

    def get(self, pool) -> str:
        cands = [n for n in pool if n not in self.used]
        n = self.rng.choice(cands)
        self.used.add(n)
        return n


def _ints(rng, k, lo=-5, hi=20):
    return [rng.randint(lo, hi) for _ in range(k)]


def _word(rng):
    w = rng.choice(WORDS)
    if rng.random() < 0.3:
        w = w + rng.choice(["-", "_", ""]) + rng.choice(WORDS)
    return w[:14]


def spec(setup, body, out, helpers=(), sep=" "):
    return {"setup": list(setup), "body": list(body), "out": list(out), "helpers": list(helpers), "sep": sep}


# --------------------------------------------------------------------------------------------------- families
# Each family returns a spec: setup [(name, literal value)], body lines (top-level indentation), output expressions,
# optional helper definitions (lines) placed before everything else.

def fam_loop_acc(rng, nb):
    acc, i = nb.get(INT_NAMES), nb.get(LOOP_NAMES)
    start, step = rng.choice([0, 0, 1, 2, 3, 5]), rng.choice([1, 1, 1, 2, 3])
    stop = start + rng.randint(4, 11)
    args = f"{stop}" if start == 0 and step == 1 else f"{start}, {stop}" + (f", {step}" if step > 1 else "")
    m = rng.choice([2, 3, 4, 5])
    r = rng.randrange(m)
    c1, c2 = rng.randint(2, 5), rng.randint(1, 9)
    e1 = rng.choice([f"{i} * {c1} + {c2}", f"{c2} + {i} * {c1}", f"{i} - {c2} % {c1}", f"{c2} * {i} - {c1}",
                     f"{i} + {i} // {c1}", f"{i} ** 2 // {c1}", f"{c1} + {i} % {c2 + 1}", f"{i} * {i} - {c2}"])
    cond = rng.choice([f"{i} % {m} == {r}", f"{i} % {m} == {r} and {i} > {start + 1}", f"not {i} % {m}",
                       f"{i} % {m} != {r}", f"{i} > {start + 2} or {i} % {m} == 0"])
    lines = [f"for {i} in range({args}):", f"    if {cond}:", f"        {acc} += {e1}"]
    shape = rng.choice(["if", "else", "elif", "elif_else", "elif_else"])
    if shape.startswith("elif"):
        t = rng.randint(start + 1, stop - 1)
        lines += [f"    elif {i} {rng.choice(['<', '<=', '>', '>='])} {t}:",
                  f"        {acc} -= {rng.choice([i, f'{c1} * {i}', str(c2), f'{i} // 2'])}"]
    if shape.endswith("else"):
        lines += ["    else:", f"        {acc} += {rng.choice(['1', str(c1), f'{i} // 2', f'{i} % 3'])}"]
    out = [acc] if rng.random() < 0.65 else [acc, i]
    return spec([(acc, rng.randint(0, 12))], lines, out)


def fam_while(rng, nb):
    n, steps = nb.get(INT_NAMES), nb.get(INT_NAMES)
    k, d, t = rng.choice([2, 3, 2]), rng.randint(1, 7), rng.randint(1, 9)
    cmpop = rng.choice([">", ">="])
    upd_even = rng.choice([f"{n} //= {k}", f"{n} = {n} // {k}", f"{n} = {n} // {k} + 1" if k > 2 else f"{n} //= {k}"])
    upd_odd = rng.choice([f"{n} -= {d}", f"{n} = {n} - {d}", f"{n} = ({n} - {d}) // 2 + {d}" if d > 1 else f"{n} -= 1"])
    lines = [f"while {n} {cmpop} {t}:", f"    if {n} % {k} == 0:", f"        {upd_even}", "    else:",
             f"        {upd_odd}", f"    {steps} += 1"]
    out = rng.choice([[n, steps], [steps], [steps, n]])
    return spec([(n, rng.randint(18, 160)), (steps, 0)], lines, out)


def fam_alias(rng, nb):
    a, b = nb.get(LIST_NAMES), nb.get(LIST_NAMES)
    vals = _ints(rng, rng.randint(3, 5), 0, 15)
    x, y = rng.randint(20, 40), rng.randint(41, 60)
    link = rng.choice([f"{a}", f"{a}", f"{a}[:]", f"list({a})", f"{a}.copy()"])
    ops_b = [f"{b}.append({x})", f"{b}[0] = {x}", f"{b} += [{x}, {y}]", f"{b}.extend([{x}])", f"{b}.insert(1, {x})",
             f"{b}.pop()", f"{b} = {b} + [{x}]", f"{b}.append([{x}, {y}])"]
    ops_a = [f"{a}[-1] = {y}", f"{a}.append({y})", f"{a} = {a} + [{y}]", f"{a}.sort()", f"{a}.reverse()",
             f"{a}[1] += {x}", f"{a}.remove({vals[0]})"]
    body = [f"{b} = {link}"]
    seq = [rng.choice(ops_b), rng.choice(ops_a)]
    if rng.random() < 0.5:
        seq.append(rng.choice(ops_b))
    rng.shuffle(seq)
    body += seq
    out = rng.choice([[a, b], [b, a], [f"len({a})", b], [a, f"len({b})"], [f"sum({a})", f"{b}[-1]"], [f"{a}[0]", b]])
    return spec([(a, vals)], body, out)


def fam_grid(rng, nb):
    g = nb.get(("grid", "board", "table2", "mat", "rows", "field"))
    w, h = rng.randint(2, 3), rng.randint(2, 3)
    fill = rng.randint(0, 2)
    make = rng.choice([f"[[{fill}] * {w}] * {h}", f"[[{fill}] * {w} for _ in range({h})]", f"[[{fill}] * {w}] * {h}"])
    body = [f"{g} = {make}"]
    for _ in range(rng.randint(2, 3)):
        r_, c_ = rng.randrange(h), rng.randrange(w)
        body.append(rng.choice([f"{g}[{r_}][{c_}] = {rng.randint(3, 9)}", f"{g}[{r_}][{c_}] += {rng.randint(1, 5)}"]))
    out = rng.choice([[g], [g], [f"sum(sum(r) for r in {g})", f"{g}[0]"], [f"{g}[-1]", f"{g}[0][0]"]])
    return spec([], body, out)


def fam_string_build(rng, nb):
    word, outv, ch = nb.get(STR_NAMES), nb.get(STR_NAMES), nb.get(("ch", "c", "letter", "char"))
    w = _word(rng)
    skip = rng.choice(w)
    vow = rng.choice(['"aeiou"', '"aeiou"', '"abc"', '"rst"', '"lmn"'])
    first = rng.choice([f"{outv} = {ch}.upper() + {outv}", f"{outv} = {outv} + {ch}.upper()", f"{outv} += {ch} * 2",
                        f"{outv} = {ch} + {outv}"])
    other = rng.choice([f"{outv} = {outv} + {ch}", f"{outv} += {ch}", f"{outv} = {ch} + {outv}"])
    lines = [f"for {ch} in {word}:", f"    if {ch} in {vow}:", f"        {first}"]
    if rng.random() < 0.5:
        lines += [f"    elif {ch} == {skip!r}:", "        continue" if rng.random() < 0.6 else "        break"]
    lines += ["    else:", f"        {other}"]
    out = [outv] if rng.random() < 0.6 else [outv, f"len({outv})"]
    return spec([(word, w), (outv, "")], lines, out)


def fam_index_string(rng, nb):
    word, outv, i = nb.get(STR_NAMES), nb.get(STR_NAMES), nb.get(LOOP_NAMES)
    w = _word(rng)
    m = rng.choice([2, 3])
    start = rng.choice([0, 1])
    rngs = f"len({word})" if start == 0 else f"{start}, len({word})"
    pick = rng.choice([f"{word}[{i}]", f"{word}[{i}].upper()", f"{word}[-{i} - 1]", f"{word}[{i} - 1]"])
    lines = [f"for {i} in range({rngs}):", f"    if {i} % {m} == {rng.randrange(m)}:", f"        {outv} += {pick}"]
    if rng.random() < 0.5:
        lines += ["    else:", f"        {outv} = {word}[{i}] + {outv}" if rng.random() < 0.5 else f"        {outv} += '.'"]
    out = rng.choice([[outv], [outv], [outv, f"len({outv})"]])
    return spec([(word, w), (outv, "")], lines, out)


def fam_str_num(rng, nb):
    a, b = nb.get(STR_NAMES), nb.get(INT_NAMES)
    names = [nb.get(INT_NAMES) for _ in range(3)]
    av, bv = str(rng.randint(2, 9)) if rng.random() < 0.6 else str(rng.randint(10, 40)), rng.randint(2, 4)
    exprs = [f"{a} * {b}", f"int({a}) * {b}", f"{a} + str({b})", f"int({a}) + {b}", f"str({b}) + {a}",
             f"int({a} + str({b})) // 2", f"len({a} * {b})", f"int({a}) * {b} + int({a} * 2)", f"str(int({a}) + {b}) * 2"]
    chosen = rng.sample(exprs, rng.randint(2, 3))
    body = [f"{nm} = {e}" for nm, e in zip(names, chosen)]
    outs = names[:len(chosen)]
    out = outs if len(outs) == 2 or rng.random() < 0.5 else outs[-2:]
    return spec([(a, av), (b, bv)], body, out)


def fam_dict_count(rng, nb):
    seq, d, w = nb.get(LIST_NAMES), nb.get(DICT_NAMES), nb.get(ELEM_NAMES)
    keys = rng.sample(SHORT, rng.randint(3, 4))
    vals = [rng.choice(keys) for _ in range(rng.randint(5, 9))]
    style = rng.choice(["get", "in", "setdefault", "len"])
    if style == "get":
        lines = [f"for {w} in {seq}:", f"    {d}[{w}] = {d}.get({w}, 0) + 1"]
    elif style == "in":
        lines = [f"for {w} in {seq}:", f"    if {w} in {d}:", f"        {d}[{w}] += 1", "    else:", f"        {d}[{w}] = 1"]
    elif style == "setdefault":
        lines = [f"for pos, {w} in enumerate({seq}):", f"    {d}.setdefault({w}, []).append(pos)"]
    else:
        lines = [f"for {w} in {seq}:", f"    {d}[len({w})] = {d}.get(len({w}), '') + {w}[0]"]
    if rng.random() < 0.3:
        lines[0] = lines[0].replace(f"in {seq}:", f"in {seq}[1:]:")
    k = rng.choice(keys)
    outs = {"get": [[d], [f"max({d}, key={d}.get)", f"{d}[{k!r}]"], [f"len({d})", d], [f"sorted({d}.items())"]],
            "in": [[d], [f"{d}[{k!r}]", f"len({d})"], [f"sorted({d}.values())"]],
            "setdefault": [[d], [f"{d}[{k!r}]"], [f"len({d})", f"{d}.get({k!r}, [])"]],
            "len": [[d], [f"sorted({d})", f"{d}[{len(k)}]"]]}[style]
    out = rng.choice(outs)
    return spec([(seq, vals), (d, {})], lines, out)


def fam_floor_mod(rng, nb):
    a, b = nb.get(INT_NAMES), nb.get(INT_NAMES)
    q, r = nb.get(INT_NAMES), nb.get(INT_NAMES)
    if rng.random() < 0.7:
        av, bv = -rng.randint(3, 40), rng.randint(2, 7)
    else:
        av, bv = rng.randint(3, 40), -rng.randint(2, 7)
    if av % bv == 0:
        av -= 1
    body = [f"{q} = {a} // {b}", f"{r} = {a} % {b}"]
    extra = rng.choice([None, f"{q} * {b} + {r}", f"{q} + {r}", f"abs({a}) // {b}", f"-{a} // {b}", f"{a} // -{b}"])
    out = [q, r]
    if extra and rng.random() < 0.6:
        z = nb.get(INT_NAMES)
        body.append(f"{z} = {extra}")
        out = rng.choice([[q, r, z], [z, q], [r, z]])
    elif rng.random() < 0.4:
        body = []
        out = [f"divmod({a}, {b})"]
    return spec([(a, av), (b, bv)], body, out)


_OPS = {"+": ast.Add(), "-": ast.Sub(), "*": ast.Mult(), "//": ast.FloorDiv(), "%": ast.Mod()}


def _expr(rng, leaves, depth):
    if depth == 0 or (depth < 3 and rng.random() < 0.25):
        leaf = rng.choice(leaves)
        return ast.Name(leaf, ast.Load()) if isinstance(leaf, str) else ast.Constant(leaf)
    op = rng.choice(["+", "-", "*", "//", "%", "+", "-", "*"])
    return ast.BinOp(_expr(rng, leaves, depth - 1), _OPS[op], _expr(rng, leaves, depth - 1))


def fam_precedence(rng, nb):
    vs = [nb.get(INT_NAMES) for _ in range(rng.randint(2, 3))]
    setup = [(v, rng.choice([rng.randint(-9, -1), rng.randint(2, 13), rng.randint(2, 13)])) for v in vs]
    leaves = vs + [rng.randint(2, 6), rng.randint(2, 9)]
    outs = []
    body = []
    for _ in range(rng.randint(1, 2)):
        nm = nb.get(INT_NAMES)
        e = ast.unparse(_expr(rng, leaves, rng.randint(2, 3)))
        if rng.random() < 0.25:
            e = f"-{rng.choice(vs)} ** 2 + {e}"
        body.append(f"{nm} = {e}")
        outs.append(nm)
    if len(outs) == 1 and rng.random() < 0.5:
        outs.append(rng.choice(vs))
    return spec(setup, body, outs)


def fam_slicing(rng, nb):
    s = nb.get(STR_NAMES + LIST_NAMES)
    if rng.random() < 0.55:
        val = _word(rng)
        while len(val) < 7:
            val += rng.choice(["-", "_", ""]) + rng.choice(WORDS)
        val = val[:14]
    else:
        val = _ints(rng, rng.randint(7, 10), 0, 30)
    L = len(val)
    forms = [f"{s}[{rng.randint(1, 3)}:{rng.randint(4, L - 1)}]", f"{s}[-{rng.randint(2, 4)}:]", f"{s}[:{rng.randint(2, 5)}]",
             f"{s}[::{rng.randint(2, 3)}]", f"{s}[{rng.randint(1, 2)}::{rng.randint(2, 3)}]",
             f"{s}[{rng.randint(1, 2)}:-{rng.randint(1, 2)}:{rng.randint(2, 3)}]", f"{s}[::-1]",
             f"{s}[-{rng.randint(2, 4)}::-1]", f"{s}[{rng.randint(5, L - 1)}:{rng.randint(1, 3)}:-1]"]
    picks = rng.sample(forms, rng.randint(2, 3))
    if rng.random() < 0.3:
        picks[-1] = rng.choice([f"{s}[{rng.randint(0, L - 1)}]", f"{s}[-{rng.randint(1, 3)}]"])
    names = [nb.get(STR_NAMES + LIST_NAMES) for _ in picks]
    body = [f"{n} = {p}" for n, p in zip(names, picks)]
    sliced = [n for n, p in zip(names, picks) if ":" in p]
    outs = [names[:2], names[-2:], [f"len({names[0]})", names[-1]]]
    if len(sliced) >= 2:
        outs.append([f"{sliced[0]} + {sliced[1]}"])
    return spec([(s, val)], body, rng.choice(outs))


def fam_recursion(rng, nb):
    g, n = nb.get(FUNC_NAMES), nb.get(("n", "k", "m", "num", "depth"))
    base_n, base_v = rng.randint(0, 2), rng.randint(0, 3)
    cmpop = rng.choice(["<=", "<", "=="]) if base_n > 0 else rng.choice(["<=", "=="])
    rec = rng.choice([f"{n} + {g}({n} - 2)", f"{n} * {g}({n} - 1)", f"{g}({n} - 1) + {g}({n} - 2)",
                      f"{g}({n} // 2) + {n} % 2", f"2 * {g}({n} - 1) - {rng.randint(1, 3)}", f"{n} % 3 + {g}({n} - 1) * 2",
                      f"{g}({n} - 1) + {n} * {n}", f"{g}({n} - 3) + {g}({n} - 1)"])
    if "2)" in rec and cmpop == "==":
        cmpop = "<="
    helpers = [f"def {g}({n}):", f"    if {n} {cmpop} {base_n}:", f"        return {base_v}", f"    return {rec}"]
    top = 7 if "*" in rec and "{g}" not in rec else rng.randint(4, 9)
    if f"{g}({n} - 1) + {g}({n} - 2)" in rec or f"{g}({n} - 3)" in rec:
        top = rng.randint(4, 8)
    if rec.startswith(f"{n} * "):
        top = rng.randint(3, 6)
    calls = [f"{g}({top})"] if rng.random() < 0.6 else [f"{g}({top})", f"{g}({rng.randint(base_n + 1, top)})"]
    return spec([], [], calls, helpers)


def fam_comprehension(rng, nb):
    nums, v = nb.get(LIST_NAMES), nb.get(ELEM_NAMES)
    a, b = nb.get(LIST_NAMES), nb.get(LIST_NAMES)
    vals = _ints(rng, rng.randint(5, 8), -6, 15)
    t = rng.randint(0, 8)
    c1 = rng.choice([f"[{v} * {v} for {v} in {nums} if {v} % 2 == 0]", f"[{v} + 1 for {v} in {nums} if {v} > {t}]",
                     f"[abs({v}) for {v} in {nums} if {v} < {t}]", f"[{v} // 2 for {v} in {nums} if not {v} % 3]",
                     f"[{v} * 2 + 1 for {v} in {nums} if {v} >= {t}]", f"[{v} ** 2 for {v} in {nums} if {v} % 2]"])
    c2 = rng.choice([f"[{v} for {v} in {nums} if {v} % 3 == 0]", f"[{v} for {v} in {nums} if {v} <= {t}]",
                     f"[{v} - {t} for {v} in {nums} if {v} != {t}]", f"[{v} for {v} in {nums}[1:] if {v} > 0]"])
    body = [f"{a} = {c1}", f"{b} = {c2}"]
    out = rng.choice([[a], [a, f"len({b})"], [f"sum({a})", f"len({b})"], [b, f"sum({a})"], [f"{a}[:3]", f"{b}[-1:]"]])
    return spec([(nums, vals)], body, out)


def fam_sorting(rng, nb):
    pairs, ranked, p = nb.get(LIST_NAMES), nb.get(LIST_NAMES), nb.get(("p", "pr", "t", "e"))
    ws = rng.sample(NOUNS, rng.randint(4, 6))
    vals = [(w, rng.randint(1, 5)) for w in ws]
    key = rng.choice([f"lambda {p}: {p}[1]", f"lambda {p}: ({p}[1], {p}[0])", f"lambda {p}: len({p}[0])",
                      f"lambda {p}: -{p}[1]", f"lambda {p}: {p}[0][-1]"])
    rev = rng.choice(["", ", reverse=True"])
    how = rng.choice(["sorted", "sort"])
    if how == "sorted":
        body = [f"{ranked} = sorted({pairs}, key={key}{rev})"]
    else:
        body = [f"{pairs}.sort(key={key}{rev})", f"{ranked} = {pairs}"]
    out = rng.choice([[f"[{p}[0] for {p} in {ranked}]"], [f"{ranked}[0]", f"{ranked}[-1]"], [f"{ranked}[:2]"],
                      [f"{pairs}[0]", f"{ranked}[0]"], [f"[{p}[0] for {p} in {ranked}][:3]", f"{ranked}[0][1]"]])
    return spec([(pairs, vals)], body, out)


def fam_nested(rng, nb):
    i, j, hits = nb.get(LOOP_NAMES), nb.get(LOOP_NAMES), nb.get(INT_NAMES)
    a, b = rng.randint(3, 6), rng.randint(4, 8)
    m, kk = rng.randint(3, 5), rng.randint(2, 5)
    cond = rng.choice([f"({i} + {j}) % {m} == 0", f"{i} * {j} % {m} == 1", f"{j} - {i} == {m - 2}", f"({i} * {j}) % {m} == 0"])
    jstart = rng.choice([f"{i}", "1", f"{i} + 1"])
    lines = [f"for {i} in range(1, {a}):", f"    for {j} in range({jstart}, {b}):", f"        if {cond}:",
             f"            {hits} += 1", f"            if {hits} == {kk}:", "                break",
             f"    if {hits} >= {kk}:", "        break"]
    if rng.random() < 0.35:
        lines[5] = "                continue" if rng.random() < 0.5 else lines[5]
    out = rng.choice([[i, j, hits], [hits, i], [i, j]])
    return spec([(hits, 0)], lines, out)


def fam_split_join(rng, nb):
    text, parts, clean = nb.get(STR_NAMES), nb.get(LIST_NAMES), nb.get(LIST_NAMES)
    ws = rng.sample(WORDS, rng.randint(3, 5))
    sepc = rng.choice([",", ";", "|", "/"])
    raw = sepc.join(w if rng.random() < 0.6 else rng.choice([" ", "  "]) + w if rng.random() < 0.5 else w + " " for w in ws)
    if rng.random() < 0.5:
        k = rng.randint(1, len(ws) - 1)
        raw = sepc.join(raw.split(sepc)[:k] + [""] + raw.split(sepc)[k:])
    body = [f"{parts} = {text}.split({sepc!r})"]
    body.append(rng.choice([f"{clean} = [{'x'}.strip() for {'x'} in {parts} if {'x'}.strip()]",
                            f"{clean} = [{'x'}.strip().upper() for {'x'} in {parts} if {'x'}]",
                            f"{clean} = [{'x'}.strip()[:3] for {'x'} in {parts} if len({'x'}) > 3]",
                            f"{clean} = [{'x'}.strip().title() for {'x'} in {parts} if {'x'}.strip()]"]))
    joiner = rng.choice(["-", "+", ":", ""])
    letter = rng.choice("aeiorst")
    out = rng.choice([[f"len({parts})", f"{joiner!r}.join({clean})"], [f"{joiner!r}.join({clean})"],
                      [f"len({clean})", f"{clean}[-1]"], [f"{text}.count({letter!r})", f"{text}.find({letter!r})"],
                      [f"{clean}[0]", f"len({parts}) - len({clean})"]])
    return spec([(text, raw)], body, out)


def fam_mutable_default(rng, nb):
    fn, item, bucket = nb.get(FUNC_NAMES), nb.get(("item", "v", "x", "entry")), nb.get(("bucket", "acc", "store", "box", "into"))
    ret = rng.choice([bucket, f"len({bucket})", f"sum({bucket})", f"{bucket}[:]"])
    helpers = [f"def {fn}({item}, {bucket}=[]):", f"    {bucket}.append({item})", f"    return {ret}"]
    names = [nb.get(INT_NAMES) for _ in range(3)]
    args = [rng.randint(1, 9) for _ in range(3)]
    fresh = rng.randrange(3)
    body = [f"{nm} = {fn}({ag}{', []' if k == fresh else ''})" for k, (nm, ag) in enumerate(zip(names, args))]
    out = rng.choice([names, names[1:], [names[0], names[2]]])
    return spec([], body, out, helpers)


def fam_tuple_update(rng, nb):
    a, b, it = nb.get(INT_NAMES), nb.get(INT_NAMES), nb.get(("_", "i", "k", "step_no"))
    upd = rng.choice([f"{a}, {b} = {b}, {a} + {b}", f"{a}, {b} = {b}, {a} * 2 - {b}", f"{a}, {b} = {a} + {b}, {a} - {b}",
                      f"{a}, {b} = {b} % 7, {a} + {b}", f"{a}, {b} = {b} + 1, {a} * 2"])
    n = rng.randint(3, 7)
    lines = [f"for {it} in range({n}):", f"    {upd}"]
    out = rng.choice([[a, b], [a], [b, a]])
    return spec([(a, rng.randint(0, 4)), (b, rng.randint(1, 5))], lines, out)


def fam_digits(rng, nb):
    n, total = nb.get(INT_NAMES), nb.get(INT_NAMES)
    val = rng.randint(100, 99999)
    upd = rng.choice([f"{total} += {n} % 10", f"{total} = {total} * 10 + {n} % 10", f"{total} += ({n} % 10) * ({n} % 10)",
                      f"{total} = {total} + 1 if {n} % 2 == 0 else {total}"])
    lines = [f"while {n} > 0:", f"    {upd}", f"    {n} //= 10"]
    if rng.random() < 0.4:
        lines = [f"while {n} > {rng.randint(9, 99)}:", f"    {upd}", f"    {n} //= 10"]
    out = rng.choice([[total], [total, n], [n, total]])
    return spec([(n, val), (total, 0)], lines, out)


def fam_best(rng, nb):
    names, scores = nb.get(LIST_NAMES), nb.get(LIST_NAMES)
    best, top, pos, nm, sc = nb.get(STR_NAMES), nb.get(INT_NAMES), nb.get(LOOP_NAMES), nb.get(("nm", "who", "label_")), nb.get(("sc", "pts", "val"))
    k = rng.randint(4, 6)
    ws = rng.sample(NOUNS, k + (1 if rng.random() < 0.3 else 0))
    vals = [rng.randint(1, 6) for _ in range(k)]
    start = rng.choice(["", ", 1"])
    cmpop = rng.choice([">", ">="])
    form = rng.choice([f"f\"{{{pos}}}:{{{nm}}}\"", nm, f"{nm}.upper()"])
    lines = [f"for {pos}, ({nm}, {sc}) in enumerate(zip({names}, {scores}){start}):", f"    if {sc} {cmpop} {top}:",
             f"        {top} = {sc}", f"        {best} = {form}"]
    out = rng.choice([[best, top], [best], [best, pos]])
    return spec([(names, ws), (scores, vals), (best, ""), (top, -1)], lines, out)


def fam_helpers(rng, nb):
    f1, f2 = nb.get(FUNC_NAMES), nb.get(FUNC_NAMES)
    v, k = nb.get(("v", "x", "num")), nb.get(("k", "factor", "by"))
    c = rng.randint(1, 4)
    kd = rng.randint(2, 4)
    e = rng.choice([f"{v} * {k} + {c}", f"{c} + {v} * {k}", f"{v} - {k} * {c}", f"({v} + {c}) * {k}", f"{v} * {k} // {c + 1}"])
    th = rng.randint(3, 12)
    helpers = [f"def {f1}({v}, {k}={kd}):", f"    return {e}", "", f"def {f2}({v}, {k}={th}):",
               f"    return {v} - {k} if {v} > {k} else {k} - {v}"]
    a, b, cc = nb.get(INT_NAMES), nb.get(INT_NAMES), nb.get(INT_NAMES)
    x = rng.randint(1, 9)
    body = [f"{a} = {f1}({x})", rng.choice([f"{b} = {f2}({a})", f"{b} = {f2}({a}, {rng.randint(5, 20)})"]),
            rng.choice([f"{cc} = {f1}({k}=1, {v}={b})", f"{cc} = {f1}({b}, {rng.randint(2, 3)})", f"{cc} = {f2}({f1}({b}))"])]
    out = rng.choice([[a, b, cc], [b, cc], [cc]])
    return spec([], body, out, helpers)


def fam_immutable(rng, nb):
    word, letters = nb.get(STR_NAMES), nb.get(LIST_NAMES)
    w = _word(rng)
    a, b = rng.choice(w), rng.choice("xyzo")
    body = [rng.choice([f"{word}.upper()", f"{word}.replace({a!r}, {b!r})", f"{word}.strip({w[0]!r})"]),
            f"{letters} = list({word})"]
    body.append(rng.choice([f"{letters}.reverse()", f"{letters}.sort()", f"{letters}.pop(0)", f"{letters}.append({b!r})"]))
    if rng.random() < 0.5:
        body.insert(1, rng.choice([f"{word} = {word}.replace({a!r}, {b!r})", f"{word} = {word}.capitalize()"]))
    out = rng.choice([[word, f"''.join({letters})"], [f"''.join({letters})"], [word, f"len({letters})"]])
    return spec([(word, w)], body, out)


FAMILIES = (fam_loop_acc, fam_while, fam_alias, fam_grid, fam_string_build, fam_index_string, fam_str_num,
            fam_dict_count, fam_floor_mod, fam_precedence, fam_slicing, fam_recursion, fam_comprehension, fam_sorting,
            fam_nested, fam_split_join, fam_mutable_default, fam_tuple_update, fam_digits, fam_best, fam_helpers,
            fam_immutable)


def assemble(sp: dict, mode: str, rng, nb) -> tuple[str, str | None]:
    """Program text for the spec: a top-level script ending in print(...) or a function stored in a variable."""
    lines = list(sp["helpers"])
    if lines:
        lines.append("")
    out = sp["out"]
    if mode == "print":
        lines += [f"{n} = {v!r}" for n, v in sp["setup"]] + sp["body"]
        args = ", ".join(out)
        if len(out) > 1 and sp["sep"] != " ":
            args += f", sep={sp['sep']!r}"
        lines.append(f"print({args})")
        return "\n".join(lines), None
    var = nb.get(RESULT_NAMES)
    if not sp["setup"] and not sp["body"] and len(out) == 1:
        lines.append(f"{var} = {out[0]}")
        return "\n".join(lines), var
    fn = nb.get(FUNC_NAMES)
    params = [n for n, _ in sp["setup"]]
    lines.append(f"def {fn}({', '.join(params)}):")
    lines += ["    " + ln if ln else "" for ln in sp["body"]]
    lines.append(f"    return {', '.join(out)}")
    lines += ["", f"{var} = {fn}({', '.join(repr(v) for _, v in sp['setup'])})"]
    return "\n".join(lines), var


# ------------------------------------------------------------------------------------------------- named mistakes

PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.FloorDiv: 2, ast.Mod: 2, ast.Div: 2, ast.Pow: 4}
STR_METHODS = ("upper", "lower", "strip", "title", "capitalize", "swapcase", "replace")


def _parents(tree):
    m = {}
    for p in ast.walk(tree):
        for field, val in ast.iter_fields(p):
            if isinstance(val, list):
                for i, c in enumerate(val):
                    if isinstance(c, ast.AST):
                        m[id(c)] = (p, field, i)
            elif isinstance(val, ast.AST):
                m[id(val)] = (p, field, None)
    return m


def _replace(parents, old, new):
    p, field, i = parents[id(old)]
    if i is None:
        setattr(p, field, new)
        return
    lst = getattr(p, field)
    if isinstance(new, list):
        lst[i:i + 1] = new
    else:
        lst[i] = new


def _plus(node, k):
    return ast.BinOp(node, ast.Add() if k > 0 else ast.Sub(), ast.Constant(abs(k)))


def _is_call(n, name):
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name


def _is_meth(n, names):
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in names


def _const_int(n):
    if isinstance(n, ast.Constant) and type(n.value) is int:
        return n.value
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant) \
            and type(n.operand.value) is int:
        return -n.operand.value
    return None


def _trunc(a, b):
    return ast.Call(ast.Name("int", ast.Load()), [ast.BinOp(a, ast.Div(), b)], [])


# Each mutator: (mistake name, site predicate, number of variants at a site, apply(node, variant, parents) -> None)

def _m_range(n, v, P):
    stop = 0 if len(n.args) == 1 else 1
    if v == 0:
        n.args[stop] = _plus(n.args[stop], 1)
    elif v == 1:
        n.args[stop] = _plus(n.args[stop], -1)
    else:
        n.args[0] = _plus(n.args[0], 1)


_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}


def _m_cmp(n, v, P):
    idx = [i for i, o in enumerate(n.ops) if type(o) in _CMP_SWAP][v]
    n.ops[idx] = _CMP_SWAP[type(n.ops[idx])]()


def _prec_site(n):
    if isinstance(n, ast.BinOp) and isinstance(n.right, ast.BinOp) and type(n.op) in PREC and type(n.right.op) in PREC:
        return PREC[type(n.right.op)] > PREC[type(n.op)]
    return isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.BinOp) \
        and isinstance(n.operand.op, ast.Pow)


def _m_prec(n, v, P):
    if isinstance(n, ast.UnaryOp):
        _replace(P, n, ast.BinOp(ast.UnaryOp(ast.USub(), n.operand.left), ast.Pow(), n.operand.right))
        return
    a, op1, b, op2, c = n.left, n.op, n.right.left, n.right.op, n.right.right
    n.left, n.op, n.right = ast.BinOp(a, op1, b), op2, c


def _m_floor_trunc(n, v, P):
    if isinstance(n, ast.AugAssign):
        _replace(P, n, ast.Assign([n.target], _trunc(ast.Name(n.target.id, ast.Load()), n.value)))
    else:
        _replace(P, n, _trunc(n.left, n.right))


def _m_mod_c(n, v, P):
    if isinstance(n, ast.AugAssign):
        a = ast.Name(n.target.id, ast.Load())
        _replace(P, n, ast.Assign([n.target], ast.BinOp(a, ast.Sub(), ast.BinOp(n.value, ast.Mult(), _trunc(copy.deepcopy(a), copy.deepcopy(n.value))))))
    else:
        _replace(P, n, ast.BinOp(n.left, ast.Sub(), ast.BinOp(n.right, ast.Mult(), _trunc(copy.deepcopy(n.left), copy.deepcopy(n.right)))))


def _is_copy(v):
    return (isinstance(v, ast.Subscript) and isinstance(v.value, ast.Name) and isinstance(v.slice, ast.Slice)
            and v.slice.lower is None and v.slice.upper is None and v.slice.step is None) \
        or (_is_call(v, "list") and len(v.args) == 1 and isinstance(v.args[0], ast.Name)) \
        or (_is_meth(v, ("copy",)) and isinstance(v.func.value, ast.Name) and not v.args)


def _alias_site(n):
    return isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
        and (_is_copy(n.value) or isinstance(n.value, ast.Name))


def _m_alias(n, v, P):
    val = n.value
    if isinstance(val, ast.Name):
        n.value = ast.Subscript(ast.Name(val.id, ast.Load()), ast.Slice(None, None, None), ast.Load())
    elif isinstance(val, ast.Subscript):
        n.value = val.value
    elif _is_call(val, "list"):
        n.value = val.args[0]
    else:
        n.value = val.func.value


def _m_aug(n, v, P):
    if isinstance(n, ast.AugAssign):
        _replace(P, n, ast.Assign([n.target], ast.BinOp(ast.Name(n.target.id, ast.Load()), n.op, n.value)))
    else:
        _replace(P, n, ast.AugAssign(ast.Name(n.targets[0].id, ast.Store()), ast.Add(), n.value.right))


def _aug_site(n):
    if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and isinstance(n.op, ast.Add):
        return True
    return isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
        and isinstance(n.value, ast.BinOp) and isinstance(n.value.op, ast.Add) and isinstance(n.value.left, ast.Name) \
        and n.value.left.id == n.targets[0].id and isinstance(n.value.right, ast.List)


def _m_append(n, v, P):
    n.func.attr = "extend" if n.func.attr == "append" else "append"


def _concat_site(n):
    if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and isinstance(n.op, ast.Add):
        return True
    if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
            and isinstance(n.value, ast.BinOp) and isinstance(n.value.op, ast.Add):
        t = n.targets[0].id
        return any(isinstance(s, ast.Name) and s.id == t for s in (n.value.left, n.value.right))
    return False


def _m_concat(n, v, P):
    if isinstance(n, ast.AugAssign):
        _replace(P, n, ast.Assign([n.target], ast.BinOp(n.value, ast.Add(), ast.Name(n.target.id, ast.Load()))))
    else:
        n.value.left, n.value.right = n.value.right, n.value.left


def _elif_site(n):
    return isinstance(n, ast.If) and len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If)


def _m_elif(n, v, P):
    inner = n.orelse[0]
    n.orelse = []
    _replace(P, n, [n, inner])


def _m_not(n, v, P):
    _replace(P, n, n.operand)


def _m_pass(n, v, P):
    _replace(P, n, ast.Pass())


def _loop_site(n):
    return isinstance(n, (ast.For, ast.While)) and len(n.body) >= 2 and not n.orelse


def _m_dedent(n, v, P):
    last = n.body.pop()
    _replace(P, n, [n, last])


def _m_powmul(n, v, P):
    n.op = ast.Mult() if isinstance(n.op, ast.Pow) else ast.Pow()


def _powmul_site(n):
    return isinstance(n, ast.BinOp) and (isinstance(n.op, ast.Pow) or (isinstance(n.op, ast.Mult) and _const_int(n.right) in (2, 3)))


def _m_modfloor(n, v, P):
    if isinstance(n, ast.AugAssign):
        n.op = ast.Mod() if isinstance(n.op, ast.FloorDiv) else ast.FloorDiv()
    else:
        n.op = ast.Mod() if isinstance(n.op, ast.FloorDiv) else ast.FloorDiv()


def _index_site(n):
    return isinstance(n, ast.Subscript) and not isinstance(n.slice, ast.Slice) and _const_int(n.slice) is not None


def _m_index(n, v, P):
    k = _const_int(n.slice)
    n.slice = ast.Constant(k - 1) if v == 0 else ast.Constant(k + 1)
    if isinstance(n.slice, ast.Constant) and n.slice.value < 0:
        n.slice = ast.UnaryOp(ast.USub(), ast.Constant(-n.slice.value))


def _slice_site(n):
    return isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice) and (n.slice.upper is not None or n.slice.lower is not None)


def _slice_variants(n):
    return (n.slice.upper is not None) + (n.slice.lower is not None)


def _m_slice(n, v, P):
    s = n.slice
    if s.upper is not None and v == 0:
        s.upper = _plus(s.upper, 1) if _const_int(s.upper) != -1 else ast.Constant(None)
    else:
        s.lower = _plus(s.lower, -1) if (_const_int(s.lower) or 0) > 0 else _plus(s.lower, 1)


def _enum_site(n):
    return _is_call(n, "enumerate") and len(n.args) in (1, 2)


def _m_enum(n, v, P):
    if len(n.args) == 2:
        n.args.pop()
    else:
        n.args.append(ast.Constant(1))


def _rev_site(n):
    if isinstance(n, ast.Call) and any(k.arg == "reverse" for k in n.keywords):
        return True
    if _is_call(n, "reversed") and len(n.args) == 1:
        return True
    return isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice) and _const_int(n.slice.step) == -1


def _m_rev(n, v, P):
    if isinstance(n, ast.Call) and n.keywords:
        n.keywords = [k for k in n.keywords if k.arg != "reverse"]
    elif isinstance(n, ast.Call):
        _replace(P, n, ast.Call(ast.Name("list", ast.Load()), [n.args[0]], []))
    else:
        n.slice.step = None


def _sorted_site(n):
    return isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
        and _is_call(n.value, "sorted") and isinstance(n.value.args[0], ast.Name)


def _m_sorted(n, v, P):
    src = n.value.args[0].id
    sort = ast.Expr(ast.Call(ast.Attribute(ast.Name(src, ast.Load()), "sort", ast.Load()), [], n.value.keywords))
    _replace(P, n, [sort, ast.Assign(n.targets, ast.Name(src, ast.Load()))])


def _tuple_site(n):
    return isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Tuple) \
        and isinstance(n.value, ast.Tuple) and len(n.value.elts) == len(n.targets[0].elts)


def _m_tuple(n, v, P):
    _replace(P, n, [ast.Assign([t], e) for t, e in zip(n.targets[0].elts, n.value.elts)])


def _strnum_site(n):
    if not isinstance(n, ast.BinOp):
        return False
    if isinstance(n.op, ast.Add) and (_is_call(n.left, "str") or _is_call(n.right, "str")):
        return True
    if isinstance(n.op, (ast.Add, ast.Mult)) and _is_call(n.left, "int"):
        return True
    return isinstance(n.op, ast.Mult) and isinstance(n.left, ast.Name) and _const_int(n.right) is None and isinstance(n.right, ast.Name)


def _m_strnum(n, v, P):
    S = lambda e: ast.Call(ast.Name("str", ast.Load()), [e], [])   # noqa: E731
    I = lambda e: ast.Call(ast.Name("int", ast.Load()), [e], [])   # noqa: E731
    if isinstance(n.op, ast.Add) and (_is_call(n.left, "str") or _is_call(n.right, "str")):
        l = n.left.args[0] if _is_call(n.left, "str") else I(n.left)
        r = n.right.args[0] if _is_call(n.right, "str") else I(n.right)
        _replace(P, n, S(ast.BinOp(l, ast.Add(), r)))          # numbers added instead of text joined
    elif _is_call(n.left, "int"):
        if isinstance(n.op, ast.Mult):
            n.left = n.left.args[0]                              # text repeated instead of a number multiplied
        else:
            _replace(P, n, I(ast.BinOp(n.left.args[0], ast.Add(), S(n.right))))
    else:
        n.left = I(n.left)                                       # text read as a number


def _default_site(n):
    return isinstance(n, ast.FunctionDef) and any(isinstance(d, ast.List) and not d.elts for d in n.args.defaults)


def _m_default(n, v, P):
    k = [i for i, d in enumerate(n.args.defaults) if isinstance(d, ast.List) and not d.elts][0]
    pname = n.args.args[len(n.args.args) - len(n.args.defaults) + k].arg
    n.args.defaults[k] = ast.Constant(None)
    guard = ast.If(ast.Compare(ast.Name(pname, ast.Load()), [ast.Is()], [ast.Constant(None)]),
                   [ast.Assign([ast.Name(pname, ast.Store())], ast.List([], ast.Load()))], [])
    n.body.insert(0, guard)


def _strinplace_site(n):
    return isinstance(n, ast.Expr) and _is_meth(n.value, STR_METHODS) and isinstance(n.value.func.value, ast.Name)


def _m_strinplace(n, v, P):
    _replace(P, n, ast.Assign([ast.Name(n.value.func.value.id, ast.Store())], n.value))


def _strignored_site(n):
    return _is_meth(n, STR_METHODS) and not isinstance(n.func.value, ast.Constant)


def _m_strignored(n, v, P):
    _replace(P, n, n.func.value)


def _filter_site(n):
    return isinstance(n, ast.comprehension) and n.ifs


def _m_filter(n, v, P):
    n.ifs = []


def _find_site(n):
    return _is_meth(n, ("find", "index"))


def _m_find(n, v, P):
    _replace(P, n, _plus(copy.deepcopy(n), 1))


def _rows_site(n):
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult) and isinstance(n.left, ast.List) and len(n.left.elts) == 1 \
            and isinstance(n.left.elts[0], (ast.List, ast.BinOp)):
        return isinstance(n.left.elts[0], ast.List) or isinstance(n.left.elts[0].left, ast.List)
    return isinstance(n, ast.ListComp) and len(n.generators) == 1 and isinstance(n.elt, ast.BinOp) \
        and isinstance(n.elt.left, ast.List) and _is_call(n.generators[0].iter, "range")


def _m_rows(n, v, P):
    if isinstance(n, ast.BinOp):
        _replace(P, n, ast.ListComp(n.left.elts[0], [ast.comprehension(ast.Name("_", ast.Store()),
                                                                        ast.Call(ast.Name("range", ast.Load()), [n.right], []), [], 0)]))
    else:
        _replace(P, n, ast.BinOp(ast.List([n.elt], ast.Load()), ast.Mult(), n.generators[0].iter.args[0]))


def _break_site(n):
    return isinstance(n, (ast.Break, ast.Continue))


MUTATORS = (
    ("off-by-one loop bound", lambda n: _is_call(n, "range") and 1 <= len(n.args) <= 3,
     lambda n: 2 + (len(n.args) >= 2), _m_range),
    ("boundary < vs <=", lambda n: isinstance(n, ast.Compare) and any(type(o) in _CMP_SWAP for o in n.ops),
     lambda n: sum(type(o) in _CMP_SWAP for o in n.ops), _m_cmp),
    ("operator precedence read left to right", _prec_site, lambda n: 1, _m_prec),
    ("truncating instead of floor division",
     lambda n: (isinstance(n, ast.BinOp) and isinstance(n.op, ast.FloorDiv))
     or (isinstance(n, ast.AugAssign) and isinstance(n.op, ast.FloorDiv) and isinstance(n.target, ast.Name)),
     lambda n: 1, _m_floor_trunc),
    ("C-style remainder", lambda n: (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod))
     or (isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Mod) and isinstance(n.target, ast.Name)),
     lambda n: 1, _m_mod_c),
    ("copy vs alias", _alias_site, lambda n: 1, _m_alias),
    ("+= vs rebinding", _aug_site, lambda n: 1, _m_aug),
    ("append vs extend", lambda n: _is_meth(n, ("append", "extend")) and len(n.args) == 1, lambda n: 1, _m_append),
    ("prepend vs append", _concat_site, lambda n: 1, _m_concat),
    ("elif read as a separate if", _elif_site, lambda n: 1, _m_elif),
    ("not ignored", lambda n: isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not), lambda n: 1, _m_not),
    ("break / continue ignored", _break_site, lambda n: 1, _m_pass),
    ("indentation misread", _loop_site, lambda n: 1, _m_dedent),
    ("** vs *", _powmul_site, lambda n: 1, _m_powmul),
    ("% vs //", lambda n: (isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, (ast.Mod, ast.FloorDiv))),
     lambda n: 1, _m_modfloor),
    ("index off by one", _index_site, lambda n: 2, _m_index),
    ("slice bound off by one", _slice_site, _slice_variants, _m_slice),
    ("enumerate start", _enum_site, lambda n: 1, _m_enum),
    ("reverse ignored", _rev_site, lambda n: 1, _m_rev),
    ("sorted() read as in-place", _sorted_site, lambda n: 1, _m_sorted),
    ("tuple assignment done one by one", _tuple_site, lambda n: 1, _m_tuple),
    ("string vs number", _strnum_site, lambda n: 1, _m_strnum),
    ("mutable default read as fresh", _default_site, lambda n: 1, _m_default),
    ("string method read as in-place", _strinplace_site, lambda n: 1, _m_strinplace),
    ("string method ignored", _strignored_site, lambda n: 1, _m_strignored),
    ("comprehension filter ignored", _filter_site, lambda n: 1, _m_filter),
    ("1-based position", _find_site, lambda n: 1, _m_find),
    ("row list copies vs aliases", _rows_site, lambda n: 1, _m_rows),
)


def mistake_sites(tree) -> list[tuple[int, int, int]]:
    """Every single mistake that applies to the tree as (mutator index, site index, variant), in a fixed order."""
    out = []
    for mi, (_name, pred, nvar, _apply) in enumerate(MUTATORS):
        sites = [n for n in ast.walk(tree) if pred(n)]
        for si, node in enumerate(sites):
            out += [(mi, si, v) for v in range(nvar(node))]
    return out


def apply_mistakes(tree, mistakes) -> ast.Module | None:
    """A copy of the tree with all the given mistakes applied (sites located before any change); None if they clash."""
    t2 = copy.deepcopy(tree)
    nodes = []
    for mi, si, _v in mistakes:
        pred = MUTATORS[mi][1]
        nodes.append([n for n in ast.walk(t2) if pred(n)][si])
    try:
        for node, (mi, _si, v) in zip(nodes, mistakes):
            MUTATORS[mi][3](node, v, _parents(t2))
        ast.fix_missing_locations(t2)
    except (IndexError, AttributeError, KeyError, TypeError):
        return None
    return t2


def mutants(tree) -> list[tuple[str, ast.Module]]:
    """Every single-mistake variant of the program tree, in a fixed order."""
    out = []
    for m in mistake_sites(tree):
        t2 = apply_mistakes(tree, [m])
        if t2 is not None:
            out.append((MUTATORS[m[0]][0], t2))
    return out


# --------------------------------------------------------------------------------------------------- near values

def _near(v, rng) -> list:
    if isinstance(v, bool):
        return [not v]
    if isinstance(v, int):
        out = [v + d for d in (1, -1, 2, -2, 3, -3, 4, -4)]
        if v:
            out.append(-v)
        return out
    if isinstance(v, str):
        out = [v.upper(), v.lower(), v.capitalize()]
        if len(v) > 1:
            out += [v[1:], v[:-1], v[1:] + v[0], v[-1] + v[:-1]]
            i = rng.randrange(len(v) - 1)
            out.append(v[:i] + v[i + 1] + v[i] + v[i + 2:])
        return out
    if isinstance(v, list):
        out = [v[:-1], v[1:], v + v[-1:], v[1:] + v[:1], v[-1:] + v[:-1]]
        if len(v) <= 3:
            out.append(v[::-1])
        try:
            out.append(sorted(v))
        except TypeError:
            pass
        for i in rng.sample(range(len(v)), min(3, len(v))):
            for e in _near(v[i], rng)[:4]:
                out.append(v[:i] + [e] + v[i + 1:])
        return out
    if isinstance(v, tuple):
        out = []
        if len(v) == 2 and v[0] != v[1]:
            out.append((v[1], v[0]))
        for i in range(len(v)):
            for e in _near(v[i], rng)[:6]:
                out.append(v[:i] + (e,) + v[i + 1:])
        return out
    if isinstance(v, dict):
        ks = list(v)
        out = []
        for k in ks:
            for e in _near(v[k], rng)[:3]:
                out.append({**v, k: e})
        if len(ks) > 1:
            out.append({k: v[k] for k in ks[:-1]})
            out.append({k: v[k] for k in ks[1:]})
            a, b = ks[0], ks[-1]
            if v[a] != v[b]:
                out.append({**v, a: v[b], b: v[a]})
            out.append({k: v[k] for k in reversed(ks)})
        return out
    return []


def _near_values(values: tuple, rng) -> list[tuple]:
    out = []
    for i in range(len(values)):
        for e in _near(values[i], rng):
            out.append(values[:i] + (e,) + values[i + 1:])
    return out


# ------------------------------------------------------------------------------------------------------- contract

K_DIMS = {2: 1, 3: 2, 4: 3, 5: 3, 6: 3, 7: 4, 8: 4, 9: 4, 10: 5}


def draw(rng):
    nb = Names(rng)
    fam = rng.choice(FAMILIES)
    sp = fam(rng, nb)
    mode = "value" if rng.random() < 0.45 else "print"
    if mode == "print" and len(sp["out"]) > 1 and rng.random() < 0.25:
        sp["sep"] = rng.choice([", ", " | ", " / ", "; "])
    code, var = assemble(sp, mode, rng, nb)
    if code.count("\n") + 1 > MAX_LINES:
        raise Retry("program too long")
    try:
        gold, gvals = execute(code, mode, var)
    except Abort as exc:
        raise Retry(f"gold program unusable: {exc}") from None
    gv = gvals[0] if mode == "value" else gvals
    if _has_float(gv) or not text_ok(gold, mode):
        raise Retry("gold output not in a fixed format")
    n_opt = rng.choices(N_OPTIONS, N_WEIGHTS)[0]
    seen = {gold}

    def usable(text, vals):
        if text in seen or not text_ok(text, mode):
            return False
        if mode == "value":
            return compatible(gv, vals[0])
        return len(vals) == len(gvals) and all(compatible(a, b) for a, b in zip(gvals, vals))

    def run(t):
        if t is None:
            return None
        try:
            return execute(t, mode, var)
        except Abort:
            return None

    tree = ast.parse(code)
    # 1. single mistakes that change the output, one per distinct output
    singles, outs = [], set()
    for m in mistake_sites(tree):
        r = run(apply_mistakes(tree, [m]))
        if r and usable(*r) and r[0] not in outs:
            outs.add(r[0])
            singles.append((m, r))
    if not singles:
        raise Retry("no distractor from a named mistake")
    rng.shuffle(singles)
    # 2. K independent mistakes; every non-empty combination of them is a candidate (the corners of a cube with the gold
    #    as one corner). Sampling corners uniformly keeps the gold from being the one option all others surround.
    dims = singles[:min(len(singles), K_DIMS[n_opt])]
    combos = []
    for size in range(1, len(dims) + 1):
        combos += [list(c) for c in _combinations(range(len(dims)), size)]
    rng.shuffle(combos)
    corners = []
    for c in combos:
        if len(c) == 1:
            r = dims[c[0]][1]
        else:
            r = run(apply_mistakes(tree, [dims[k][0] for k in c]))
        if r and usable(*r):
            seen.add(r[0])
            corners.append((r[0], " + ".join(MUTATORS[dims[k][0][0]][0] for k in c), r[1]))
    picked = corners[:n_opt - 1]
    for t, _, _ in corners[n_opt - 1:]:
        seen.discard(t)
    # 3a. a single integer: near values that move the gold to a random rank among the options where the mistakes allow
    #     it (mistakes tend to inflate numbers, which would make the largest option a safe one to rule out)
    g_int = gv if mode == "value" else (gvals[0] if len(gvals) == 1 else None)
    if type(g_int) is int and len(picked) < n_opt - 1:
        num = (lambda p: p[2][0])
        above = sum(num(p) > g_int for p in picked)
        free = n_opt - 1 - len(picked)
        want_above = min(max(rng.randrange(n_opt) - above, 0), free)
        sides = [1] * want_above + [-1] * (free - want_above)
        rng.shuffle(sides)
        for side in sides:
            for _ in range(40):
                same = [num(p) for p in picked if (num(p) - g_int) * side > 0]
                base = rng.choice(same) if same and rng.random() < 0.5 else g_int
                v = base + side * rng.randint(1, 4)
                text = fmt((v,), mode, sp["sep"])
                if usable(text, (v,)):
                    seen.add(text)
                    picked.append((text, "near value", (v,)))
                    break
    # 3b. near values for the slots still open, grown mostly from the distractors (growing them from the gold, the
    #     first option, would make it the most central one)
    tries = 0
    while len(picked) < n_opt - 1 and tries < 200:
        tries += 1
        base = rng.choice([p[2] for p in picked]) if picked and rng.random() < 0.8 else gvals
        near = _near_values(base, rng)
        if not near:
            continue
        vals = rng.choice(near)
        text = fmt(vals, mode, sp["sep"])
        if usable(text, vals):
            seen.add(text)
            picked.append((text, "near value", vals))
    if len(picked) < n_opt - 1:
        raise Retry("not enough distinct options")
    return {"family": fam.__name__[4:], "mode": mode, "code": code, "var": var, "sep": sp["sep"],
            "options": [gold] + [t for t, _, _ in picked], "origins": ["gold"] + [o for _, o, _ in picked]}


def _combinations(items, k):
    items = list(items)
    if k == 0:
        yield []
        return
    for i in range(len(items)):
        for rest in _combinations(items[i + 1:], k - 1):
            yield [items[i]] + rest


def solve(case):
    """Run the program in the restricted namespace; the gold is the index of the option equal to its output."""
    try:
        text, _ = execute(case["code"], case["mode"], case["var"])
    except Abort as exc:
        raise Retry(f"program unusable: {exc}") from None
    hits = [i for i, o in enumerate(case["options"]) if o == text]
    if len(hits) != 1:
        raise Retry("output not exactly once among the options")
    return [hits[0]]


INTROS_PRINT = (
    "Here is a short Python 3 program. It reads no input and uses no randomness.",
    "The Python 3 script below is run once, from top to bottom, in a standard interpreter.",
    "Trace the following Python 3 code by hand.",
    "A student runs this Python 3 program in a terminal.",
    "Consider this self-contained Python 3 program (no imports, no input).",
    "Read the Python 3 code below carefully and work out what it does.",
)
NOTES_PRINT = (
    "Each option shows a candidate for the single line it prints, without the trailing newline.",
    "The options are possible printed lines, exactly as the terminal would show them.",
    "Exactly one option matches what the print call writes, character for character.",
    "Options give the printed text verbatim (no trailing newline).",
    "Compare the options with the program's printed output, character for character.",
)
QUESTIONS_PRINT = (
    "What does the program print?",
    "Which option is the exact output of the program?",
    "What line appears on the screen when the program runs?",
    "Which option shows the text printed by the program?",
    "What is printed?",
)
INTROS_VALUE = (
    "Here is a short Python 3 program that defines a function and stores the result of a call to it.",
    "The Python 3 code below is executed once in a standard interpreter.",
    "Trace the following Python 3 code by hand; it reads no input and uses no randomness.",
    "Consider this self-contained Python 3 snippet (no imports, no input).",
    "A developer runs the Python 3 code below.",
    "Work through the Python 3 code below step by step.",
)
NOTES_VALUE = (
    "Each option is written as Python's repr() of a value.",
    "Options are shown in repr() form, so strings keep their quotes.",
    "Two values count as the same only if their repr() strings are identical.",
    "Every option is the repr() of a candidate value.",
    "The options are repr() strings of possible values.",
)
QUESTIONS_VALUE = (
    "What is the value of `{var}` after the code runs?",
    "Which option equals repr({var}) at the end?",
    "When the code finishes, what does `{var}` hold?",
    "Which option is the repr() of `{var}` once execution is complete?",
    "What value ends up in `{var}`?",
)


def render(case, rng):
    if case["mode"] == "print":
        intro, note, qq = rng.choice(INTROS_PRINT), rng.choice(NOTES_PRINT), rng.choice(QUESTIONS_PRINT)
    else:
        intro, note, qq = rng.choice(INTROS_VALUE), rng.choice(NOTES_VALUE), rng.choice(QUESTIONS_VALUE)
    text = f"{intro} {note}\n\n```python\n{case['code']}\n```\n\n{qq.format(var=case['var'])}"
    return [{"instructions": text, "options": list(case["options"])}]


# ------------------------------------------------------------------------------------------------- second solver

_CODE_RE = re.compile(r"```python\n(.*?)\n```", re.S)
_VAR_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`|repr\(([A-Za-z_][A-Za-z0-9_]*)\)")


def solve_text(q: dict) -> str:
    """Reads only the rendered question: the code block, run the same restricted way; print mode when the code calls
    print, otherwise the variable named in the question; the key of the option equal to the output."""
    text = q["instructions"]
    code = _CODE_RE.search(text).group(1)
    question = text.rsplit("\n\n", 1)[1]
    if re.search(r"\bprint\(", code):
        out, _ = execute(code, "print")
    else:
        m = _VAR_RE.search(question)
        out, _ = execute(code, "value", m.group(1) or m.group(2))
    keys = [k for k, v in q["criteria"].items() if v == out]
    if len(keys) != 1:
        raise ValueError(f"output {out!r} matches {len(keys)} options")
    return keys[0]
