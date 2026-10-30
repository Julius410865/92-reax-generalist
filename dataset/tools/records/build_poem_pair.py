"""poem_pair (arts, T): two versions of four lines of rhyming verse; in one, the last word of line 4 was swapped for a
non-rhyming word from the same book. Which version is the original?

    python -I tools/records/build_poem_pair.py

Source: a fixed list of Project Gutenberg poetry collections (public domain in the USA), fetched once from
https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt (2 s between downloads) into data/generalist/raw/poem_pair/ and
pinned by sha256. The Gutenberg header, footer and licence are cut off (text between the "*** START OF" and
"*** END OF" lines only); titles, headings, notes, footnotes and line numbers never pass the verse-window filter.

Split by ebook (group = book), so select and test come from poets never seen in train; ``source_id`` = ebook id + poem
index for tracing. All randomness from ``common.rng``; output is byte-identical on every run.
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.records import common as C  # noqa: E402

TASK = "poem_pair"
VERSION = "poem_pair-1"
TRAIN_TARGET = 1500
TRAIN_PER_BOOK = 80
HELD_PER_BOOK = 50          # select / test: at most this many per book, so each split spans at least 3 books
SELECT_SHARE = 0.13
TEST_SHARE = 0.13
LICENCE = "Public domain in the USA (Project Gutenberg texts, header/licence stripped)"
LICENCE_URL = "https://www.gutenberg.org/policy/license.html"

# ebook id -> (title, author); every one a collection of (mostly) rhyming verse, published before 1928.
BOOKS: dict[int, tuple[str, str]] = {
    13: ("The Hunting of the Snark", "Lewis Carroll"),
    136: ("A Child's Garden of Verses", "Robert Louis Stevenson"),
    151: ("The Rime of the Ancient Mariner", "Samuel Taylor Coleridge"),
    207: ("The Spell of the Yukon and Other Verses", "Robert W. Service"),
    213: ("The Man from Snowy River", "A. B. Paterson"),
    214: ("In the Days When the World Was Wide, and Other Verses", "Henry Lawson"),
    246: ("The Rubaiyat of Omar Khayyam", "Edward FitzGerald (tr.)"),
    262: ("The Collected Poems of Rupert Brooke", "Rupert Brooke"),
    263: ("Trees, and Other Poems", "Joyce Kilmer"),
    301: ("The Ballad of Reading Gaol", "Oscar Wilde"),
    353: ("In Flanders Fields, and Other Poems", "John McCrae"),
    596: ("Rivers to the Sea", "Sara Teasdale"),
    931: ("The Bab Ballads", "W. S. Gilbert"),
    941: ("Just Folks", "Edgar A. Guest"),
    1021: ("The Congo, and Other Poems", "Vachel Lindsay"),
    1034: ("Poems", "Wilfred Owen"),
    1041: ("Shakespeare's Sonnets", "William Shakespeare"),
    1279: ("Poems and Songs of Robert Burns", "Robert Burns"),
    1365: ("The Complete Poetical Works of Henry Wadsworth Longfellow", "Henry Wadsworth Longfellow"),
    1469: ("Poems", "Francis Thompson"),
    1568: ("Poems", "William Ernest Henley"),
    1746: ("New Collected Rhymes", "Andrew Lang"),
    1934: ("Songs of Innocence and of Experience", "William Blake"),
    2819: ("Barrack-room Ballads", "Rudyard Kipling"),
    3011: ("The Lady of the Lake", "Walter Scott"),
    3167: ("Wessex Poems and Other Verses", "Thomas Hardy"),
    4798: ("The Complete Poetical Works of Percy Bysshe Shelley, Volume 2", "Percy Bysshe Shelley"),
    5720: ("A Shropshire Lad", "A. E. Housman"),
    7388: ("The Poetical Works of Oliver Wendell Holmes, Volume 01: Earlier Poems", "Oliver Wendell Holmes"),
    8209: ("Poems 1817", "John Keats"),
    8601: ("The Early Poems of Alfred Lord Tennyson", "Alfred Tennyson"),
    8930: ("Counter-Attack and Other Poems", "Siegfried Sassoon"),
    9567: ("Narrative and Legendary Poems, Complete (Works of Whittier, Volume I)", "John Greenleaf Whittier"),
    9889: ("Songs and Other Verse", "Eugene Field"),
    12242: ("Poems by Emily Dickinson, Three Series, Complete", "Emily Dickinson"),
    13310: ("The Complete Poetical Works of James Russell Lowell", "James Russell Lowell"),
    13647: ("Nonsense Songs", "Edward Lear"),
    15079: ("Green Fields and Running Brooks, and Other Poems", "James Whitcomb Riley"),
    15652: ("The Poetical Works of Thomas Hood", "Thomas Hood"),
    16341: ("Poems by William Cullen Bryant", "William Cullen Bryant"),
    16776: ("Poems of Passion", "Ella Wheeler Wilcox"),
    16950: ("Goblin Market, The Prince's Progress, and Other Poems", "Christina Rossetti"),
    18338: ("The Complete Poems of Paul Laurence Dunbar", "Paul Laurence Dunbar"),
    21029: ("The New Morning: Poems", "Alfred Noyes"),
    21700: ("Don Juan", "Lord Byron"),
    35402: ("Poems & Ballads (First Series)", "Algernon Charles Swinburne"),
    50852: ("The Bells, and Other Poems", "Edgar Allan Poe"),
    52761: ("Salt-Water Ballads", "John Masefield"),
}
# sha256 of each raw file as downloaded on 2026-10-27; a changed upstream file is refused (common.fetch).
PINNED: dict[int, str] = {
    13: "30d6d0a4fa246393ba85df5fa4fb3d0358bdf3f4784a8d0ebb96547275bc4f74",
    136: "0684e08feb0fc8df5206ca899ba66937bef011bec11ac8e829fa3a8bea0e94bf",
    151: "97b2a12f1ae2c7724680bcfe584a3328eb87f908dc68c3e23ecf52b790772ee4",
    207: "0723ce9010b7df6078bb850c4193b588769891d3d5faf2b11368934954c9eb6d",
    213: "80d20cb5b84daed17d10c4f4e6ca8cefb17f715e71514511fd773cddb6402f64",
    214: "dae08e7ad618b825884eefba2f07c75d175a2f4c8817612e855931350a7f2489",
    246: "711166b8e22f048a2fc79599d5db3520f78120f42b2473a431df07863ce769b0",
    262: "a5dd99336f11127c381fbfbfffbcc0c1b759b53ccacfbb0ee459a5c1caa82ce2",
    263: "4b459d41c46c4a50c10bd35623a0791e5accb1835074cf024956b596983a04d5",
    301: "4f7cd480ced9757e3e72869a63d9a979bbb45cb77280d74a739dbd2818dcdb1e",
    353: "0950230ce9e511bca99fa37882cd4f20d2973f953f69c98d6dc67cb0f29ab27a",
    596: "d7315354c96c7058e8c0c97de0bed2ba06e2464af83bb54678f7c2d5e1f9cc13",
    931: "3c9fac90425cd8c9b4e6a31c5d4f7adae9e90d516ff5f1926abe866557c4d20e",
    941: "a26dc0126b97e6e5fede69ac7f2c7f8da555c3da44bef365d3362ff49a222006",
    1021: "8d00dd3ce69ee0d18ed9db308cd7a1ba53283ed5546ec09fdfe80e79fb667fba",
    1034: "b7a3deee488c381262d4db0e7fcf23228d20d38c9d5da3a971d90d31cdabcbb6",
    1041: "4a3a5466591e30ca93b2c19daeb24770bb08833b57b1616c972b97246e23580f",
    1279: "b4f506d4460a78d61434d3fca7b4fba48a1c0795f9fefd23454ed14ee21aa65c",
    1365: "9889340fd77d801429306af64a272646b0cbaaf259e4bc9089f5ca691856e641",
    1469: "470086e07432cbe353b8f6195d5e2cc74a3a5e71c3a01d2ae6903fb19d3a4c58",
    1568: "dd312f8be16a82f073e06a5a2b34b8a4b22cf6802d0fc141024f420bce242e32",
    1746: "9240f35c2d57c17b5c94a4d66044d157c4d748896f28992ba99da90fd3e2ae6f",
    1934: "a5b76d4de22f42e1bf40f08256a329728f4cb7ad18d6581709aa7a9683c5e455",
    2819: "e2de55400491f7b2a42901ddd8d9448505d2c4537b0a75cb907d939deca54488",
    3011: "11c3cd3a803278bf9b78115043dff2f064a984448f19ba14c53a72fdb556caaf",
    3167: "796536a9c21535b87c6266f95cb46d0ebae4310ea2627b21081491f080e17d65",
    4798: "095062184d815c8b49598a525f121a7d8975801ca27fef69fc50de12fa55f749",
    5720: "4cb77143d17f6cfcd845fe4575ac1bb83905c2471f259f0ebd8b8e03f7681f53",
    7388: "19b1e29a3a66e0b17e1a61808ecb9f0b799fa33f94d674c2ec9a0150ad32d7b1",
    8209: "dda508030b2098d8f77edec7d96124f7874ca6587f3790dddf7cb8fbc9514876",
    8601: "71906f15b2cf2fa6ab7c2221de6f1323b3f1e202e1c09610dc5c266f9890a9c4",
    8930: "fa630355c70e86b12568a61a452fa08c1790db0a5c1b1adbabd5ef3d7ef10b59",
    9567: "b67d1968fa7f9db62b12614908f722a84469e3b6f7aa187b88f33cf8dc19613d",
    9889: "0e80eaaceacac37292ff8c3b5b9bca37776f2a8eca16036e76f606627846c620",
    12242: "f4421418353de2737c9bfe3db1e4657534b6b8ae2a8603f31de2d77678d18791",
    13310: "a85046996f4b25be896a8eac1d43330a9b1141af8543b233d2b8e026472add74",
    13647: "fa8bd7e37e362fc608c5daf83703ee9a248ecc4006a6654e2fcbd91166843e3a",
    15079: "8dd4a9c41d6f5d72e7bfd0ae9b6ced89cb90c5689d85207f3fe2315972c72e6b",
    15652: "d07da79629316f04dae1097f479716f6bf70a1334f1da9f0ae0503c9572137a2",
    16341: "a999e2f97f954404ff254048e40d67ca5f21a36c3d8fa0b94ea57d73132e28c7",
    16776: "11effd01598bf7a33a91ca961495bdd52e06c954595344db9b0c844dc19eef0f",
    16950: "9c218814d72367d42f6e2f3b94507ed869b34d5d25f78fc461435b5ebe45949e",
    18338: "0e97ad6cd6ea5775b96446a531e2b097116b4c7e2b7b313e45f31bfed9055a6c",
    21029: "c789e909cdecb623fa6dedb83af90998a6aa38d901b7f5293256fcd9d4241916",
    21700: "b47f24d980e964d42406544becbcba0e424d12c25d36e8243589347a5965243b",
    35402: "285fc048e1d0f2365e1862348e1adbd2308f663234e1df511fd0a7aa326ccef9",
    50852: "65688b75504252ddb7cad660d544f7a847744693a7b3907bf905de8ae7aa3bf3",
    52761: "21ef6a62a357182549ae0398e2092fe129d2ad7e5d3f0c099dc5c0283ce8d8d9",
}

TEMPLATES = [
    "Two copies of a four-line passage of verse follow. They match except for the final word of the closing line: one "
    "copy keeps the poet's word, the other has a substitute that spoils the rhyme. Which copy is the poet's own?",
    "These four lines of poetry are given twice. In one copy somebody swapped out the very last word, so the fourth line "
    "no longer rhymes as it should. Pick the copy that is unaltered.",
    "A short stanza appears in two forms. The forms are the same apart from how the fourth line ends; only one of them "
    "preserves the rhyme the poet wrote. Which form is authentic?",
    "Compare the two renderings of this quatrain. One ending of the fourth line is genuine; the other was exchanged for "
    "a word that does not rhyme. Select the genuine rendering.",
    "Each option below holds the same four verse lines, except that the closing word of the last line differs. One of "
    "them was tampered with and lost its rhyme. Which option reproduces the poem faithfully?",
    "Read both texts. A single word, the final one of the stanza, was changed in one of them, breaking the rhyme scheme. "
    "Identify the text that is the untouched original.",
]
LABELS = [("Text 1:", "Text 2:"), ("Copy 1:", "Copy 2:"), ("Rendering 1:", "Rendering 2:"),
          ("Excerpt 1:", "Excerpt 2:"), ("Form 1:", "Form 2:"), ("Passage 1:", "Passage 2:")]
TEMPLATE_WORDS = {w for t in TEMPLATES for w in re.findall(r"[a-z]+", t.lower())} | {
    w for p in LABELS for s in p for w in re.findall(r"[a-z]+", s.lower())}
STOP = set("""the and but for nor yet with from into onto upon over under about above below than then that this these
those there their they them what when where which while whom whose will would shall should could have has had been being
are was were not you your yours his her hers its our ours who how why all any each both some such only own same very can
just now too also out off again once here thee thou thy thine doth hath unto mine must may might let ere till every much
many more most less like well else even ever never still though through without within among around along across behind
beyond before after against between toward towards since until because whether either neither none nought naught aught
myself himself herself itself ourselves themselves yourself thyself whence thence hence thus quite rather did does done
shalt wilt canst couldst wouldst art wert hast dost one two three four five six seven eight nine ten""".split())
DET = set("the a an my his her their our your its thy thine this that these those each every no some any".split())
AUX = set("to will shall would could can may might must should did do does not wilt shalt".split())
# unstressed endings: a rhyme on one of these must also agree on the syllable before it ('slumbered' / 'numbered')
WEAK = {"er", "ed", "es", "en", "el", "ing", "ess", "est", "eth", "ly", "y", "ow"}
VOWELS = "aeiouy"
FIRST_LETTER = re.compile(r"[A-Za-z]")
LAST_WORD = re.compile(r"(?<![A-Za-z'’\-])([A-Za-z]+)([^A-Za-z]*)$")
WORD = re.compile(r"(?<![A-Za-z'’\-])([A-Za-z]+)(?![A-Za-z'’\-])")
BAD_LINE = re.compile(r"[\[\]{}<>|*#@=+\\/0-9]|https?:|gutenberg|ebook|chapter|footnote|canto|stanza|illustration", re.I)


# ------------------------------------------------------------------------------------------------------- download

def fetch_all() -> list[dict]:
    entries = []
    for book in sorted(BOOKS):
        name = f"pg{book}.txt"
        url = f"https://www.gutenberg.org/cache/epub/{book}/pg{book}.txt"
        new = not (C.RAW / TASK / name).exists()
        C.fetch(TASK, url, name, PINNED.get(book))
        if new:
            time.sleep(2.0)
        entries.append({"name": name, "url": url})
    return entries


def body(path: Path) -> list[str]:
    """The ebook text between the START and END markers, with Gutenberg's header, footer and licence removed."""
    text = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.lstrip().startswith("*** START OF")), None)
    end = next((i for i, l in enumerate(lines) if l.lstrip().startswith("*** END OF")), None)
    if start is None or end is None or end <= start:
        raise SystemExit(f"{path}: no Gutenberg START/END markers")
    return lines[start + 1:end]


# ---------------------------------------------------------------------------------------------------------- rhyme

def rhyme_key(word: str) -> str:
    """Final vowel group plus the consonants after it ('storm' -> 'orm', 'night' -> 'ight'); a silent final e keeps
    the syllable before it ('shade' -> 'ade')."""
    w = word.lower()
    tail = ""
    if len(w) > 2 and w.endswith("e") and w[-2] not in VOWELS:
        tail, w = "e", w[:-1]
    i = len(w)
    while i > 0 and w[i - 1] not in VOWELS:
        i -= 1
    j = i
    while j > 0 and w[j - 1] in VOWELS:
        j -= 1
    if i == 0:
        return ""
    return w[j:] + tail


def rhyme_tail(word: str, depth: int = 0) -> str:
    """The rhyming tail: the final vowel group + consonants, extended over an unstressed ending to the syllable before
    it ('shiver' -> 'iver', 'slumbered' -> 'umbered')."""
    w = word.lower()
    k = rhyme_key(w)
    if depth < 2 and k in WEAK and len(w) > len(k) + 1:
        stem = rhyme_tail(w[:-len(k)], depth + 1)
        return stem + k if stem else ""
    return k


def rhymes(a: str, b: str) -> bool:
    """Conservative rhyme: two different words with the same rhyming tail of at least 2 letters."""
    a, b = a.lower(), b.lower()
    ta, tb = rhyme_tail(a), rhyme_tail(b)
    return a != b and len(ta) >= 2 and ta == tb


def clearly_not_rhyme(a: str, b: str) -> bool:
    """Stricter than ``not rhymes``: also a different last letter, last two letters and first vowel of the final vowel
    group, so sound-alike endings ('night'/'white', 'see'/'tea') are not counted as non-rhymes."""
    a, b = a.lower(), b.lower()
    if a == b or rhymes(a, b) or a[-1] == b[-1] or a[-2:] == b[-2:]:
        return False
    va, vb = (re.match(r"[aeiouy]*", rhyme_key(x)).group(0) for x in (a, b))
    return not va or not vb or va[0] != vb[0]


def word_class(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "ly", "est", "er"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return suf
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return "s"
    return ""


def case_of(w: str) -> str | None:
    if w.islower():
        return "lower"
    if w[0].isupper() and (len(w) == 1 or w[1:].islower()):
        return "title"
    return None


# ------------------------------------------------------------------------------------------------------ verse text

def clean(line: str) -> str:
    return line.replace("_", "").strip()


def norm_line(line: str) -> str:
    return re.sub(r"\W+", " ", line.lower()).strip()


def blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Blank-line separated blocks with a poem index: a run of 3+ blank lines or a heading line starts a new poem."""
    out, cur, poem, blank = [], [], 0, 0
    for raw in lines:
        l = clean(raw)
        if not l:
            blank += 1
            if cur:
                out.append((poem, cur))
                cur = []
            continue
        letters = [c for c in l if c.isalpha()]
        heading = bool(letters) and all(c.isupper() for c in letters) or re.fullmatch(r"[IVXLC]+\.?", l) is not None
        if blank >= 3 or heading:
            poem += 1
        blank = 0
        if heading:
            continue
        cur.append(l)
    if cur:
        out.append((poem, cur))
    return out


def verse_line(l: str) -> bool:
    n = len(l.split())
    if not 4 <= n <= 14 or len(l) > 90 or BAD_LINE.search(l):
        return False
    m = FIRST_LETTER.search(l)
    if not m or not m.group(0).isupper():
        return False
    letters = [c for c in l if c.isalpha()]
    return sum(c.isupper() for c in letters) <= 0.5 * len(letters)


def windows(lines: list[str]):
    """Non-overlapping 4-line verse windows whose lines 2 and 4 rhyme."""
    for poem, blk in blocks(lines):
        if len(blk) < 4:
            continue
        caps = sum(1 for l in blk if (m := FIRST_LETTER.search(l)) and m.group(0).isupper())
        if caps < 0.8 * len(blk):  # verse capitalises its lines; wrapped prose does not
            continue
        i = 0
        while i + 4 <= len(blk):
            w = blk[i:i + 4]
            m2, m4 = LAST_WORD.search(w[1]), LAST_WORD.search(w[3])
            if all(verse_line(l) for l in w) and m2 and m4 and rhymes(m2.group(1), m4.group(1)):
                yield poem, w
                i += 4
            else:
                i += 1


class Vocab:
    """A book's lower-case verse vocabulary: counts, the words that end a verse line, and how often each word follows
    a determiner (noun-like) or an auxiliary / 'to' (verb-like), as a rough part-of-speech signal."""

    def __init__(self, lines: list[str]):
        self.counts, self.det, self.aux = collections.Counter(), collections.Counter(), collections.Counter()
        finals = set()
        for _, blk in blocks(lines):
            for l in blk:
                if not verse_line(l):
                    continue
                toks = WORD.findall(l)
                for prev, t in zip([""] + toks, toks):
                    if not t.islower():
                        continue
                    self.counts[t] += 1
                    self.det[t] += prev.lower() in DET
                    self.aux[t] += prev.lower() in AUX
                m = LAST_WORD.search(l)
                if m and m.group(1).islower():
                    finals.add(m.group(1))
        usable = [w for w in sorted(self.counts) if self.counts[w] >= 2 and len(w) >= 3 and w not in STOP
                  and w not in TEMPLATE_WORDS]
        self.pools = []
        for words in ([w for w in usable if w in finals], usable):
            by_len: dict[tuple[int, str], list[str]] = collections.defaultdict(list)
            for w in words:
                by_len[(len(w), word_class(w))].append(w)
            self.pools.append(by_len)

    def pos(self, w: str) -> str:
        n = max(1, self.counts[w])
        if self.det[w] >= 0.3 * n:
            return "noun"
        if self.aux[w] >= 0.2 * n:
            return "verb"
        return "other"


def dev_lines() -> set[str]:
    out = set()
    for l in open(C.DEV, encoding="utf-8"):
        d = json.loads(l)
        if d["task_type"] != TASK:
            continue
        for q in d["questions"]:
            for v in q["criteria"].values():
                for x in v.split("\n")[1:]:
                    if len(norm_line(x).split()) >= 3:
                        out.add(norm_line(x))
    return out


def alter(book: int, w: list[str], v: Vocab, balance: list[int]) -> str | None:
    """Line 4 with only its last word replaced, or None when no clean substitute exists. ``balance`` is the running
    sum of the signs of the length offsets so far; the next nonzero offset takes the sign that cancels it, so the
    altered version is not longer or shorter than the original on average."""
    m2, m4 = LAST_WORD.search(w[1]), LAST_WORD.search(w[3])
    orig, rhyme_word = m4.group(1), m2.group(1)
    case = case_of(orig)
    low = orig.lower()
    if case is None or len(orig) < 3 or low in STOP or low in TEMPLATE_WORDS or v.counts[low] < 2:
        return None
    before = WORD.findall(w[3][:m4.start(1)])
    prev = before[-1].lower() if before else ""
    want = "noun" if prev in DET else "verb" if prev in AUX else v.pos(low)
    others = [m.group(1) for x in (w[0], w[2]) if (m := LAST_WORD.search(x))]
    cls = word_class(low)
    r = C.rng(TASK, VERSION, "alter", book, "\n".join(w))
    # length offset of the substitute, symmetric around 0 so that neither version is longer on average: an offset
    # that cannot go both ways (words have at least 3 letters) becomes 0
    sign = -1 if balance[0] > 0 else 1 if balance[0] < 0 else r.choice([1, -1])
    delta = sign * r.choice([0, 0, 1, 2])
    if len(orig) - abs(delta) < 3:
        delta = 0
    steps = [delta, -delta, 0] + ([sign, -sign, 2 * sign, -2 * sign] if len(orig) >= 5 else [])
    stanza_words = {t.lower() for l in w for t in WORD.findall(l)}

    def ok(c: str) -> bool:
        if c == low or c in stanza_words or v.pos(c) != want:
            return False
        if prev == "a" and c[0] in "aeiou" or prev == "an" and c[0] not in "aeiou":
            return False
        return (clearly_not_rhyme(c, rhyme_word) and clearly_not_rhyme(c, low)
                and not any(rhymes(c, o) for o in others))

    for pool in v.pools:
        for d in dict.fromkeys(steps):
            cands = [c for c in pool.get((len(orig) + d, cls), ()) if ok(c)]
            if cands:
                c = r.choice(cands)
                if case == "title":
                    c = c[0].upper() + c[1:]
                s, e = m4.span(1)
                balance[0] += (d > 0) - (d < 0)
                return w[3][:s] + c + w[3][e:]
    return None


# ----------------------------------------------------------------------------------------------------------- build

def main() -> None:
    entries = fetch_all()
    C.record_source(TASK, entries, LICENCE, LICENCE_URL, notes=(
        "Project Gutenberg plain-text poetry collections, public domain in the USA; only the text between the "
        "'*** START OF' and '*** END OF' markers is read (header, footer and licence stripped). Ebooks: "
        + "; ".join(f"#{b} {t} ({a})" for b, (t, a) in sorted(BOOKS.items()))
        + ". Each item: four consecutive verse lines whose lines 2 and 4 rhyme; the altered copy replaces only the last "
          "word of line 4 with a non-rhyming word of similar length from the same book. Split by ebook."))
    meta = C.dev_meta(TASK)
    skip = dev_lines()
    seen: set[str] = set()
    by_book: dict[int, list[tuple[int, list[str], str]]] = {}
    balance = [0]
    for book in sorted(BOOKS):
        lines = body(C.RAW / TASK / f"pg{book}.txt")
        vocab = Vocab(lines)
        items = []
        for poem, w in windows(lines):
            key = "\n".join(norm_line(l) for l in w)
            if key in seen or any(norm_line(l) in skip for l in w):
                continue
            alt = alter(book, w, vocab, balance)
            if alt is None:
                continue
            seen.add(key)
            items.append((poem, w, alt))
        by_book[book] = items

    split_items: dict[str, list] = {"train": [], "select": [], "test": []}
    for book, items in by_book.items():
        split = C.split_of(TASK, f"pg{book}", select=SELECT_SHARE, test=TEST_SHARE)
        cap = TRAIN_PER_BOOK if split == "train" else HELD_PER_BOOK
        items = sorted(items, key=lambda it: C.unit("pick", TASK, VERSION, book, "\n".join(it[1])))[:cap]
        split_items[split] += [(book, *it) for it in items]

    targets = {"train": TRAIN_TARGET, "select": C.SPLIT_SIZES["select"], "test": C.SPLIT_SIZES["test"]}
    rows_by_split, books = {}, {}
    for split, items in split_items.items():
        items = sorted(items, key=lambda it: C.unit("cut", TASK, VERSION, it[0], "\n".join(it[2])))[:targets[split]]
        books[split] = collections.Counter(str(it[0]) for it in items)
        golds = [i % 2 for i in range(len(items))]  # gold position: exactly half A, half B
        C.rng(TASK, VERSION, "gold", split).shuffle(golds)
        rows = []
        for (book, poem, w, alt), want in zip(items, golds):
            original = "\n".join(w)
            altered = "\n".join(w[:3] + [alt])
            r = C.rng(TASK, VERSION, "item", book, original)
            tmpl, labels = r.choice(TEMPLATES), r.choice(LABELS)
            seed = f"{book}|{original}"
            crit, exp = C.mc([original, altered], 0, C.rng(TASK, VERSION, "mc", seed))
            if exp != C.code(want):
                crit, exp = C.mc([altered, original], 1, C.rng(TASK, VERSION, "mc", seed))
            crit = {k: f"{labels[i]}\n{v}" for i, (k, v) in enumerate(crit.items())}
            q = {"instructions": tmpl, "criteria": crit, "expected": exp}
            rows.append(C.row(TASK, meta, f"gutenberg_poetry_{C.COLLECTED}", f"pg{book}-poem{poem:04d}", [q]))
        rows_by_split[split] = rows
    counts = C.write_splits(TASK, rows_by_split, TRAIN_TARGET)
    print(json.dumps({"counts": counts, "books_per_split": {s: len(b) for s, b in books.items()},
                      "items_per_book": {s: dict(sorted(b.items(), key=lambda x: int(x[0]))) for s, b in books.items()},
                      "available": {b: len(v) for b, v in by_book.items()}}))


if __name__ == "__main__":
    main()
