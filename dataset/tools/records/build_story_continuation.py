"""story_continuation: 2-4 consecutive sentences of a public-domain novel -> which sentence comes next (4 options).

    python -I tools/records/build_story_continuation.py

Source: a fixed list of public-domain (USA) English novels and story collections, plain-text eBooks downloaded once from
https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt (2 s between requests) into data/generalist/raw/story_continuation/
and pinned by sha256. The dev set's books (Pride and Prejudice, A Study in Scarlet, The Adventures of Sherlock Holmes,
Frankenstein, Dracula) are excluded, and so is every other Sherlock Holmes book.

Per book: the distributor's header, footer and licence (everything outside the "*** START OF" / "*** END OF" markers),
headings, tables of contents, illustration and footnote markers, verse and indented blocks are removed; prose paragraphs are
split into sentences by a rule-based splitter. An item is a window of 2-4 consecutive sentences (6-60 words each, never across
a heading) plus the true next sentence; the 3 distractors are clean sentences of the same book at least 50 sentences away,
0.6x-1.6x the gold's word count. Distractors are chosen so that the gold's length rank among the 4 options is uniform and the
distractors' word overlap with the passage is as close as possible to the gold's (no length or overlap shortcut).

Group key (source_id) = the eBook id: whole books are held out for select and test.
"""
from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.records import common as C  # noqa: E402

TASK = "story_continuation"
VERSION = 1
SOURCE = f"pd_us_fiction_ebooks_{C.COLLECTED}"
TRAIN_TARGET = 2500
TRAIN_CAP = 120          # items per book in train
HELDOUT_CAP = 50         # items per book in select / test (spreads the 150 over several books)
SELECT_SHARE = 0.13
TEST_SHARE = 0.04
MIN_WORDS, MAX_WORDS = 6, 60
MIN_DISTANCE = 50        # sentences between a distractor and the window / gold
WINDOW_GAP = 25          # sentences between two items' windows of one book
LEN_LO, LEN_HI = 0.6, 1.6
URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
LICENCE = ("Public domain in the USA: Project Gutenberg eBooks of works whose US copyright has expired; the distributor's "
           "header, footer and licence text are stripped and the Project Gutenberg trademark is not used in the rows")
LICENCE_URL = "https://www.gutenberg.org/policy/license.html"

# (eBook id, author, title as in the eBook's "Title:" header (prefix match), sha256 of the downloaded file)
BOOKS: list[tuple[int, str, str, str]] = [
    (158, "Jane Austen", "Emma", "532b122b4e6a76cc556d6fdcd729b5892f5c4ce4a1b7060b9f832adfad8680dc"),
    (161, "Jane Austen", "Sense and Sensibility", "7bcd77c45cb32fb8d9f89402561270cc6a911c0a4e20667176d5be779fc3974a"),
    (105, "Jane Austen", "Persuasion", "7365e47089a3d63c64b011342bd00e2375cc51ee642dcf9af5aaba75cfd771bc"),
    (121, "Jane Austen", "Northanger Abbey", "273d7d35f8cc0286812bdb26ccc17f362b4f2d0d69a2ec96ca403fac8505b709"),
    (141, "Jane Austen", "Mansfield Park", "b34723544dbe8185e786d0fdd47e42e7e1ac4265b84141e31ca260c1e36b68d8"),
    (768, "Emily Bronte", "Wuthering Heights", "e533fe750589f0421d5d744576315f5c2b9b0d69e981179ea0551bbf134c5e02"),
    (1260, "Charlotte Bronte", "Jane Eyre", "13414dee2951c3ee731d76d2ffd822016b2479c892162760c5d0eb2aa5fa7631"),
    (969, "Anne Bronte", "The Tenant of Wildfell Hall", "a3aab47ab84eac0ce05210be83907b6bce654abc3e1c882d4975bc516ec67f0b"),
    (767, "Anne Bronte", "Agnes Grey", "c4069c6f61522720405a538168a599c0b314c9cfe685f1cd25c4f9809b77ee81"),
    (98, "Charles Dickens", "A Tale of Two Cities", "d54c2b80d40a40b982cd88852c6180bb944d95acdb028af3d0e01a1750681784"),
    (1400, "Charles Dickens", "Great Expectations", "9a637118af8e953e9764ec603d9b0a032883384d465acac2e27966a80cf1c6f8"),
    (730, "Charles Dickens", "Oliver Twist", "6c37f41a8a253e95eba0f990f61cf60ac2e6d625c306c13027672d67885a6b6a"),
    (766, "Charles Dickens", "David Copperfield", "51650d348820a64ca4d4233da035f804819d2231801b59373db4e1279a1985e0"),
    (1023, "Charles Dickens", "Bleak House", "27e002dee487817b00ba884f3d5ffd8dbb821f82353e914cdc22bf33c413ba16"),
    (786, "Charles Dickens", "Hard Times", "dd239b4a0c9c1b72be40f9f7e1aabce511c022b238a8feb2a9e63f169a7436d9"),
    (580, "Charles Dickens", "The Pickwick Papers", "b44980181ef76e3879d5864a5f6cc4073c12eb940bc6db7a32632e9bb2f4bbd9"),
    (145, "George Eliot", "Middlemarch", "dc2e0107e6ae07e8e33da934b2ec4e8e600826a2e0cd48df265119cd02e5fb50"),
    (550, "George Eliot", "Silas Marner", "b4e54f078d8ff14846ef6196f3ae5134194818841a43c135a5346beded735eb9"),
    (6688, "George Eliot", "The Mill on the Floss", "6cd9e230aa05eb249e2c42630d051325cb865d9cf05902819a57177860d7947d"),
    (507, "George Eliot", "Adam Bede", "be0e4681617825580f2f1bff1f04f477a9af2d49b9835bcb7d9ab9eb9ef3aecb"),
    (110, "Thomas Hardy", "Tess of the d", "503e08df0ca12fb21f4db9df75cfa97f9ba31b4d136add695b9e3e350b1699b1"),
    (107, "Thomas Hardy", "Far from the Madding Crowd", "67d4901981ceaef9ae2e5de32d1c59c8005101375a932d49861054f65bb60099"),
    (143, "Thomas Hardy", "The Mayor of Casterbridge", "afc11a8bb54ae3d37551d4d6d3523e5df2371665781da769344597969c116a00"),
    (122, "Thomas Hardy", "The Return of the Native", "bdd2c262086b9c8ae4361ef1e7f29fcc9e462bbab108cbe94c3e972276444b14"),
    (74, "Mark Twain", "The Adventures of Tom Sawyer", "74d77384b123a6360db9ab58463cff8b38df8525fbdc6000c81ee388e1f3cf10"),
    (76, "Mark Twain", "Adventures of Huckleberry Finn", "d617a37aa7ae1e1a93dcde2634db2bccb86824e31e29a55230bdbf77d6872d59"),
    (1837, "Mark Twain", "The Prince and the Pauper", "fea44db55e86147d3708216d72d4be58f1869fb6a73cc371d51877d49745bfb8"),
    (35, "H. G. Wells", "The Time Machine", "2892e919000e17c83e1dac51b30f4675db50536b644d7579fe8a89bb399a9bdc"),
    (36, "H. G. Wells", "The War of the Worlds", "8417469e3ab664749f7b36ebb85799075818207b0380b54c27d07d592a44117d"),
    (5230, "H. G. Wells", "The Invisible Man", "28c70e3809ce945efbe5f8681532916a2c4253fee5cca6e1a191707af22280d3"),
    (159, "H. G. Wells", "The Island of Doctor Moreau", "6085aef7b293dc0935974736f71e84c86952d5cb4cbad977fde942ffeba98a31"),
    (43, "Robert Louis Stevenson", "The Strange Case of Dr. Jekyll and Mr. Hyde", "b43448a88391591f9cf82b25553df00faf47a2752a873185fcdd1156eebdb990"),
    (120, "Robert Louis Stevenson", "Treasure Island", "5bc08275eacea8640b1aa185c645283bb8c564d7b23df6b03437d229b4fc6ebd"),
    (421, "Robert Louis Stevenson", "Kidnapped", "d57ef5be2a98ff2bbe3819abc84deeeea7f5f039a4b90fd358b2babb0f75588a"),
    (174, "Oscar Wilde", "The Picture of Dorian Gray", "38f36b510417177aa87a6a24c968e3ec63a447b7df36a9c1a7c5a3f2d9e51547"),
    (219, "Joseph Conrad", "Heart of Darkness", "1bcdf0a1ac611dd6b70a20d100a07085754da4e90a949d6031717b86cd6d020a"),
    (5658, "Joseph Conrad", "Lord Jim", "e2de6f15eb867e864aa4b5e22410d6dc1c12b7c225a48e2376f6401b71a3b96e"),
    (974, "Joseph Conrad", "The Secret Agent", "0a37c8fc9a62db2efcea487f02c1cdd4d48657c66b54af3ad90f2317e42b7588"),
    (2701, "Herman Melville", "Moby", "b5e88b71a1cda068e9ab1d94344c9d932338ba6da1a66def97a1aecd9cfcc87d"),
    (33, "Nathaniel Hawthorne", "The Scarlet Letter", "ae8d5a2d55a7b5d2b4b37497338892dab5ff6cc535bf523698da4ba6abe15ee7"),
    (77, "Nathaniel Hawthorne", "The House of the Seven Gables", "0d09eef49bec474dc4253b3035f298425280ec82d3e70b43befa443dd5e9819a"),
    (209, "Henry James", "The Turn of the Screw", "171afa184a54b6004194e02047f5d01cf216d8bc519ddfb671a1e41d80bbdf65"),
    (541, "Edith Wharton", "The Age of Innocence", "aae279f1a60ac64be53f63357e708a2fdaabdb334a1c92f81fc1c3b5c848a092"),
    (284, "Edith Wharton", "The House of Mirth", "52728930e0b308772f8781b1e8b20a981b38cdebf161c20fb84ffc6764c1b6df"),
    (4517, "Edith Wharton", "Ethan Frome", "995fb43e2017211808edd68464ac9a5fb975fb81d6973bfbef59796702ae543a"),
    (215, "Jack London", "The Call of the Wild", "30f569c5671bba7bbc4a92ab6d8ee01a0d3be00f994819c77da62c28041eb8a2"),
    (910, "Jack London", "White Fang", "3c7226d00fd9b169f0016635d0e461501620f343220ee18db7ca9f083f4ad3f4"),
    (1074, "Jack London", "The Sea-Wolf", "8a53d5cd1b8ac63f353f29c1fc4968cda8d32cc7fe3d683f1afbee38a7dd12bf"),
    (160, "Kate Chopin", "The Awakening", "31d4577d255806b92c6296419adddd5ca460bdb788743878a09ded1e19f4161a"),
    (2814, "James Joyce", "Dubliners", "6be7d8400ac2549459307d1c1a20a25c86a736984269d3e9d989c817814be60c"),
    (2641, "E. M. Forster", "A Room with a View", "3dce58eb1786b10b79f8688968d293a1990dfed4a1f83a5c04a6a2a10381db36"),
    (2891, "E. M. Forster", "Howards End", "5eb70bcf8a299f4a546c84b063b8ac0dad2b177a98d5a8348ee3216bd9c98ffa"),
    (64317, "F. Scott Fitzgerald", "The Great Gatsby", "ce760ec377accd352b41bb8f64504a72d7aa18ab3afb42ded2b56cecacf29e35"),
    (155, "Wilkie Collins", "The Moonstone", "e2f9023a41c388fa2b0d2a21d71a363e603b33860d8d964e314b5f4da7e6f837"),
    (583, "Wilkie Collins", "The Woman in White", "c8cb8872f6c0a2a5b6489873c6c7b8c39f006c3fa44219738186a96f2c1d1254"),
    (599, "William Makepeace Thackeray", "Vanity Fair", "36c7db9809ec4e833125f9ccc81ee66583ea6d698114b2907d2220599126fddd"),
    (82, "Walter Scott", "Ivanhoe", "188187a4af0956b01ccb0a9f8fb50587ffa4fca0b2d12d8ff5a82fc6f05f15e0"),
    (203, "Harriet Beecher Stowe", "Uncle Tom", "95e4ce1153f8506d9903df84541cfa99c8ac6ad3ad69bcf5ea37d042d01a0a98"),
    (140, "Upton Sinclair", "The Jungle", "1a28274fdea8c1438ebad3d7d07946b3d8a0779754427ba4a4da3b64882b7514"),
    (4276, "Elizabeth Gaskell", "North and South", "675a034c9711be4483f17316ac09fc9ec58d4503516db9b95ed70dc64fce9c79"),
    (394, "Elizabeth Gaskell", "Cranford", "3bb263075a97afd4058933534549f6176d881f7a9f74bb62eb52be26670e3cb0"),
    (863, "Agatha Christie", "The Mysterious Affair at Styles", "1faa63bb31d418523417dda0227d29f78e71aec474db5a18021e41fab1dc2d57"),
    (1695, "G. K. Chesterton", "The Man Who Was Thursday", "16fde29acf764ba5742fd5db8833f424b6b89c0f6e282d518f6c626006faf6e1"),
    (11, "Lewis Carroll", "Alice", "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e"),
    (113, "Frances Hodgson Burnett", "The Secret Garden", "6b0bb5fbd0c4e873d2d22028da9d753cf3977d5f70ac58221556b28060badbf5"),
    (45, "L. M. Montgomery", "Anne of Green Gables", "89a5e9fb2e0bb44562a969785385366f94e1da736aebee7d9cdf459eb0b5f9f6"),
    (514, "Louisa May Alcott", "Little Women", "36831477b339dbcd7e7206119d77e9e58b9727ef3c299d1a1dc4446e1db97850"),
]

# ---------------------------------------------------------------- instruction templates (own wording, not the dev set's)
TEMPLATES = [
    "The following sentences are taken, in order, from a novel:\n\n{ctx}\n\nWhich sentence follows them directly in the book?",
    "Read this excerpt from a work of fiction.\n\n{ctx}\n\nWhat is the very next sentence of the original text?",
    "Excerpt:\n{ctx}\n\nOne of the options is the sentence the author wrote right after this excerpt; the others come from "
    "other parts of the same book. Which one continues the excerpt?",
    "{ctx}\n\nThe lines above are consecutive sentences from a published story. Pick the sentence that comes immediately "
    "after them.",
    "Below are {n} consecutive sentences from a book of fiction.\n\n{ctx}\n\nWhich option is the next sentence in the book?",
    "Passage ({n} sentences, original order):\n{ctx}\n\nChoose the sentence that the author placed right after the last one.",
    "A novel reads, at one point:\n\n{ctx}\n\nWhich of these sentences is the one that comes next in the novel?",
]

# ---------------------------------------------------------------- cleaning
START_RE = re.compile(r"^\*\*\* ?START OF[^\n]*$", re.M)
END_RE = re.compile(r"^\*\*\* ?END OF[^\n]*$", re.M)
HEADING_RE = re.compile(r"^(chapter|book|part|volume|vol\.|section|stave|canto|letter|appendix|preface|introduction|"
                        r"contents|epilogue|prologue|conclusion|finis|the end)\b|^[ivxlcdm]+[.:]?$|^\d+[.:]?$", re.I)
SKIP_PARA_RE = re.compile(r"produced by|transcriber|e-?text|ebook|e-book|project gutenberg|gutenberg|proofread|"
                          r"distributed proofreading|www\.|http|copyright|all rights reserved|illustrat", re.I)
ABBREV = {"mr", "mrs", "ms", "dr", "st", "messrs", "mme", "mlle", "rev", "col", "capt", "gen", "lt", "sgt", "prof",
          "jr", "sr", "hon", "gov", "esq", "no", "vs", "etc", "viz", "mt", "ft", "co", "bros", "rt", "sq", "ave", "ch",
          "vol", "pp", "cf", "ib", "ibid", "lieut", "maj", "adm", "supt", "insp", "inst", "ult", "prox", "fig", "e.g",
          "i.e", "a.m", "p.m", "do", "mons", "messieurs", "sen", "rep", "fr", "pres", "dept", "univ", "op"}
OPEN_Q = "\"“‘'"
CLOSE_Q = "\"”’'"


def strip_markers(text: str, book: int) -> str:
    s, e = START_RE.search(text), END_RE.search(text)
    if not s or not e or e.start() <= s.end():
        raise SystemExit(f"{book}: START/END markers not found")
    return text[s.end():e.start()]


def clean_inline(t: str) -> str:
    t = re.sub(r"\[(?:Illustration|Footnote|Sidenote|Transcriber)[^\]]*\]", " ", t, flags=re.I)
    t = re.sub(r"\[\d+\]|\[[A-Z]\]", "", t)                 # footnote anchors
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", t)           # _italics_
    t = re.sub(r"(?<!\w)=(.+?)=(?!\w)", r"\1", t)           # =bold=
    t = t.replace("--", "—").replace(" ", " ").replace("\t", " ")
    t = re.sub(r"\.\s*\.\s*\.(?:\s*\.)?", "...", t)          # ". . ." -> "..."
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def paragraphs(body: str) -> list[str | None]:
    """Prose paragraphs in order; None marks a break (heading, verse, table of contents, front matter...)."""
    out: list[str | None] = []
    for block in re.split(r"\n\s*\n", body.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        joined = clean_inline(" ".join(l.strip() for l in lines))
        indented = sum(1 for l in lines if l.startswith(("  ", "\t"))) > len(lines) / 2
        short_lines = len(lines) > 1 and sum(len(l.strip()) for l in lines) / len(lines) < 45
        letters = [c for c in joined if c.isalpha()]
        caps = letters and sum(c.isupper() for c in letters) / len(letters) > 0.6
        nwords = len(joined.split())
        if (not joined or indented or short_lines or caps or HEADING_RE.match(joined) or SKIP_PARA_RE.search(joined)
                or nwords < 4 or not re.search(r"[.!?][\"”’')\]]*$", joined)):
            out.append(None)
            continue
        out.append(joined)
    return out


def split_sentences(p: str) -> list[str]:
    """Rule-based splitter: a boundary is [.!?] or "..." (plus closing quotes / brackets), whitespace, then an
    (optionally quoted) capital letter or digit; abbreviations (Mr., Mrs., Dr., St., ...) and single initials never end a
    sentence; an ellipsis ends one only before a capital."""
    out, start = [], 0
    for m in re.finditer(r"(\.\.\.|[.!?])([\"”’')\]]*)(\s+)(?=[\"“‘'(\[]*[A-Z0-9])", p):
        term = m.group(1)
        before = p[start:m.start()]
        if term == ".":
            w = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
            if w:
                tok = w.group(1).lower()
                if tok.rstrip(".") in ABBREV or re.fullmatch(r"[a-z]", tok) or re.fullmatch(r"(?:[a-z]\.)+[a-z]", tok):
                    continue
        out.append(p[start:m.end(2)].strip())
        start = m.end()
    tail = p[start:].strip()
    if tail:
        out.append(tail)
    return out


def nwords(s: str) -> int:
    return len(s.split())


def quotes_balanced(s: str) -> bool:
    if s.count('"') % 2 or s.count("“") != s.count("”"):
        return False
    opens = len(re.findall(r"(?:^|(?<=[\s(\[—“\"]))[‘'](?=[\w…])", s))
    closes = len(re.findall(r"(?<=[.,!?;:—\-…a-rt-zA-RT-Z])[’'](?=$|[\s)\]—”\".,;:!?])", s))
    return opens == closes


def clean_option(s: str) -> bool:
    """A sentence that can stand alone as an option: right length, starts with a capital (after an opening quote), ends
    with terminal punctuation, balanced quotes and brackets, no stray markup."""
    if not MIN_WORDS <= nwords(s) <= MAX_WORDS:
        return False
    if not re.match(r"^[\"“‘']?[A-Z]", s) or not re.search(r"[.!?][\"”’']?$", s):
        return False
    if s.count("(") != s.count(")") or s.count("[") != s.count("]") or re.search(r"[_*=<>{}|#@\\/~^]|\d{3,}", s):
        return False
    return quotes_balanced(s)


def book_sentences(path: Path, book: int) -> list[tuple[int, str]]:
    """(block number, sentence) in reading order; a block is a run of prose paragraphs without a break."""
    body = strip_markers(path.read_text(encoding="utf-8-sig"), book)
    out, blk = [], 0
    for p in paragraphs(body):
        if p is None:
            blk += 1
            continue
        for s in split_sentences(p):
            out.append((blk, s))
    return out


# ---------------------------------------------------------------- items
def wordset(a: str) -> set[str]:
    """Words of 3+ characters, as the checker's overlap cue counts them."""
    return {w for w in re.sub(r"\W+", " ", a.lower()).split() if len(w) > 2}


def build_book(book: int, sents: list[tuple[int, str]], cap: int) -> list[dict]:
    meta = C.dev_meta(TASK)
    n = len(sents)
    texts = [s for _, s in sents]
    ok_len = [MIN_WORDS <= nwords(s) <= MAX_WORDS for s in texts]
    ok_opt = [clean_option(s) for s in texts]
    nw = [nwords(s) for s in texts]
    wsets = [wordset(s) for s in texts]
    first = {}
    for i in range(n):                    # one index per distinct option text (repeated sentences are not used twice)
        if ok_opt[i]:
            first.setdefault(texts[i], i)
    pool = sorted(first.values())
    r = C.rng(TASK, VERSION, "windows", book)
    starts = list(range(n))
    r.shuffle(starts)
    used: list[int] = []
    items = []
    for g in starts:                      # g = index of the gold sentence
        if len(items) >= cap:
            break
        k = C.rng(TASK, VERSION, "k", book, g).choice((2, 3, 3, 4))
        lo = g - k
        if lo < 0 or not ok_opt[g] or any(abs(g - u) < WINDOW_GAP for u in used):
            continue
        if not all(ok_len[i] and sents[i][0] == sents[g][0] for i in range(lo, g)):
            continue
        gold = texts[g]
        ctx = texts[lo:g]
        if gold in ctx or not quotes_balanced(" ".join(ctx)):   # the passage never starts or ends inside a quotation
            continue
        gw = nwords(gold)
        ctx_words = set().union(*wsets[lo:g])
        seen = {gold, *ctx}
        cands = [i for i in pool if not lo - MIN_DISTANCE < i < g + MIN_DISTANCE and texts[i] not in seen
                 and LEN_LO * gw <= nw[i] <= LEN_HI * gw]
        ri = C.rng(TASK, VERSION, "item", book, g)
        glen = len(gold)
        shorter = [i for i in cands if len(texts[i]) < glen]
        longer = [i for i in cands if len(texts[i]) > glen]
        rank = ri.randrange(4)            # number of distractors shorter than the gold
        if len(shorter) < rank or len(longer) < 3 - rank:
            continue
        gov = len(wsets[g] & ctx_words)

        def pick(lst: list[int], m: int) -> list[int]:
            keyed = sorted(lst, key=lambda i: (abs(len(wsets[i] & ctx_words) - gov), ri.random()))
            return keyed[:m]

        dis = pick(shorter, rank) + pick(longer, 3 - rank)
        opts = [gold] + [texts[i] for i in dis]
        crit, exp = C.mc(opts, 0, ri)
        tpl = TEMPLATES[ri.randrange(len(TEMPLATES))]
        q = {"instructions": tpl.format(ctx=" ".join(ctx), n=k), "criteria": crit, "expected": exp}
        items.append(C.row(TASK, meta, SOURCE, str(book), [q]))
        used.append(g)
    return items


def download() -> dict[int, Path]:
    paths, last = {}, 0.0
    for book, _, _, sha in BOOKS:
        p = C.RAW / TASK / f"pg{book}.txt"
        if not p.exists():
            wait = 2.0 - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
        paths[book] = C.fetch(TASK, URL.format(id=book), p.name, sha)
    return paths


def check_titles(paths: dict[int, Path]) -> None:
    bad = []
    for book, _, title, _ in BOOKS:
        head = paths[book].read_text(encoding="utf-8-sig")[:4000]
        m = re.search(r"^Title:\s*(.+)$", head, re.M)
        lang = re.search(r"^Language:\s*(.+)$", head, re.M)
        if not m or not m.group(1).strip().lower().startswith(title.lower()) or not lang or "English" not in lang.group(1):
            bad.append(f"{book}: expected {title!r}, header says {m.group(1).strip() if m else None!r} "
                       f"({lang.group(1).strip() if lang else None})")
    if bad:
        raise SystemExit("eBook ids do not match their titles:\n" + "\n".join(bad))


def main() -> None:
    ids = [b for b, *_ in BOOKS]
    assert len(ids) == len(set(ids)) and 50 <= len(ids) <= 70
    paths = download()
    check_titles(paths)
    split = {b: C.split_of(TASK, str(b), select=SELECT_SHARE, test=TEST_SHARE) for b in ids}
    per = {s: [b for b in ids if split[b] == s] for s in ("train", "select", "test")}
    if len(per["select"]) < 3 or len(per["test"]) < 3 or len(per["train"]) <= len(ids) / 2:
        raise SystemExit(f"split shares give {({s: len(v) for s, v in per.items()})} books")
    rows = {"train": [], "select": [], "test": []}
    for b in ids:
        sents = book_sentences(paths[b], b)
        rows[split[b]] += build_book(b, sents, TRAIN_CAP if split[b] == "train" else HELDOUT_CAP)
    counts = C.write_splits(TASK, rows, TRAIN_TARGET)
    titles = "; ".join(f"{b} = {t} ({a})" for b, a, t, _ in BOOKS)
    C.record_source(TASK, [{"name": f"pg{b}.txt", "url": URL.format(id=b)} for b in ids], LICENCE, LICENCE_URL,
                    notes=(f"builder version {VERSION}. {len(ids)} eBooks (id = title (author)): {titles}. "
                           "Books per split: " + "; ".join(f"{s}: {', '.join(map(str, v))}" for s, v in per.items())
                           + ". Every row's source_id is its eBook id; whole books are held out for select and test. "
                           "Excluded (dev set books): Pride and Prejudice, A Study in Scarlet, The Adventures of Sherlock "
                           "Holmes (and all other Sherlock Holmes books), Frankenstein, Dracula."))
    print(counts, {s: len(v) for s, v in per.items()})


if __name__ == "__main__":
    main()
