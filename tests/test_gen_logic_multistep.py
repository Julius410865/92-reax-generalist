"""logic_multistep: forward-chaining boundaries (step counts, contrapositives, side conditions, exceptions), exact
entailment, rule wording round trips and the second solver."""

from __future__ import annotations

import random

import pytest

from tools.gen import logic_multistep as G
from tools.gen.base import Retry, make_row

T, F = True, False


def L(p, s=True):
    return [p, s]


def clauses(*rules):
    return [c for r in rules for c in G.rule_clauses(r)]


# ------------------------------------------------------------------------------------------------ forward chaining

def test_modus_ponens_counts_one_round_per_step():
    cl = clauses({"kind": "imp", "a": L(0), "b": L(1)}, {"kind": "imp", "a": L(1), "b": L(2)}, {"kind": "imp", "a": L(2), "b": L(3, F)})
    k = G.forward(cl, [L(0)])
    assert k[1] == (T, 1) and k[2] == (T, 2) and k[3] == (F, 3)


def test_stopping_one_round_early_leaves_the_last_step_undecided():
    cl = clauses({"kind": "imp", "a": L(0), "b": L(1)}, {"kind": "imp", "a": L(1), "b": L(2)})
    assert 2 not in G.forward(cl, [L(0)], max_rounds=1) and G.forward(cl, [L(0)], max_rounds=2)[2] == (T, 2)


def test_modus_tollens_only_if_and_exclusion():
    assert G.forward(clauses({"kind": "imp", "a": L(0), "b": L(1)}), [L(1, F)])[0] == (F, 1)          # not b -> not a
    assert G.forward(clauses({"kind": "onlyif", "b": L(0), "a": L(1)}), [L(0)])[1] == (T, 1)          # b only if a
    assert G.forward(clauses({"kind": "onlyif", "b": L(0), "a": L(1)}), [L(1, F)])[0] == (F, 1)
    k = G.forward(clauses({"kind": "excl", "a": L(0), "b": L(1)}), [L(1)])
    assert k[0] == (F, 1)                                                                            # an exclusion reads both ways


def test_converse_is_not_valid():
    assert 0 not in G.forward(clauses({"kind": "imp", "a": L(0), "b": L(1)}), [L(1)])
    assert 1 not in G.forward(clauses({"kind": "imp", "a": L(0), "b": L(1)}), [L(0, F)])                # antecedent denied


def test_conjunction_needs_both_conditions():
    cl = clauses({"kind": "conj", "a": L(0), "c": L(1), "b": L(2)})
    assert G.forward(cl, [L(0), L(1)])[2] == (T, 1)
    assert 2 not in G.forward(cl, [L(0)])
    assert G.forward(cl, [L(0), L(2, F)])[1] == (F, 1)


def test_exception_flips_the_default():
    cl = clauses({"kind": "unless", "a": L(0), "c": L(1), "b": L(2)})
    assert G.forward(cl, [L(0), L(1, F)])[2] == (T, 1)
    assert G.forward(cl, [L(0), L(1)])[2] == (F, 1)
    assert 2 not in G.forward(cl, [L(0)])                                      # exception unknown: undecided


def test_contradictions_are_detected():
    with pytest.raises(G.Contradiction):
        G.forward(clauses({"kind": "imp", "a": L(0), "b": L(1)}), [L(0), L(1, F)])


def test_enumeration_is_exact_where_forward_chaining_is_not():
    cl = clauses({"kind": "imp", "a": L(0), "b": L(1)}, {"kind": "imp", "a": L(0, F), "b": L(1)})
    m = G.models(cl, [], [0, 1])
    assert G.entailed(m, L(1)) and not G.entailed(m, L(0)) and 1 not in G.forward(cl, [])
    assert not G.models(cl, [L(1, F)], [0, 1])["ms"]


# ---------------------------------------------------------------------------------------------------------- solve

def base_case(kind, **kw):
    rules = [{"kind": "imp", "a": L(0), "b": L(1)}, {"kind": "onlyif", "b": L(1), "a": L(2, F)},
             {"kind": "excl", "a": L(3), "b": L(4)}]
    c = {"theme": 0, "preds": [0, 1, 2, 3, 4], "rules": rules, "depth": 2, "kind": kind,
         "entities": [{"name": "Biscuit", "facts": [L(0)]}, {"name": "Clover", "facts": [L(1, F)]}, {"name": "Mocha", "facts": [L(3)]}]}
    c.update(kw)
    return c


def test_solve_yes_no_and_true_false():
    assert G.solve(base_case("yesno", entity=0, asked=L(2, F))) == [True]
    assert G.solve(base_case("yesno", entity=0, asked=L(2))) == [False]
    assert G.solve(base_case("tf", entity=0, asked=L(2), options=["True", "False"])) == [1]
    with pytest.raises(Retry):
        G.solve(base_case("yesno", entity=1, asked=L(2)))                       # not decided for Clover


def test_solve_which_entity_and_which_statement():
    assert G.solve(base_case("who", target=L(2, F), options=["Clover", "Mocha", "Biscuit"])) == [2]
    assert G.solve(base_case("what", entity=0, options=[L(3), L(2, F), L(4)])) == [1]
    with pytest.raises(Retry):
        G.solve(base_case("what", entity=0, options=[L(1), L(2, F)]))           # two statements derived


# -------------------------------------------------------------------------------------------- wording round trips

@pytest.mark.parametrize("theme", range(len(G.THEMES)))
def test_every_rule_template_parses_back_to_its_clauses(theme):
    rng = random.Random(f"rt|{theme}")
    rules = [{"kind": "imp", "a": L(0, F), "b": L(1)}, {"kind": "onlyif", "b": L(2), "a": L(3, F)},
             {"kind": "excl", "a": L(4), "b": L(5)}, {"kind": "conj", "a": L(6), "c": L(7, F), "b": L(8)},
             {"kind": "unless", "a": L(9), "c": L(10), "b": L(0, F)}]
    for r in rules:
        for _ in range(12):
            text = G._render_rule(rng, theme, r)
            got = G._parse_rule(text)
            want = [[(G.THEMES[theme]["preds"][p][0], s) for p, s in c] for c in G.rule_clauses(r)]
            assert got is not None, text
            assert sorted(map(sorted, got)) == sorted(map(sorted, want)), text


def test_no_phrase_is_ambiguous():
    phrases = [p for th in G.THEMES for pair in th["preds"] for p in pair]
    assert len(phrases) == len(set(phrases))
    assert all(" and " not in p and "." not in p for p in phrases)


# --------------------------------------------------------------------------------------------------- end to end

def rows(n=300, seed="t"):
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


def test_second_solver_agrees_depth_and_balance():
    rs = rows()
    assert len(rs) == 300
    yes = total = 0
    for c, r in rs:
        q = r["questions"][0]
        assert G.solve_text(q) == q["expected"]
        assert 2 <= c["depth"] <= 5 and 3 <= len(c["rules"]) <= 8
        assert 2 <= len(q["criteria"]) <= 7
        if list(q["criteria"]) == ["yes", "no"]:
            yes += q["expected"] == "yes"
            total += 1
    assert 0.40 <= yes / total <= 0.60


def test_draws_are_deterministic():
    a = [r["questions"][0]["instructions"] for _, r in rows(30, "d")]
    b = [r["questions"][0]["instructions"] for _, r in rows(30, "d")]
    assert a == b
