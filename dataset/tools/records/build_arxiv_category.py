"""T type ``arxiv_category``: a paper's title and abstract -> its research field, over the full list of 26 OpenAlex fields.

    python -I tools/records/build_arxiv_category.py

Source: OpenAlex works (CC0), fetched unmodified by tools/records/fetch_arxiv_category.py into
data/generalist/raw/arxiv_category/ (every file's sha256 is checked against SOURCE.json first; raw files are parsed as data
only). The dev items of this type come from arXiv, so every work with any trace of arXiv is excluded: an arXiv id, the arXiv
index, a location (or primary / best OA location) on arxiv.org or the arXiv source, an arXiv DOI (10.48550), or the word
arXiv in its title or abstract.

Label level: the OpenAlex *field* (26 classes: "Computer Science", "Medicine", ...). Fields give a label set of tens of
classes like the dev items (41 arXiv categories); subfields would give 252. 26 is also the number of options the validator
serves per question, so every served question shows the whole label list, as the dev items keep their whole list.
Gold = ``primary_topic.field`` of the work: a structured field of the record, which OpenAlex assigns with its own topic
classifier (https://help.openalex.org/data/topics/#assigning-topics-to-works); nothing here labels or edits it. Works whose
listed topics put less than ``MIN_FIELD_CONF`` of the classifier's probability on the gold field (sum of the scores of the
work's listed topics in that field) are dropped as uncertain labels.

Options: the 26 field names of fields.json, in a per-item shuffled order (``mc``). Text: ``Title:`` (on about 70 % of the
items; never a title that is not English, see ``english_titles``) and ``Abstract:`` with the record's own wording (abstract
rebuilt from the inverted index, markup and boilerplate removed, cut at a sentence boundary to ``MAX_CHARS``).
Classification statements (keywords lists, JEL / MSC / PACS codes), copyright and licence notices, graphical-abstract and
DOI / citation tails, a dangling section heading and an ellipsis-truncated end are cut; a work whose abstract has e-mail
addresses, links, author / contact blocks, formula placeholders, a truncated start or non-English text is dropped.
``SCRUB`` lists what may not remain and the build asserts 0 hits.

Splits: by sha256 of the OpenAlex work id (``C.split_of``); works sharing a normalised title or abstract are near-copies and
only one of them is kept. Each split holds an equal share of every field (class prior uniform, so no label dominates).
Works that are near-copies of a dev item or of a row of any other built type (shared word 8-grams, see ``drop_overlaps``)
are dropped. The dev set is read from ``C.DEV``, or from the repository's eval-v5/devset-v1/dev.jsonl when this checkout
has no copy under dataset/.
"""
from __future__ import annotations

import collections
import glob
import hashlib
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.records import common as C  # noqa: E402

TASK = "arxiv_category"
VERSION = "ac-1"
SNAPSHOT = "2026-10-28"
SOURCE = f"openalex_works_{SNAPSHOT}"
TRAIN_TARGET = 2500
SPLIT_SHARE = 0.05            # select and test shares of the hash range (cut to 150 each)
MIN_FIELD_CONF = 0.8
MAX_CHARS = 1400              # abstract, cut at a sentence boundary
MIN_CHARS = 300
TITLE_WORDS = (3, 40)
TITLE_SHARE = 0.75            # items that show the title (the others show the abstract only, as the dev items do)
TITLE_VOCAB_SHARE = 0.6       # a title is shown only if this share of its words is English (see english_titles)
VOCAB_MIN_DF = 3
SHINGLE = 8
OVERLAP_ABSTRACT = 0.10      # share of a work's 8-grams found in other texts that makes it a near-copy
OVERLAP_TITLE = 0.5
LICENCES = {"cc-by", "cc-by-sa", "public-domain"}
ARXIV_SOURCE = "S4306400194"
RAW = C.RAW / TASK
DEV = C.DEV if C.DEV.exists() else C.ROOT.parent / "eval-v5" / "devset-v1" / "dev.jsonl"
OTHER_GLOBS = (str(C.OUT / "*.jsonl"), str(C.ROOT / "data" / "generalist" / "n_gen" / "*.jsonl"),
               str(C.ROOT.parent / "data" / "generalist" / "rec" / "*.jsonl"),
               str(C.ROOT.parent / "data" / "generalist" / "gen" / "*.jsonl"))

# ---------------------------------------------------------------------------------------------------------------- text

TAG = re.compile(r"</?(?:jats:|mml:)?[A-Za-z][\w:.-]*(?:\s[^<>]{0,200})?/?>")
LEAD = re.compile(r"^\W*(?:(?:(?i:abstract)(?:\s*/\s*(?i:summary))?|(?i:summary))\b\s*[:.\-–—]?\s*(?=[A-Z0-9(\[\"'“])"
                  r"|(?:ABSTRACT|Abstract)(?=[A-Z][a-z]))")
# a tail that is not part of the abstract: cut the text where it starts
TAIL = re.compile(
    r"(?i:\b(?:key ?words?|keyterms|index terms|subject terms)\b)\s*(?:[:：]|\s[-–—]\s)"
    r"|\bKEY ?WORDS?\b"
    r"|\bJEL\b(?:\s+(?i:classifications?|codes?))?\s*[:.]?\s*[A-Z]\d"
    r"|\b(?:MSC|AMS)\b\s*(?:\(?\s*(?:19|20)\d\d\s*\)?|(?i:subject\s+)?(?i:classifications?))"
    r"|\bPACS\b(?:\s+(?i:numbers?|codes?))?\s*[:.]?\s*\d"
    r"|(?i:\bgraphical\s*abstract|\bhighlights\s*[:：]|\bDOI\s*[:：]|\bcitation\s*[:：]|\bcite this article\b)"
    r"|(?<=\S)\s*(?:ABSTRACT|Abstract)(?=[A-Z][a-z])"
    r"|©|\([cC]\)\s*(?:19|20)\d\d|(?i:\bcopyright\b|\ball rights reserved\b|\bopen access article\b)"
    r"|(?i:\bcreative commons\b|\blicensee\b|\bthis article is protected\b)|\bORCID\b"
    r"|(?i:\b(?:resumen|resumo|résumé|zusammenfassung|abstrak|özet|sažetak|streszczenie|riassunto)\b)\s*[:.]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# boilerplate that is no abstract (author and contact blocks name private persons): the work is dropped
JUNK = re.compile(r"(?i:corresponding author|correspondence\s*(?:to|address)?\s*:|author information|\bsponsorship\s*:"
                  r"|\bfunding\s*:|ugc[- ]?care|find, read and cite|\bpdf\s*citations|\baffiliations?\s*:)")
ELLIPSIS = re.compile(r"\.\.\.|…")
PLACEHOLDER = re.compile(r"\[\s*Formula[^\]]*\]|\[\s*see text\s*\]", re.I)
TRUNCATED_START = re.compile(r"[a-z]+\b(?![-’'])")        # "power generation system of ...": the record lost its first words
HEADING_END = re.compile(r"(?:^|\s)(?:Conclusions?|Results?|Methods?|Background|Objectives?|Aims?|Purpose|Findings|Discussion"
                         r"|Introduction|Materials and methods|Methodology|Significance|Interpretation)\s*[.:]?$")
MISSING_SPACE = re.compile(r"(?<=[a-z0-9)\]'\"’”%])([.!?])(?=[A-Z][a-z])")
LINK = re.compile(r"https?://|www\.|\bdoi\.org\b", re.I)
BOUNDARY = re.compile("(?<=[.!?])[\"'”’)\\]]*\\s+(?=[\"'“‘(\\[]?[A-Z0-9])")
ABBREV = re.compile(r"(?:\b(?:[A-Za-z]\.){1,3}|\b(?:e\.g|i\.e|cf|vs|etc|al|Fig|Figs|Eq|Eqs|No|Nos|Dr|Prof|approx|ca|sp|spp|var|"
                    r"subsp|St|Mr|Mrs|Ms|Jr|Sr|Inc|Co|Ltd|vol|pp|resp)\.)$")
SENT_END = (".", "!", "?", ".)", ".”", ".\"", "?”", "!”")

# what must not remain in any row (the scrub test); the label words themselves are the subject matter and stay
SCRUB = re.compile(
    r"\bkey ?words?\s*[:：]|\bindex terms\b|\bJEL\s+(?:classification|codes?)\b|\bPACS\s+(?:numbers?|codes?)\b"
    r"|\bMSC\s*(?:19|20)\d\d\b|\bsubject classification\b|©|\bcopyright\b|\ball rights reserved\b|\bcreative commons\b"
    r"|\bopen access article\b|\bgraphical abstract\b|\barxiv\b|\bopenalex\b|https?://|www\.|[\w.+-]+@[\w-]+\.[a-z]{2,}"
    r"|</?[A-Za-z][\w:]*>|&[a-z]+;|&#\d+;", re.I)

EN_WORDS = frozenset("the of and in to a is for with on that by this are was were as from be an at which these or it we our "
                     "has have been than between their its using based study results".split())
# Romance / German / Indonesian function words. Words that are also English tokens in abstracts are left out ("IL-6",
# "Au nanoparticles", "x and y", "et al.", "LOS", "per", "von Willebrand", "do"); titles use the full list
FOREIGN_WORDS = frozenset("de la el las del que por con para una um uma os das dos em não le les des du une est aux "
                          "der die und das mit für ist auf den dem ein eine nicht che della dei delle sono "
                          "dan yang pada dalam terhadap untuk dengan ini dari oleh sebagai atau tidak adalah serta kepada bagi"
                          .split())
TITLE_FOREIGN_WORDS = FOREIGN_WORDS | frozenset("y e di il et los do au un pengaruh analisis penerapan peningkatan "
                                                "pembelajaran implementasi perancangan pengembangan hubungan studi kasus "
                                                "berbasis menggunakan".split())


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def strip_markup(text: str) -> str:
    t = str(text or "")
    for _ in range(2):
        t = html.unescape(t)
    t = TAG.sub(" ", t)
    t = "".join(" " if unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs", "Zl", "Zp") else ch for ch in t)
    t = MISSING_SPACE.sub(r"\1 ", t)
    t = collapse(t)
    return re.sub(r"\s+([,;:.!?])(?=\s|$)", r"\1", t)


def rebuild(inv: dict | None) -> str | None:
    """The abstract from OpenAlex's inverted index (None when positions are missing or repeated)."""
    if not inv:
        return None
    pos: dict[int, str] = {}
    for word, ps in inv.items():
        for p in ps:
            if p in pos:
                return None
            pos[p] = word
    if not pos or max(pos) + 1 != len(pos):
        return None
    return " ".join(pos[i] for i in range(len(pos)))


def english(text: str, ratio: bool = True) -> bool:
    """Latin script (Greek letters allowed, as in formulas), few non-ASCII letters, few Romance / German / Indonesian function
    words, and (running text only, not titles) enough English function words."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    other = sum(ord(c) > 0x24F and not 0x370 <= ord(c) <= 0x3FF for c in letters)
    if other / len(letters) > 0.01 or sum(ord(c) > 127 for c in letters) / len(letters) > 0.08:
        return False
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    if not words:
        return False
    foreign = FOREIGN_WORDS if ratio else TITLE_FOREIGN_WORDS
    if sum(w in foreign for w in words) / len(words) > (0.03 if ratio else 0.13):
        return False
    return not ratio or sum(w in EN_WORDS for w in words) / len(words) >= 0.12


def cut(text: str, limit: int) -> str | None:
    """The text if it fits and ends a sentence, else its longest run of whole sentences within ``limit`` characters."""
    if len(text) <= limit and text.endswith(SENT_END) and not ABBREV.search(text):
        return text
    best = None
    for m in BOUNDARY.finditer(text):
        if m.start() > limit:
            break
        head = text[:m.start()].rstrip()
        if ABBREV.search(head):
            continue
        best = head
    if best is None and len(text) <= limit and text.endswith(SENT_END[:3]):
        best = text
    return best


def clean_abstract(raw: str) -> str | None:
    t = strip_markup(raw)
    for _ in range(2):
        t = LEAD.sub("", t, count=1)
    if JUNK.search(t) or PLACEHOLDER.search(t) or TRUNCATED_START.match(t):
        return None
    m = TAIL.search(t)
    if m:
        t = t[:m.start()].rstrip(" ,;:-–—(")
    m = ELLIPSIS.search(t)          # a truncated abstract ("... pathologies...") keeps its whole sentences before the cut
    if m:
        t = t[:m.start()].rstrip()
    if EMAIL.search(t) or LINK.search(t):
        return None
    t = cut(t, MAX_CHARS)
    if t:
        t = HEADING_END.sub("", t).rstrip()      # a section heading left dangling by the cut ("... everyday life. Conclusion.")
    if not t or not t.endswith(SENT_END) or len(t) < MIN_CHARS or not english(t):
        return None
    return t


def clean_title(raw: str) -> str | None:
    t = strip_markup(raw).rstrip(" .")
    n = len(t.split())
    if not (TITLE_WORDS[0] <= n <= TITLE_WORDS[1]) or EMAIL.search(t) or LINK.search(t) or not english(t, ratio=False):
        return None
    return t


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def shingles(text: str, n: int = SHINGLE) -> set[tuple[str, ...]]:
    w = norm(text).split()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


# ------------------------------------------------------------------------------------------------------------- records

def on_arxiv(w: dict) -> bool:
    blob = json.dumps([w.get("ids"), w.get("doi"), w.get("indexed_in"), w.get("locations"), w.get("primary_location"),
                       w.get("best_oa_location")]).lower()
    if "arxiv" in blob or "10.48550" in blob or ARXIV_SOURCE.lower() in blob:
        return True
    if (w.get("locations_count") or 0) > len(w.get("locations") or []):      # not every location is shown: cannot verify
        return True
    return bool(re.search(r"arxiv", f"{w.get('title') or ''}", re.I))


def field_conf(w: dict) -> float:
    f = w["primary_topic"]["field"]["id"]
    return sum(float(t.get("score") or 0) for t in w.get("topics") or [] if (t.get("field") or {}).get("id") == f)


def verify_raw() -> dict:
    src = json.loads((RAW / "SOURCE.json").read_text())
    for name, meta in sorted(src["files"].items()):
        got = hashlib.sha256((RAW / name).read_bytes()).hexdigest()
        if got != meta["sha256"]:
            raise SystemExit(f"{RAW / name}: sha256 {got} differs from SOURCE.json {meta['sha256']}")
    return src


def load_fields() -> dict[str, str]:
    res = json.loads((RAW / "fields.json").read_text())["results"]
    out = {f["id"]: f["display_name"] for f in res}
    if len(out) != 26 or len(set(out.values())) != 26:
        raise SystemExit(f"{TASK}: expected 26 distinct OpenAlex fields, got {len(out)}")
    return dict(sorted(out.items(), key=lambda kv: int(kv[0].rsplit("/", 1)[1])))


def candidates(fields: dict[str, str], why: collections.Counter) -> list[dict]:
    out, seen = [], set()
    for path in sorted(glob.glob(str(RAW / "works__*.json"))):
        for w in json.loads(Path(path).read_text())["results"]:
            wid = str(w.get("id") or "").rsplit("/", 1)[-1]
            if not re.fullmatch(r"W\d+", wid) or wid in seen:
                why["duplicate id"] += 1
                continue
            seen.add(wid)
            pt = w.get("primary_topic") or {}
            fid = (pt.get("field") or {}).get("id")
            if fid not in fields or (pt.get("field") or {}).get("display_name") != fields[fid]:
                why["no or unknown field"] += 1
                continue
            if on_arxiv(w):
                why["arXiv trace"] += 1
                continue
            if (w.get("type") != "article" or w.get("language") != "en" or w.get("is_retracted")
                    or (w.get("primary_location") or {}).get("license") not in LICENCES):
                why["type / language / retracted / licence"] += 1
                continue
            if field_conf(w) < MIN_FIELD_CONF:
                why[f"field confidence < {MIN_FIELD_CONF}"] += 1
                continue
            date = str(w.get("publication_date") or "")
            if not ("2010-01-01" <= date <= "2026-07-31"):
                why["publication date"] += 1
                continue
            raw_abs = rebuild(w.get("abstract_inverted_index"))
            abstract = clean_abstract(raw_abs) if raw_abs else None
            if not abstract:
                why["abstract unusable"] += 1
                continue
            title = clean_title(w.get("title") or w.get("display_name") or "")
            if re.search(r"arxiv", f"{abstract} {w.get('title') or ''}", re.I):
                why["arXiv trace"] += 1
                continue
            out.append({"id": wid, "field": fields[fid], "title": title, "abstract": abstract, "date": date})
    return out


def english_titles(cands: list[dict], why: collections.Counter) -> list[dict]:
    """Hide (set to None) a title that is not English: fewer than ``TITLE_VOCAB_SHARE`` of its words (3+ letters) occur in
    its own abstract or in at least ``VOCAB_MIN_DF`` abstracts of the pool (the abstracts passed the English test). Such a
    work stays, as an abstract-only item; abstract-only items are part of the design anyway."""
    def words(t: str) -> list[str]:
        return [x for x in re.findall(r"[a-z]+", t.lower()) if len(x) >= 3]

    df = collections.Counter(x for c in cands for x in set(words(c["abstract"])))
    vocab = {x for x, n in df.items() if n >= VOCAB_MIN_DF}
    for c in cands:
        if c["title"] is None:
            why["title hidden: unusable"] += 1
            continue
        w = words(c["title"])
        own = set(words(c["abstract"]))
        if w and sum(x in vocab or x in own for x in w) < TITLE_VOCAB_SHARE * len(w):
            c["title"] = None
            why["title hidden: not English"] += 1
    return cands


def drop_near_copies(cands: list[dict], why: collections.Counter) -> list[dict]:
    """Works sharing a normalised title or abstract: keep only the first in hash order (they would be near-copies)."""
    keep, titles, abstracts = [], set(), set()
    for c in sorted(cands, key=lambda c: C.unit("pick", TASK, c["id"])):
        t, a = norm(c["title"] or ""), norm(c["abstract"])
        if (t and t in titles) or a in abstracts:
            why["near-copy of another work"] += 1
            continue
        if t:
            titles.add(t)
        abstracts.add(a)
        keep.append(c)
    return keep


def other_texts() -> list[str]:
    """Instruction texts of the dev set and of every other built type (T, N records, generators)."""
    paths = [str(DEV)] + sorted(p for g in OTHER_GLOBS for p in glob.glob(g) if not Path(p).name.startswith(f"{TASK}."))
    out: dict[str, None] = {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("task_type") == TASK and not p == str(DEV):
                    continue
                for q in r.get("questions") or []:
                    out[str(q.get("instructions") or "")] = None
    return list(out)


def drop_overlaps(cands: list[dict], why: collections.Counter) -> list[dict]:
    """Drop near-copies of the dev set or of another built type: at least ``OVERLAP_ABSTRACT`` of the abstract's word
    8-grams, or ``OVERLAP_TITLE`` of the title's, occur in those texts, or the title equals one of their lines. (A single
    shared 8-gram is no copy: stock phrases such as "the purpose of this study was to examine the" recur everywhere.)"""
    own = [(shingles(c["abstract"]), shingles(c["title"] or "")) for c in cands]
    wanted = set().union(*(a | t for a, t in own)) if own else set()
    titles = {norm(c["title"]) for c in cands if c["title"] and len(norm(c["title"]).split()) >= 4}
    matched: set[tuple[str, ...]] = set()
    title_lines: set[str] = set()
    for text in other_texts():
        matched.update(s for s in shingles(text) if s in wanted)
        for line in text.split("\n"):
            body = line.split(":", 1)[1] if re.match(r"^[\w ()-]{1,40}:", line) else line
            if norm(body) in titles:
                title_lines.add(norm(body))
    out = []
    for c, (a, t) in zip(cands, own):
        if (len(a & matched) >= OVERLAP_ABSTRACT * max(1, len(a)) or (t and len(t & matched) >= OVERLAP_TITLE * len(t))
                or (c["title"] and norm(c["title"]) in title_lines)):
            why["near-copy of the dev set or another built type"] += 1
            continue
        out.append(c)
    return out


# -------------------------------------------------------------------------------------------------------------- render

LABELS = (("Title", "Abstract"), ("Title", "Abstract"), ("Paper title", "Abstract"), ("Title", "Summary of the paper"),
          ("Article title", "Article abstract"))
INTROS = ("", "", "", "A journal article is described below.", "Here is a published research paper.",
          "The record below comes from a scholarly journal.")
QUESTIONS = (
    "Which research field does this paper belong to?",
    "Choose the field that best describes the subject of this article.",
    "Assign the article to one of the fields listed below.",
    "What is the primary field of this publication?",
    "Under which field would a bibliographic index file this work?",
    "Pick the field that matches what the work described above is about.",
    "Judging from the {what}, which field is this paper's main one?",
    "Which of the following fields covers the topic of this paper?",
)


def render(c: dict, labels: list[str], r) -> dict:
    title_lab, abs_lab = LABELS[r.randrange(len(LABELS))]
    show_title = r.random() < TITLE_SHARE and c["title"] is not None
    record = (f"{title_lab}: {c['title']}\n" if show_title else "") + f"{abs_lab}: {c['abstract']}"
    what = "title and abstract" if show_title else "abstract"
    question = QUESTIONS[r.randrange(len(QUESTIONS))].format(what=what)
    intro = INTROS[r.randrange(len(INTROS))]
    head = f"{intro}\n\n" if intro else ""
    instructions = f"{head}{question}\n\n{record}" if r.random() < 0.25 else f"{head}{record}\n\n{question}"
    criteria, expected = C.mc(labels, labels.index(c["field"]), r)
    return {"instructions": instructions, "criteria": criteria, "expected": expected}


def quotas(labels: list[str]) -> dict[str, dict[str, int]]:
    """Equal per-field counts per split; the remainder goes to the fields first in a hash order of the split."""
    out = {}
    for split, total in (("train", TRAIN_TARGET), ("select", C.SPLIT_SIZES["select"]), ("test", C.SPLIT_SIZES["test"])):
        base, extra = divmod(total, len(labels))
        order = sorted(labels, key=lambda f: C.unit("extra", TASK, split, f))
        out[split] = {f: base + (1 if order.index(f) < extra else 0) for f in labels}
    return out


def dev_meta() -> dict:
    for line in open(DEV, encoding="utf-8"):
        d = json.loads(line)
        if d["task_type"] == TASK:
            return {k: d.get(k) for k in ("area", "gold", "half", "component")}
    raise SystemExit(f"{TASK}: not a dev task type")


def main() -> None:
    src = verify_raw()
    fields = load_fields()
    labels = list(fields.values())
    why: collections.Counter = collections.Counter()
    cands = candidates(fields, why)
    cands = english_titles(cands, why)
    cands = drop_near_copies(cands, why)
    cands = drop_overlaps(cands, why)
    meta = dev_meta()
    q = quotas(labels)
    by = collections.defaultdict(list)
    for c in cands:
        by[(C.split_of(TASK, c["id"], select=SPLIT_SHARE, test=SPLIT_SHARE), c["field"])].append(c)
    rows: dict[str, list[dict]] = {s: [] for s in q}
    short = {}
    for split in q:
        for f in labels:
            pool = sorted(by[(split, f)], key=lambda c: C.unit("pick", TASK, c["id"]))
            if len(pool) < q[split][f]:
                short[f"{split}:{f}"] = (len(pool), q[split][f])
            for c in pool[:q[split][f]]:
                r = C.row(TASK, meta, SOURCE, c["id"], [render(c, labels, C.rng(TASK, VERSION, c["id"]))])
                r.update(collected=SNAPSHOT, collected_utc=f"{SNAPSHOT}T00:00:00Z")
                rows[split].append(r)
    if short:
        raise SystemExit(f"{TASK}: field quotas not filled (have, need): {short}")
    for split, rs in rows.items():
        for r in rs:
            for qq in r["questions"]:
                for text in [qq["instructions"], *qq["criteria"].values()]:
                    m = SCRUB.search(text)
                    if m:
                        raise SystemExit(f"{TASK}: scrub word {m.group(0)!r} left in {r['source_id']}")
        prior = collections.Counter(r["questions"][0]["criteria"][r["questions"][0]["expected"]] for r in rs)
        if max(prior.values()) > 3 * sorted(prior.values())[len(prior) // 2]:
            raise SystemExit(f"{TASK}: a field above 3x the median count in {split}")
    counts = C.write_splits(TASK, rows, TRAIN_TARGET)
    n_works = sum(len(json.loads((RAW / n).read_text())["results"]) for n in src["files"] if n.startswith("works__"))
    print(json.dumps({"task": TASK, "version": VERSION, "works": n_works, "kept_candidates": len(cands),
                      "filters": dict(sorted(why.items())), "pool": {s: sum(len(v) for k, v in by.items() if k[0] == s)
                                                                    for s in q},
                      "counts": counts, "label_level": "field", "classes": len(labels)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
