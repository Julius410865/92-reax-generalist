"""chord_from_notes: solve() on every quality, enharmonic spellings and octave voicings, the draw invariants, and the
rendered text's second solver (DEV-GUIDELINES.md section 7)."""

from __future__ import annotations

import collections
import random

import pytest

from tools.gen import chord_from_notes as G
from tools.gen.base import make_row

ALL = list(G.QUALITY_ORDER)


def case(notes, spelling="mixed", vocab=None):
    vocab = list(vocab or ALL)
    names = G.SPELLINGS[spelling]
    return {"spelling": spelling, "vocab": vocab, "notes": [list(n) for n in notes],
            "options": [[names[pc], q] for pc in range(12) for q in vocab]}


def label(c):
    n, q = c["options"][G.solve(c)[0]]
    return f"{n}:{q}"


def close(root_name, octave, quality, spelling="mixed"):
    names = G.SPELLINGS[spelling]
    root = G.midi(root_name, octave)
    return [[names[m % 12], m // 12 - 1] for m in (root + i for i in G.INTERVALS[quality])]


# ----------------------------------------------------------------------------------------------------- solve()

@pytest.mark.parametrize("quality", ALL)
def test_every_quality_on_every_root_in_close_position(quality):
    for spelling in ("mixed", "sharps", "flats"):
        for pc, name in enumerate(G.SPELLINGS[spelling]):
            assert label(case(close(name, 2, quality, spelling), spelling)) == f"{name}:{quality}"


@pytest.mark.parametrize("notes,expected", [
    ([("E", 1), ("B", 2), ("G#", 3), ("E", 4)], "E:maj"),                       # open, doubled root (sharps)
    ([("C", 2), ("G", 2), ("Eb", 3), ("G", 4), ("C", 5)], "C:min"),
    ([("D", 1), ("Ab", 3), ("F", 4)], "D:dim"),
    ([("F", 2), ("A", 3), ("C#", 4), ("F", 5)], "F:aug"),
    ([("Eb", 2), ("Bb", 3), ("F", 4), ("Bb", 4)], "Eb:sus2"),
    ([("B", 1), ("F#", 2), ("E", 4), ("F#", 4)], "B:sus4"),
    ([("C", 1), ("Bb", 2), ("E", 3), ("G", 4), ("C", 5)], "C:7"),
    ([("Ab", 2), ("G", 3), ("C", 4), ("Eb", 5)], "Ab:maj7"),
    ([("E", 2), ("B", 2), ("D", 3), ("G", 4), ("B", 5)], "E:min7"),
    ([("G", 1), ("Bb", 2), ("C#", 3), ("E", 4)], "G:dim7"),
    ([("B", 1), ("A", 3), ("D", 4), ("F", 4), ("A", 4)], "B:hdim7"),
])
def test_spread_voicings_with_doublings(notes, expected):
    assert label(case(notes)) == expected


def test_same_chord_in_every_octave_and_doubling_gives_one_answer():
    for octave in (1, 2, 3):
        base = close("D", octave, "maj7")
        assert label(case(base)) == "D:maj7"
        assert label(case(base + [["F#", octave + 2], ["D", octave + 3]])) == "D:maj7"
    assert label(case([("D", 1), ("C#", 4), ("F#", 4), ("A", 5)])) == "D:maj7"


def test_the_root_is_the_lowest_note_across_the_octave_boundary():
    assert label(case([("B", 2), ("Eb", 3), ("F#", 3)])) == "B:maj"       # B2 lies below C3
    assert label(case([("B", 3), ("C", 3), ("E", 3), ("G", 3)])) == "C:maj7"   # list order does not matter
    assert label(case([("C", 4), ("D", 3), ("F#", 3), ("A", 3)])) == "D:7"


def test_enharmonic_spellings_name_the_same_chord():
    sharp = case([("C#", 3), ("F", 3), ("G#", 3)], "sharps")
    flat = case([("Db", 3), ("F", 3), ("Ab", 3)], "flats")
    assert G.solve(sharp) == G.solve(flat)
    assert (label(sharp), label(flat)) == ("C#:maj", "Db:maj")
    # the mixed spelling writes E# as F and Db as C# (one fixed name per pitch class)
    assert label(case([("F#", 2), ("Bb", 2), ("C#", 3), ("F", 3)])) == "F#:maj7"
    assert label(case([("Bb", 2), ("C#", 3), ("F", 3)])) == "Bb:min"
    assert label(case([("A#", 1), ("C#", 3), ("F", 3)], "sharps")) == "A#:min"
    assert label(case([("Gb", 2), ("Bb", 2), ("Db", 3), ("E", 3)], "flats")) == "Gb:7"


def test_rotations_and_symmetric_chords_follow_the_bass():
    assert label(case([("C", 3), ("D", 3), ("G", 3)])) == "C:sus2"
    assert label(case([("G", 2), ("C", 3), ("D", 3)])) == "G:sus4"
    assert label(case([("C", 2), ("Eb", 2), ("F#", 2), ("A", 2)])) == "C:dim7"
    assert label(case([("A", 2), ("C", 3), ("Eb", 3), ("F#", 3)])) == "A:dim7"
    assert label(case([("C", 2), ("E", 2), ("Ab", 2)])) == "C:aug"
    assert label(case([("E", 2), ("Ab", 2), ("C", 3)])) == "E:aug"
    assert label(case([("A", 2), ("C", 3), ("E", 3), ("G", 3)])) == "A:min7"
    assert label(case([("F#", 2), ("A", 2), ("C", 3), ("E", 3)])) == "F#:hdim7"


@pytest.mark.parametrize("notes,vocab", [
    ([("C", 2), ("E", 2)], None),                                   # two notes: no quality
    ([("C", 2), ("E", 2), ("G", 2), ("A", 2)], None),               # a sixth chord is not in the vocabulary
    ([("C", 2), ("E", 2), ("G", 2), ("D", 3)], None),               # add9
    ([("C", 2), ("E", 2), ("Ab", 2)], G.CORE),                      # aug outside this item's vocabulary
    ([("C", 2), ("Eb", 2), ("F#", 2), ("A", 2)], G.CORE),           # dim7 outside this item's vocabulary
])
def test_interval_sets_outside_the_vocabulary_raise(notes, vocab):
    with pytest.raises(ValueError):
        G.solve(case(notes, vocab=vocab))


def test_enharmonic_duplicate_options_and_a_doubled_bass_are_rejected():
    c = case(close("C#", 2, "maj"))
    c["options"].append(["Db", "maj"])
    with pytest.raises(ValueError):
        G.solve(c)
    with pytest.raises(ValueError):
        G.solve(case([("C", 2), ("C", 2), ("E", 2), ("G", 2)]))


# ----------------------------------------------------------------------------------------------- draw / options

def draws(n, tag="t"):
    out = []
    for i in range(n):
        rng = random.Random(f"{tag}|{i}")
        c = G.draw(rng)
        out.append((c, rng))
    return out


def test_draw_invariants():
    for c, _ in draws(600):
        names = G.SPELLINGS[c["spelling"]]
        ms = [G.midi(n, o) for n, o in c["notes"]]
        assert ms == sorted(ms) and len(set(ms)) == len(ms) and 3 <= len(ms) <= 7
        assert all(n in names for n, _ in c["notes"])
        assert ms[-1] <= G.MAX_MIDI and ms[-1] - ms[0] <= G.SPAN
        n, q = c["options"][G.solve(c)[0]]
        assert G.PC[n] == ms[0] % 12                                      # the lowest note is the root
        assert sorted({(m - ms[0]) % 12 for m in ms}) == list(G.INTERVALS[q])  # every chord tone, nothing else
        assert all(x in c["vocab"] for x in G.CORE)
        labs = [(G.PC[a], b) for a, b in c["options"]]
        assert len(labs) == len(set(labs)) == 12 * len(c["vocab"])        # the full label set, no chord twice
        assert all(a in names for a, _ in c["options"])
        assert all(r in labs for r in G.related(c["vocab"], G.PC[n], q))


def test_related_distractors_share_the_root_or_notes():
    rel = G.related(ALL, 0, "maj")                   # C E G
    assert (0, "maj") not in rel
    assert all((0, q) in rel for q in ALL if q != "maj")
    assert (9, "min") in rel and (4, "min") in rel   # A minor, E minor share two notes
    assert (1, "maj") in rel and (11, "maj") in rel  # the semitone neighbours
    opts = G.build_options("mixed", ALL, 0, "maj")
    assert opts[0] == ["C", "maj"] and len(opts) == 12 * len(ALL)
    assert len(G.build_options("mixed", ALL, 0, "maj", size=26)) == 26


def test_roots_and_qualities_are_spread():
    roots, quals = collections.Counter(), collections.Counter()
    for c, _ in draws(2400, "spread"):
        n, q = c["options"][G.solve(c)[0]]
        roots[G.PC[n]] += 1
        quals[q] += 1
    assert len(roots) == 12 and min(roots.values()) > 140
    assert set(quals) == set(ALL) and min(quals[q] for q in G.CORE) > 180


# ----------------------------------------------------------------------------------------------- render / solve_text

def test_second_solver_agrees_on_rendered_rows():
    for i, (c, rng) in enumerate(draws(800, "row")):
        answers = G.solve(c)
        row = make_row(G, "train", i, G.render(c, rng), answers, rng)
        q = row["questions"][0]
        assert "\n\n" not in q["instructions"]
        assert G.solve_text(q) == q["expected"]
        assert q["criteria"][q["expected"]] == "{}:{}".format(*c["options"][answers[0]])


def test_at_least_five_templates_and_every_legend_kind_are_used():
    assert len(G.TEMPLATES) >= 5 and len({t[0] for t in G.TEMPLATES}) == len(G.TEMPLATES)
    intros, kinds = collections.Counter(), collections.Counter()
    for c, rng in draws(700, "tpl"):
        text = G.render(c, rng)[0]["instructions"]
        hits = [i for i, t in enumerate(G.TEMPLATES) if t[0].split("{notes}")[0].format(inst=c["instrument"]) in text]
        assert len(hits) == 1
        intros[hits[0]] += 1
        kind = "formula" if "0-4-7" in text else "short" if any(s in text for s in G.SHORT_LEGENDS) else "glossary"
        kinds[kind] += 1
    assert set(intros) == set(range(len(G.TEMPLATES))) and min(intros.values()) > 50
    assert all(kinds[k] > 50 for k in ("formula", "glossary", "short"))


FLIPPED = {"C#": "Db", "Eb": "D#", "F#": "Gb", "Ab": "G#", "Bb": "A#"}


def _row(tag="bad"):
    """A mixed-spelling row with a black-key note above the bass."""
    for i in range(500):
        c, rng = draws(1, f"{tag}|{i}")[0]
        if c["spelling"] == "mixed" and any(n in FLIPPED for n, _ in c["notes"][1:]):
            return c, make_row(G, "train", 0, G.render(c, rng), G.solve(c), rng)["questions"][0]
    raise AssertionError("no suitable draw")


def test_second_solver_rejects_a_broken_text():
    c, q = _row()
    first = "{}{}".format(*c["notes"][0])
    # a note spelled against the stated rule
    n, o = next((n, o) for n, o in c["notes"][1:] if n in FLIPPED)
    with pytest.raises(ValueError):
        G.solve_text(dict(q, instructions=q["instructions"].replace(f"{n}{o}", f"{FLIPPED[n]}{o}", 1)))
    # notes no longer low to high
    with pytest.raises(ValueError):
        G.solve_text(dict(q, instructions=q["instructions"].replace(first, first[:-1] + "6", 1)))
    # an enharmonic duplicate among the options
    gold = q["criteria"][q["expected"]]
    dup = dict(q["criteria"])
    dup["ZZ"] = gold
    with pytest.raises(ValueError):
        G.solve_text(dict(q, criteria=dup))
