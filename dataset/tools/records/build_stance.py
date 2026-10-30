"""T type ``stance``: does an argument support or oppose a debate topic (args.me corpus, CC BY 4.0).

    python -I tools/records/build_stance.py

Source: webis/args_me at a pinned revision, file ``args-me.jsonl`` (args.me corpus 1.0-cleaned: 382,545 arguments from
debate.org, debatepedia.org, debatewise.org and idebate.org). Each record has one premise with a structured ``stance``
(PRO / CON) towards its ``conclusion``; that field is the label. The dataset's loading script is never downloaded or run.

One question per item: the conclusion (topic) and the premise text (argument), two lettered options (for / against),
shuffled by ``common.mc``; gold is exactly 50/50 in every split, and inside every split each portal is 50/50 as well.

Portals: idebate.org and debatewise.org. Left out: www.debate.org (the label is the debater's side in a multi-round
debate; rounds quote and rebut the other debater, and a hand read of filtered samples found labels that contradict the
text) and www.debatepedia.org (after the filters almost only PRO premises remain, so its style alone would give the label).

Cleaning (all in code below): citation markers, URLs and appended bibliography entries removed, whitespace collapsed, the
text cut at a sentence boundary
to at most ``MAX_CHARS``; arguments under 15 words dropped; arguments that state their side (debate role words such as
"Pro", "my opponent", "the motion", "I agree", "I oppose", a "Pro:" / "Yes," / "No," opener, a verdict such as "this is
untrue", or a quote of the whole topic) dropped; topics that are not a proposition (no verb, a question, a truncated
"..." heading, debate meta titles such as "Rap Battle" or "Debate round 2", first- or second-person titles, "X vs Y")
dropped; topics or arguments with slurs, profanity or abuse dropped; texts seen with both labels dropped, and only the
first copy of a repeated text kept.

Group key (``source_id``): the normalised topic. The split is the hash of a connected component that joins topics sharing
a discussion title or a near-identical argument (same first 12 words), so a topic's arguments, the other points of the
same debate page and cross-portal copies never cross splits.
"""
from __future__ import annotations

import collections
import functools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.records import common as C  # noqa: E402

TASK = "stance"
VERSION = "stance-1"
REPO = "webis/args_me"
REVISION = "042bdf645bc980c751e9b217cc77e47624394390"
DATA_FILE = "args-me.jsonl"
DATA_SHA = "dc49ce6a5547370034be99365e8041d91ce477dbb4e0012ae16c0a6ecdd28187"
README_FILE = "README.md"
SOURCE = "args_me_1.0_cleaned_cc_by_4"
TRAIN_TARGET = 1500
TOPIC_CAP = {"train": 10, "select": 4, "test": 4}
MAX_CHARS = 700
MIN_WORDS = 15
PREFIX_WORDS = 12
PORTAL_SHARE = {"idebate.org": 0.65, "debatewise.org": 0.35}

LICENCE = ("CC BY 4.0. args.me corpus (version 1.0-cleaned), Yamen Ajjour, Henning Wachsmuth, Johannes Kiesel, Martin "
           "Potthast, Matthias Hagen, Benno Stein (2020), Zenodo, doi:10.5281/zenodo.4139439, "
           "https://doi.org/10.5281/zenodo.4139439; described in Wachsmuth et al. (2017), 'Building an Argument Search "
           "Engine for the Web', Proceedings of the 4th Workshop on Argument Mining, pp. 49-59. Mirror used: "
           "https://huggingface.co/datasets/webis/args_me. Arguments originate from idebate.org and debatewise.org.")
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"

# ---------------------------------------------------------------------------------------------------------------- text

DASHES = "–—"
DOUBLE_BRACKET = re.compile(r"\[\[.*?\]\]|\[\[|\]\]")
CITATION = re.compile(r"\[\s*\d+(?:\s*[,\-" + DASHES + r"]\s*\d+)*\s*\]")
URL = re.compile(r"https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|org|net|gov|edu|co\.uk|ly)/\S*", re.I)
MISSING_SPACE = re.compile(r"(?<=[a-z0-9)])([.!?])(?=[A-Z][a-z])")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
BOUNDARY = re.compile("(?<=[.!?])[\"'”’)\\]]*\\s+(?=[\"'“‘(]?[A-Z0-9])")
ABBREV = re.compile(r"(?:\b(?:[A-Za-z]\.){1,3}|\b(?:Mr|Mrs|Ms|Dr|St|vs|etc|No|Jr|Sr|Prof|Inc|Co|Gen|Gov|Sen|Rep|Fig|approx)\.)$")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def clean(text: str) -> str:
    t = DOUBLE_BRACKET.sub(" ", str(text))
    t = CITATION.sub(" ", t)
    t = URL.sub(" ", t)
    t = MISSING_SPACE.sub(r"\1 ", t)
    t = collapse(t)
    return SPACE_BEFORE_PUNCT.sub(r"\1", t)


# an appended bibliography entry: "McDonald, Henry, 'Title' ...", "Murphy, Dan. "Title" ...", "University of X, 'Title'"
REFERENCE = re.compile("(?:^|(?<=\\s))[A-Z][\\w'\\-]+(?: [A-Z][\\w'\\-]+){0,4},\\s+[A-Z][\\w.'\\- ]{0,40}[,.]\\s*[‘“\"']")
SENTENCE_END = (".", "!", "?", "\"", "”", "’", "'", ")")


def trim_reference(text: str) -> str | None:
    """The text before its first appended reference, ending at a sentence end (None if nothing usable is left)."""
    m = REFERENCE.search(text)
    if not m:
        return text
    head = text[:m.start()].rstrip()
    if head.endswith(SENTENCE_END):
        return head
    best = None
    for b in BOUNDARY.finditer(head):
        if not ABBREV.search(head[:b.start()].rstrip()):
            best = head[:b.start()].rstrip()
    return best


def cut(text: str, limit: int = MAX_CHARS) -> str | None:
    """The text itself if it fits, else its longest run of whole sentences within ``limit`` characters (None if the first
    sentence alone is longer)."""
    if len(text) <= limit:
        return text
    best = None
    for m in BOUNDARY.finditer(text):
        if m.start() > limit:
            break
        head = text[:m.start()].rstrip()
        if ABBREV.search(head):
            continue
        best = head
    return best


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def n_words(text: str) -> int:
    return len(re.findall(r"\w+", text))


# ------------------------------------------------------------------------------------------------------- scrub lists

# slurs, profanity and abuse: an item with any of these in the topic or the argument is dropped
ABUSIVE = re.compile(r"\b(?:" + "|".join([
    r"fuck\w*", r"motherfuck\w*", r"shit\w*", r"bullshit", r"bitch\w*", r"cunts?", r"dicks?", r"dickhead\w*", r"cocks?",
    r"cocksucker\w*", r"pussy", r"pussies", r"asshole\w*", r"arsehole\w*", r"ass", r"asses", r"dumbass\w*", r"jackass\w*",
    r"bastards?", r"piss\w*", r"damn\w*", r"goddamn\w*", r"crap\w*", r"wank\w*", r"twats?", r"bollocks", r"whores?",
    r"sluts?", r"slutty", r"hoes?", r"skank\w*", r"retard\w*", r"faggot\w*", r"fags?", r"dykes?", r"tranny", r"trannies",
    r"nigg\w*", r"negroe?s?", r"kikes?", r"spics?", r"chinks?", r"gooks?", r"wetbacks?", r"ragheads?", r"towelheads?",
    r"beaners?", r"coons?", r"jigaboo\w*", r"paki", r"pakis", r"cracker", r"crackers", r"honk(?:y|ies)", r"gypped",
    r"idiots?", r"idiotic", r"morons?", r"moronic", r"imbeciles?", r"stupid\w*", r"dumb", r"losers?", r"scum\w*",
    r"kill yourself", r"kys", r"shut up", r"stfu", r"wtf", r"lmao", r"lol", r"porn\w*", r"penis\w*", r"vagina\w*",
    r"dildo\w*", r"boobs?", r"tits?",
]) + r")\b", re.I)

# words and phrases that state the writer's side in the debate (role words, voting, the motion) or the stance outright
STATED_SIDE = re.compile(r"(?:" + "|".join([
    r"\bpro\b(?!-)", r"\bcon\b(?!-)", r"\bpros\b", r"\bcons\b", r"\bopponents?\b", r"\binstigator\b", r"\bcontender\b",
    r"\bchallenger\b", r"\bvot(?:e|es|ed|ers?|ing)\b", r"\bforfeit\w*", r"\bdebat\w*", r"\brounds?\b", r"\brebut\w*",
    r"\bresolution\b", r"\bmotion\b", r"\bthis house\b", r"\bproposition\b", r"\bopposition\b", r"\bproposer\b",
    r"\bburden of proof\b", r"\bbop\b", r"\bi accept\b", r"\bthanks?\b", r"\bthank you\b", r"\baffirmative\b",
    r"\bnegative side\b", r"\bcounter-?points?\b", r"\bcounter-?arguments?\b", r"\bmy side\b", r"\bthe other side\b",
    r"\bi (?:strongly |fully |completely |totally |entirely |do |would |also |still )?(?:agree|disagree|support|oppose|object)\b",
    r"\bwe (?:strongly |fully |completely |totally |do |would )?(?:agree|disagree|support|oppose)\b",
    r"\bi(?:'m| am) (?:not )?(?:for|against|anti|in favou?r|opposed|on the side|arguing|pro)\b",
    r"\bi (?:will|shall|am going to|intend to) (?:argue|show|prove|demonstrate)\b",
    r"\bi(?:'m| am) (?:not )?(?:arguing|claiming|contending)\b",
    r"\bin favou?r of (?:the|this) (?:topic|statement|claim|idea|proposal)\b",
    r"\b(?:the|this) (?:topic|statement|claim) is (?:true|false|right|wrong|correct|incorrect)\b",
]) + r")", re.I)

# an opener that answers the claim ("Pro:", "Yes,", "No, ...", "Wrong.", "No this is ...")
STATED_START = re.compile(r"^\W*(?:(?:pro|con|for|against|no|agree|disagree|support|oppose|true|false|correct|right)\b\s*"
                          r"[:,.!;\-" + DASHES + r"]|(?:yes|nope|yeah|yep|agreed|wrong|untrue|nonsense|rubbish|exactly|"
                          r"absolutely|indeed|precisely|quite|ridiculous)\b|no (?:this|that|it|they|we|i|he|she)\b)", re.I)

# a verdict on the claim being answered ("this is untrue", "this argument ignores ...")
VERDICT = re.compile(r"\b(?:this|that|it|which) (?:is|isn't|was) (?:simply |just |completely |entirely |patently |clearly |"
                     r"absolutely |totally )?(?:not true|untrue|false|wrong|incorrect|a myth|nonsense|a fallacy|misleading|"
                     r"ridiculous|absurd|correct|true|right)\b|\bthis (?:point|argument|claim|assertion|view) (?:is|fails|"
                     r"ignores|assumes|misses|overlooks|neglects)\b|\b(?:the|this) (?:point|argument|claim) (?:above|made)\b",
                     re.I)

# turns that talk to the other debater or about the exchange itself rather than the topic
DIALOGUE = re.compile(r"\b(?:you|your|yours|you're|you've|you'd|yourself|u|ur)\b|"
                      r"\bmy (?:first|second|third|next|main|final|last|own|previous|original|1st|2nd|3rd)? ?"
                      r"(?:arguments?|points?|contentions?|case|claims?|sources?|statements?)\b|"
                      r"\b(?:i will|i'll|i would like|i'd like|let me|allow me)\b|\bstated\b|\bpreviously\b|"
                      r"\bargued\b|\bargu(?:e|ing) that\b|\bwelcome\b|\bgood luck\b|\bsources?:", re.I)

# topic filters: a proposition has a finite verb (noun-ambiguous words such as "lack", "work", "benefits" do not count),
# or is a policy motion in the imperative
VERBS = frozenset("""is are was were be been being isn't aren't wasn't weren't should shouldn't must mustn't can cannot
can't could couldn't will won't would wouldn't shall ought may might has have had hasn't haven't does do did doesn't don't
didn't exists exist deserves makes leads harms helps improves outweighs prevents reduces increases violates threatens
undermines promotes encourages creates destroys saves kills contributes matters belongs protects hurts affects provides
requires existed killed caused created led won lost fails failed worked offers gives allows ensures discourages enables
denies reflects""".split())
IMPERATIVE = frozenset("""ban legalize legalise abolish introduce allow end require raise lower prohibit adopt make create
reduce increase stop use impose implement criminalise criminalize decriminalise decriminalize permit privatise privatize
nationalise nationalize subsidise subsidize establish replace remove cut grant give provide fund enforce limit restrict cap
mandate outlaw scrap withdraw join leave lift build tax punish protect recognise recognize""".split())
TOPIC_META = re.compile(r"\b(?:debat\w*|rounds?|battles?|rap|tournament|contest|mafia|troll\w*|jokes?|funny|poem|poetry|"
                        r"vs|versus|who would win|my|me|i|i'm|you|your|you're|yours|opponent|vote|voting|winner|"
                        r"part \d+|\d+(?:st|nd|rd|th) round)\b", re.I)


@functools.lru_cache(maxsize=None)
def topic_ok(topic: str) -> bool:
    if not topic or "?" in topic or topic.endswith(("...", "…")):
        return False
    w = re.findall(r"[A-Za-z']+", topic.lower())
    if not 3 <= len(w) <= 30 or TOPIC_META.search(topic) or ABUSIVE.search(topic):
        return False
    return bool(VERBS & set(w)) or w[0] in IMPERATIVE


def argument_ok(text: str, topic: str) -> bool:
    if n_words(text) < MIN_WORDS:
        return False
    for pat in (ABUSIVE, STATED_SIDE, STATED_START, VERDICT, DIALOGUE):
        if pat.search(text):
            return False
    nt, na = norm(topic), norm(text)
    if len(nt.split()) >= 3 and f" {nt} " in f" {na} ":  # quotes the whole topic
        return False
    return nt != na


# -------------------------------------------------------------------------------------------------------- wording

# (topic label, argument label, question, option "for", option "against", topic first?)
TEMPLATES = [
    ("Claim", "Passage", "Does the passage argue for the claim or against it?",
     "It argues for the claim.", "It argues against the claim.", True),
    ("Statement under discussion", "Contribution", "What position does this contribution take on the statement?",
     "It backs the statement.", "It rejects the statement.", True),
    ("Debate proposition", "Excerpt", "Which side of the proposition is the excerpt on?",
     "The side in favour of it.", "The side opposed to it.", True),
    ("Position", "Text", "Read the text and decide its stance toward the position.",
     "Pro: it defends the position.", "Con: it attacks the position.", False),
    ("Thesis", "Someone wrote", "Is the writer making a case for the thesis or a case against it?",
     "A case for the thesis.", "A case against the thesis.", True),
    ("Proposal", "Comment", "Classify the comment's stance on the proposal.",
     "Supportive of the proposal.", "Opposed to the proposal.", False),
    ("Assertion", "Reasoning offered", "Would the author of this reasoning accept or reject the assertion?",
     "Accept: the reasoning favours it.", "Reject: the reasoning disputes it.", True),
]


def render(topic: str, text: str, pro: bool, r) -> dict:
    tl, al, question, opt_for, opt_against, topic_first = TEMPLATES[r.randrange(len(TEMPLATES))]
    if topic_first:
        body = f"{tl}: {topic}\n{al}: {text}\n\n{question}"
    else:
        body = f"{question}\n\n{tl}: {topic}\n{al}: {text}"
    criteria, expected = C.mc([opt_for, opt_against], 0 if pro else 1, r)
    return {"instructions": body, "criteria": criteria, "expected": expected}


# ---------------------------------------------------------------------------------------------------------- build

def portal(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def load_candidates(path: Path) -> list[dict]:
    """Every usable argument of the chosen portals, in file order, after cleaning and the scrub filters."""
    needles = tuple(f"://{p}/" for p in PORTAL_SHARE)
    out = []
    labels = collections.defaultdict(set)
    seen = set()
    for line in open(path, encoding="utf-8"):
        if not any(n in line for n in needles):  # cheap pre-filter; the portal is checked on the parsed record below
            continue
        d = json.loads(line)
        site = portal(d.get("context", {}).get("sourceUrl", ""))
        if site not in PORTAL_SHARE or len(d.get("premises") or []) != 1:
            continue
        p = d["premises"][0]
        stance = p.get("stance")
        if stance not in ("PRO", "CON"):
            continue
        key = norm(p.get("text", ""))
        labels[key].add(stance)
        if key in seen:  # repeated text: keep the first copy only
            continue
        seen.add(key)
        topic = collapse(d.get("conclusion", ""))
        if not topic_ok(topic):
            continue
        text = trim_reference(clean(p.get("text", "")))
        text = cut(text) if text else None
        if text is None or not argument_ok(text, topic):
            continue
        out.append({"id": d["id"], "topic": topic, "group": norm(topic), "text": text, "pro": stance == "PRO",
                    "portal": site, "key": key, "prefix": " ".join(norm(text).split()[:PREFIX_WORDS]),
                    "discussion": norm(d.get("context", {}).get("discussionTitle", ""))})
    return [c for c in out if len(labels[c["key"]]) == 1]  # a text seen with both labels is dropped


def components(cands: list[dict]) -> dict[str, str]:
    """Union-find over topics joined by a shared discussion title or argument prefix; topic group -> component key."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for c in cands:
        if c["discussion"]:
            union("t:" + c["group"], "d:" + c["discussion"])
        union("t:" + c["group"], "p:" + c["prefix"])
    return {c["group"]: find("t:" + c["group"]) for c in cands}


def pick(cands: list[dict], split: str, target: int) -> list[dict]:
    """``target`` items, PRO and CON exactly half each, every portal exactly half PRO and half CON, at most TOPIC_CAP
    items per topic. Each portal gets its PORTAL_SHARE of each class, less if it has too few items of the scarcer class
    (the largest portal then takes the rest)."""
    order = sorted(cands, key=lambda c: C.unit("pick", TASK, c["id"]))
    per_class = target // 2
    avail = collections.Counter()
    seen_topic: dict = collections.defaultdict(collections.Counter)
    for c in order:
        cell = (c["portal"], c["pro"])
        if seen_topic[cell][c["group"]] < TOPIC_CAP[split]:
            seen_topic[cell][c["group"]] += 1
            avail[cell] += 1
    portals = sorted(PORTAL_SHARE, key=lambda p: PORTAL_SHARE[p])  # smallest share first, the largest takes the rest
    quota, left = {}, per_class
    for p in portals[:-1]:
        quota[p] = min(round(per_class * PORTAL_SHARE[p]), avail[(p, True)], avail[(p, False)])
        left -= quota[p]
    quota[portals[-1]] = left
    taken: list[dict] = []
    n_topic = collections.Counter()
    n_cell = collections.Counter()
    for c in order:
        cell = (c["portal"], c["pro"])
        if n_topic[c["group"]] >= TOPIC_CAP[split] or n_cell[cell] >= quota[c["portal"]]:
            continue
        taken.append(c)
        n_topic[c["group"]] += 1
        n_cell[cell] += 1
    want = {(p, s): quota[p] for p in PORTAL_SHARE for s in (True, False)}
    if dict(n_cell) != want:
        raise SystemExit(f"{split}: got {dict(n_cell)}, wanted {want}")
    return taken


def main() -> None:
    C.hf_file(TASK, REPO, REVISION, README_FILE)
    data = C.hf_file(TASK, REPO, REVISION, DATA_FILE, DATA_SHA)
    base = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/"
    C.record_source(TASK, [{"name": README_FILE, "url": base + README_FILE}, {"name": DATA_FILE, "url": base + DATA_FILE}],
                    LICENCE, LICENCE_URL,
                    notes=(f"Builder {VERSION}. Label = the premise's structured stance field (PRO/CON) towards the record's "
                           "conclusion; the dataset's loading script args_me.py was not downloaded or run. Topic = "
                           "conclusion, argument = premise text, cleaned and cut to whole sentences within "
                           f"{MAX_CHARS} characters; portals {sorted(PORTAL_SHARE)}; filters in "
                           "tools/records/build_stance.py. Group key (source_id) = normalised conclusion; the split is the "
                           "hash of the component joining topics that share a discussion title or an argument prefix."))
    cands = load_candidates(data)
    comp = components(cands)
    by_split = collections.defaultdict(list)
    for c in cands:
        by_split[C.split_of(TASK, comp[c["group"]])].append(c)
    meta = C.dev_meta(TASK)
    rows, mix = {}, {}
    for split, target in (("train", TRAIN_TARGET), ("select", C.SPLIT_SIZES["select"]), ("test", C.SPLIT_SIZES["test"])):
        chosen = pick(by_split[split], split, target)
        mix[split] = dict(sorted(collections.Counter(f"{c['portal']}:{'PRO' if c['pro'] else 'CON'}" for c in chosen).items()))
        rows[split] = [C.row(TASK, meta, SOURCE, c["group"],
                             [render(c["topic"], c["text"], c["pro"], C.rng(TASK, VERSION, c["id"]))]) for c in chosen]
    counts = C.write_splits(TASK, rows, TRAIN_TARGET)
    pool = {s: len(v) for s, v in sorted(by_split.items())}
    print(json.dumps({"task": TASK, "version": VERSION, "candidates": len(cands), "pool": pool, "mix": mix,
                      "counts": counts}))


if __name__ == "__main__":
    main()
