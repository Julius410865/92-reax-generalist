"""chord_from_notes: the notes of one chord (low to high, with octave numbers), the lowest note is the root -> root:quality.

Drawn per item:
* a quality vocabulary: the nine core qualities (maj, min, dim, sus2, sus4, 7, maj7, min7, hdim7), plus aug and / or dim7
  on some items. The vocabulary is drawn before the gold, so it says nothing about the gold;
* the root (12 pitch classes) and the gold quality (uniform over the vocabulary);
* a voicing: root in octave 1-3, the upper chord tones in close, open or spread position, 0-3 doubled notes, every chord
  tone present, the root always the lowest note (the text says so);
* a fixed enharmonic spelling, stated in the text and used for the notes and the labels alike: mixed (C# Eb F# Ab Bb),
  all sharps or all flats (one name per pitch class, whatever the key or the function of the note);
* 1-3 irrelevant performance details (meter, tempo, bar and beat, dynamics, ...) and the instrument.

Options: the item's full label set, every root of the spelling x every quality of the vocabulary (108, 120 or 132 labels;
the dev items carry the full 108-label list, and the trainer and the validator serve the gold plus 25 sampled labels per
draw). The list is built related-first (same root other qualities, chords sharing two or more pitch classes with the gold,
the semitone neighbours of the same quality) and then filled from the label set; there is one spelling per pitch class,
so no two options are the same chord (solve() rejects a list with an enharmonic duplicate).

The gold comes from solve(): the pitch-class set above the lowest note -> the quality with exactly that interval set.
solve_text() is a separate solver: it parses the stated spelling, the note list, the legend and the option labels of the
rendered question with its own tables and finds the one matching option.
"""

from __future__ import annotations

import re

from tools.gen.base import Retry

TASK = "chord_from_notes"
PART, AREA, GOLD, HALF, COMPONENT = "T", "arts", False, "hf", None

PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
      "A": 9, "A#": 10, "Bb": 10, "B": 11}
SPELLINGS = {
    "mixed": ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"),
    "sharps": ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"),
    "flats": ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"),
}
SPELLING_KIND = {"mixed": "a fixed mix of sharps and flats", "sharps": "always sharps", "flats": "always flats"}
INTERVALS = {   # semitones above the root
    "maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
    "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "dim7": (0, 3, 6, 9), "hdim7": (0, 3, 6, 10)}
QUALITY_ORDER = ("maj", "min", "dim", "aug", "sus2", "sus4", "7", "maj7", "min7", "dim7", "hdim7")
CORE = ("maj", "min", "dim", "sus2", "sus4", "7", "maj7", "min7", "hdim7")
P_EXTRA = 0.35          # chance that aug (and, independently, dim7) is in an item's vocabulary
ROOT_OCTAVES = (1, 2, 2, 2, 3)
MAX_MIDI = 91           # G6: the highest note of any voicing
SPAN = 40               # at most this many semitones between the root and the top note

DESC = {
    "maj": ("major triad", "major chord"),
    "min": ("minor triad", "minor chord"),
    "dim": ("diminished triad", "diminished chord"),
    "aug": ("augmented triad", "augmented chord"),
    "sus2": ("suspended second chord", "suspended chord with a second in place of the third"),
    "sus4": ("suspended fourth chord", "suspended chord with a fourth in place of the third"),
    "7": ("dominant seventh chord", "dominant seventh"),
    "maj7": ("major seventh chord", "major seventh"),
    "min7": ("minor seventh chord", "minor seventh"),
    "dim7": ("diminished seventh chord", "fully diminished seventh chord"),
    "hdim7": ("half-diminished seventh chord", "minor seventh flat five chord"),
}

INSTRUMENTS = ("piano", "string quartet", "brass quintet", "guitar trio", "pipe organ", "synthesizer", "vocal ensemble",
               "woodwind section", "harp", "jazz big band", "marimba", "stage piano")
DETAILS = (
    ("The passage is in {meter} time.", "meter"),
    ("The tempo is marked at {bpm} beats per minute.", "bpm"),
    ("This chord falls on beat {beat} of bar {bar}.", "beat"),
    ("The chord is held for {dur} beats.", "dur"),
    ("The dynamic marking at this point is {dyn}.", "dyn"),
    ("It is chord number {num} of the {section}.", "num"),
    ("The recording session took place in {year}.", "year"),
    ("The sound is released after {sec} seconds.", "sec"),
)

# (intro with the notes, root statement, question, note separator, joiner); every intro is distinct
TEMPLATES = (
    ("A {inst} sounds these notes together, listed from lowest to highest: {notes}.",
     "The chord's root is its lowest note.", "Which chord is sounding?", ", ", " "),
    ("Simultaneous pitches in one chord played by a {inst}, in ascending order: {notes}.",
     "Take the bottom pitch as the root.", "Name the chord as root:quality.", ", ", " "),
    ("Reading one vertical slice of a {inst} part from the bass upward gives {notes}.",
     "The bass note is the root.", "What chord do these notes spell?", "and", " "),
    ("Notes struck at the same moment by a {inst} (low to high): {notes}.",
     "The root is the lowest of them.", "Which option identifies the chord?", ", ", " "),
    ("Stacked from bottom to top, a {inst} holds the notes {notes}.",
     "Treat the lowest note as the chord root.", "Identify the chord.", ", ", " "),
    ("Chord heard from a {inst}\nNotes, lowest to highest: {notes}",
     "Root: the lowest note", "Question: what is the chord?", " ", "\n"),
    ("Instrument: {inst}\nSimultaneous notes (bass first): {notes}",
     "The bass note is the root of the chord.", "Which label names this chord?", ", ", "\n"),
)
RULES = (
    "Spelling: every black-key note is written as one of {names}, both in the note list and in the options; white keys "
    "keep their plain letter names.",
    "The five black keys always carry the names {names} ({kind}), whatever the key or the function of the note, and the "
    "option labels use the same names.",
    "Enharmonic rule for this question: black keys are spelled {names} only, in the notes and in the answer labels alike.",
    "Accidentals follow one fixed spelling throughout ({kind}): {names}.",
    "Note names never change with the harmony: the black keys are always {names}, and the labels follow the same rule.",
)
OCTAVE_NOTES = ("Octave numbers follow scientific pitch notation (middle C is in octave 4, and each octave number starts "
                "at C).", "Octave numbers count up at every C, with middle C in octave 4.")
NOTATION = ("Options are written root:quality.", "Each option gives the root, a colon and a quality code.",
            "Answer labels have the form root:quality.", "Labels read root:quality.")
SHORT_LEGENDS = (
    "Options are written root:quality using common chord-symbol abbreviations; a bare 7 means a dominant seventh chord.",
    "Each option names the root, then a colon, then the chord quality in standard shorthand.",
    "Labels take the form root:quality, with the usual abbreviations for the quality.",
    "Answer format: root:quality (standard chord shorthand; the suspended chords are sus2 and sus4).",
)


# ------------------------------------------------------------------------------------------------------------ draw

def midi(name: str, octave: int) -> int:
    """Scientific pitch notation: middle C (C4) is 60; the octave number goes up at every C."""
    return 12 * (octave + 1) + PC[name]


def pcs(root_pc: int, quality: str) -> list[int]:
    return [(root_pc + i) % 12 for i in INTERVALS[quality]]


def voicing(rng, root: int, ivs: tuple[int, ...]) -> list[int]:
    """MIDI numbers: the root, every upper chord tone once (close, open or spread), then 0-3 doublings; root lowest."""
    top = min(root + SPAN, MAX_MIDI)
    style = rng.choice(("close", "close", "open", "open", "spread"))
    notes = [root]
    for iv in ivs[1:]:
        k = 0 if style == "close" else rng.choice((0, 1, 1, 2)) if style == "open" else rng.choice((1, 2, 2, 3))
        while k > 0 and root + iv + 12 * k > top:
            k -= 1
        notes.append(root + iv + 12 * k)
    cands = sorted({root + iv + 12 * k for iv in ivs for k in range(4)} - set(notes))
    cands = [m for m in cands if root < m <= top]
    extra = rng.choice((0, 0, 1, 1, 2, 3))
    notes += rng.sample(cands, min(extra, len(cands)))
    return sorted(notes)


def related(vocab: list[str], root_pc: int, quality: str) -> list[tuple[int, str]]:
    """The distractors that share the root or notes with the gold, most related first (gold excluded)."""
    gold = set(pcs(root_pc, quality))
    labels = [(pc, q) for pc in range(12) for q in vocab]
    same_root = [(root_pc, q) for q in vocab if q != quality]
    shared = [lab for lab in labels if lab[0] != root_pc and len(gold & set(pcs(*lab))) >= 2]
    neighbours = [((root_pc + d) % 12, quality) for d in (1, -1)]
    out: list[tuple[int, str]] = []
    for lab in same_root + shared + neighbours:
        if lab not in out and lab != (root_pc, quality):
            out.append(lab)
    return out


def build_options(spelling: str, vocab: list[str], root_pc: int, quality: str, size: int | None = None) -> list[list]:
    """Gold, the related distractors, then the rest of the label set; ``size`` None keeps the full label set (dev format)."""
    labels = [(pc, q) for pc in range(12) for q in vocab]
    order = [(root_pc, quality)]
    for lab in related(vocab, root_pc, quality) + labels:
        if lab not in order:
            order.append(lab)
    names = SPELLINGS[spelling]
    return [[names[pc], q] for pc, q in order[:size or len(order)]]


def _detail(rng, kind: str) -> dict:
    if kind == "meter":
        return {"meter": rng.choice(("2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "12/8"))}
    if kind == "bpm":
        return {"bpm": rng.randint(52, 176)}
    if kind == "beat":
        return {"beat": rng.randint(1, 4), "bar": rng.randint(2, 96)}
    if kind == "dur":
        return {"dur": rng.choice((2, 3, 4, 6, 8))}
    if kind == "dyn":
        return {"dyn": rng.choice(("pianissimo", "mezzo-piano", "mezzo-forte", "forte", "fortissimo", "sforzando"))}
    if kind == "num":
        return {"num": rng.randint(2, 12), "section": rng.choice(("intro", "verse", "chorus", "bridge", "coda",
                                                                  "second verse", "final chorus"))}
    if kind == "year":
        return {"year": rng.randint(1958, 2025)}
    return {"sec": rng.choice(("1.5", "2", "2.5", "3", "4"))}


def draw(rng):
    r = rng.random()
    spelling = "mixed" if r < 0.6 else "sharps" if r < 0.8 else "flats"
    vocab = [q for q in QUALITY_ORDER if q in CORE or rng.random() < P_EXTRA]
    quality = rng.choice(vocab)
    root_pc = rng.randrange(12)
    root = 12 * (rng.choice(ROOT_OCTAVES) + 1) + root_pc
    names = SPELLINGS[spelling]
    notes = [[names[m % 12], m // 12 - 1] for m in voicing(rng, root, INTERVALS[quality])]
    if len({tuple(n) for n in notes}) != len(notes):
        raise Retry("a note twice")
    details = [tpl.format(**_detail(rng, kind)) for tpl, kind in rng.sample(list(DETAILS), rng.randint(1, 3))]
    return {"spelling": spelling, "vocab": vocab, "notes": notes, "options": build_options(spelling, vocab, root_pc, quality),
            "instrument": rng.choice(INSTRUMENTS), "details": details}


# ----------------------------------------------------------------------------------------------------------- solve

def chord_of(notes: list[list]) -> tuple[int, tuple[int, ...]]:
    """(root pitch class, interval set above the root) of [name, octave] notes; the root is the lowest note."""
    ms = [midi(n, o) for n, o in notes]
    root = min(ms)
    if ms.count(root) != 1:
        raise ValueError("the lowest note appears twice")
    return root % 12, tuple(sorted({(m - root) % 12 for m in ms}))


def solve(case):
    root_pc, ivs = chord_of(case["notes"])
    matches = [q for q in case["vocab"] if INTERVALS[q] == ivs]
    if len(matches) != 1:
        raise ValueError(f"interval set {ivs} is not exactly one quality of {case['vocab']}")
    labels = [(PC[n], q) for n, q in case["options"]]
    if len(set(labels)) != len(labels):
        raise ValueError("two options name the same chord (enharmonic duplicate)")
    hits = [i for i, lab in enumerate(labels) if lab == (root_pc, matches[0])]
    if len(hits) != 1:
        raise ValueError("the chord is not among the options")
    return [hits[0]]


# ---------------------------------------------------------------------------------------------------------- render

def _names_list(spelling: str) -> str:
    black = [SPELLINGS[spelling][pc] for pc in (1, 3, 6, 8, 10)]
    return ", ".join(black[:-1]) + " and " + black[-1]


def _legend(vocab: list[str], rng) -> str:
    codes = list(vocab)
    if rng.random() < 0.3:
        rng.shuffle(codes)
    mode = rng.random()
    if mode < 0.2:
        return rng.choice(SHORT_LEGENDS)
    notation = rng.choice(NOTATION)
    if mode < 0.4:
        f = {c: "-".join(str(i) for i in INTERVALS[c]) for c in codes}
        style = rng.randrange(3)
        if style == 0:
            return f"{notation} Quality codes with their chord tones in semitones above the root: " + \
                ", ".join(f"{c} {f[c]}" for c in codes) + "."
        if style == 1:
            return f"{notation} Semitone formulas, counted up from the root: " + "; ".join(f"{c} = {f[c]}" for c in codes) + "."
        return f"{notation} Chord tones of each quality, in semitones above the root: " + \
            "; ".join(f"{c}: {f[c]}" for c in codes) + "."
    d = {c: rng.choice(DESC[c]) for c in codes}
    style = rng.randrange(4)
    if style == 0:
        return f"{notation} Quality codes: " + ", ".join(f"{c} = {d[c]}" for c in codes) + "."
    if style == 1:
        return f"{notation} " + "; ".join(f"{c} stands for {'an' if d[c][0] in 'aeiou' else 'a'} {d[c]}" for c in codes) + "."
    if style == 2:
        return f"{notation} Quality codes used in the options:\n" + "\n".join(f"- {c}: {d[c]}." for c in codes)
    return f"{notation} The quality codes are " + ", ".join(f"{c} ({d[c]})" for c in codes) + "."


def render(case, rng):
    intro, root_stmt, question, sep, joiner = TEMPLATES[rng.randrange(len(TEMPLATES))]
    toks = [f"{n}{o}" for n, o in case["notes"]]
    notes = ", ".join(toks[:-1]) + " and " + toks[-1] if sep == "and" else sep.join(toks)
    body = [intro.format(inst=case["instrument"], notes=notes), root_stmt]
    for det in case["details"]:
        body.insert(rng.randint(0, len(body)), det)
    rule = rng.choice(RULES).format(names=_names_list(case["spelling"]), kind=SPELLING_KIND[case["spelling"]])
    if rng.random() < 0.35:
        rule += " " + rng.choice(OCTAVE_NOTES)
    tail = [rule, _legend(case["vocab"], rng)]
    if rng.random() < 0.4:
        tail.reverse()
    text = joiner.join(body + tail + [question])
    if "\n\n" in text:
        raise Retry("blank line in the text")
    return [{"instructions": text, "options": [f"{n}:{q}" for n, q in case["options"]]}]


# --------------------------------------------------------------------------------------------- second solver
# Reads only the rendered question (instructions and criteria), with its own note, spelling and quality tables.

_LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_TRIAD = {"maj": (4, 7), "min": (3, 7), "dim": (3, 6), "aug": (4, 8), "sus2": (2, 7), "sus4": (5, 7)}
_SEVENTH = {"maj": ("maj", 11), "min": ("min", 10), "dim": ("dim", 9), "hdim": ("dim", 10)}
_CODE = r"([a-z]+[0-9]?|[0-9]+)"
_GLOSSARY = (rf"(?<![\w-]){_CODE} = ([a-z][a-z -]*[a-z])(?=[,.;])",
             rf"(?<![\w-]){_CODE} stands for an? ([a-z][a-z -]*[a-z])(?=[,.;])",
             rf"(?m)^- {_CODE}: ([a-z][a-z -]*[a-z])\.",
             rf"(?<![\w-]){_CODE} \(([a-z][a-z -]*[a-z])\)")
_FORMULA = rf"(?<![\w-]){_CODE}(?: =|:)? (0(?:-[0-9]+)+)(?![\w-])"


def _txt_pc(name: str) -> int:
    return (_LETTER[name[0]] + {"": 0, "#": 1, "b": -1}[name[1:]]) % 12


def _txt_code(code: str) -> frozenset[int] | None:
    """A quality code's interval set, built from its triad and seventh."""
    if code in _TRIAD:
        return frozenset((0,) + _TRIAD[code])
    if code == "7":
        return frozenset((0,) + _TRIAD["maj"] + (10,))
    m = re.fullmatch(r"(maj|min|dim|hdim)7", code)
    if not m:
        return None
    base, seventh = _SEVENTH[m.group(1)]
    return frozenset((0,) + _TRIAD[base] + (seventh,))


def _txt_desc(desc: str) -> frozenset[int] | None:
    """A chord name in words -> its interval set."""
    d = desc.lower()
    if "suspended" in d:
        return frozenset((0, 5, 7)) if "fourth" in d else frozenset((0, 2, 7)) if "second" in d else None
    if "half-diminished" in d or "flat five" in d:
        return frozenset((0, 3, 6, 10))
    if "diminished" in d:
        return frozenset((0, 3, 6, 9)) if "seventh" in d else frozenset((0, 3, 6))
    if "augmented" in d:
        return frozenset((0, 4, 8))
    if "dominant" in d:
        return frozenset((0, 4, 7, 10))
    if "major" in d:
        return frozenset((0, 4, 7, 11)) if "seventh" in d else frozenset((0, 4, 7))
    if "minor" in d:
        return frozenset((0, 3, 7, 10)) if "seventh" in d else frozenset((0, 3, 7))
    return None


def solve_text(q: dict) -> str:
    text, crit = q["instructions"], q["criteria"]
    # spelling rule: the five black-key names stated without an octave number
    black = list(dict.fromkeys(re.findall(r"(?<![A-Za-z#])([A-G][#b])(?![#b\w])", text)))
    if len(black) != 5 or sorted(_txt_pc(b) for b in black) != [1, 3, 6, 8, 10]:
        raise ValueError(f"no complete spelling rule: {black}")
    spell = {_txt_pc(b): b for b in black} | {pc: n for n, pc in _LETTER.items()}
    # notes, as listed from low to high
    notes = re.findall(r"(?<![A-Za-z#])([A-G][#b]?)([0-9])(?![0-9])", text)
    if len(notes) < 3:
        raise ValueError("no note list")
    heights = []
    for name, octave in notes:
        if spell[_txt_pc(name)] != name:
            raise ValueError(f"{name} breaks the stated spelling")
        heights.append(12 * int(octave) + (_LETTER[name[0]] + {"": 0, "#": 1, "b": -1}[name[1:]]))
    if heights != sorted(heights) or len(set(heights)) != len(heights):
        raise ValueError("notes not strictly low to high")
    root = heights[0]
    ivs = frozenset((h - root) % 12 for h in heights)
    # options: root:code labels, spelled by the rule, no chord twice
    parsed = {}
    for key, label in crit.items():
        rname, _, code = str(label).partition(":")
        if spell.get(_txt_pc(rname)) != rname:
            raise ValueError(f"option {label} breaks the stated spelling")
        parsed[key] = (_txt_pc(rname), code)
    if len(set(parsed.values())) != len(parsed):
        raise ValueError("two options name the same chord")
    vocab = sorted({c for _, c in parsed.values()})
    # legend: semitone formulas, else a glossary in words, else the shorthand itself; each checked against the shorthand
    legend: dict[str, frozenset[int]] = {}
    for code, f in re.findall(_FORMULA, text):
        if code in vocab:
            legend[code] = frozenset(int(x) for x in f.split("-"))
    if not legend:
        for pat in _GLOSSARY:
            for code, desc in re.findall(pat, text):
                if code in vocab:
                    legend[code] = _txt_desc(desc)
    if legend and sorted(legend) != vocab:
        raise ValueError(f"the legend covers {sorted(legend)}, the options use {vocab}")
    meaning = {}
    for code in vocab:
        own = _txt_code(code)
        if code in legend and legend[code] != own:
            raise ValueError(f"legend meaning of {code} disagrees with the shorthand")
        meaning[code] = legend.get(code, own)
    found = [c for c in vocab if meaning[c] == ivs]
    if len(found) != 1:
        raise ValueError(f"interval set {sorted(ivs)} matches {found}")
    keys = [k for k, v in parsed.items() if v == (root % 12, found[0])]
    if len(keys) != 1:
        raise ValueError("the chord is not exactly one option")
    return keys[0]
