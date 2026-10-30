"""T type ``nli``: natural-language inference items from MultiNLI (non-fiction genres only).

    python -I tools/records/build_nli.py

Source: nyu-mll/multi_nli on Hugging Face at a pinned revision, train split only. Only the genres government, slate,
telephone and travel are used (their OANC text is under the permissive OANC licence); fiction is excluded because one of
its works is CC BY-SA 3.0 and the rows do not say which. Labels come from the structured ``label`` field
(0 entailment, 1 neutral, 2 contradiction); label -1 (no gold) is dropped.

Group key = MultiNLI ``promptID`` (one premise and its hypotheses): the split comes from its hash, so all hypotheses of a
premise share one split. At most one pair per premise is used, so 3,300 items cover 3,300 different premises.
Each split holds exactly equal thirds of the three labels. Wording (layout, question, option phrasing) is drawn per item;
the three options of an item always come from one phrasing set.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq  # noqa: E402

from tools.records import common as C  # noqa: E402

TASK = "nli"
REPO = "nyu-mll/multi_nli"
REVISION = "da70db2af9d09693783c3320c4249840212ee221"
PATH = "data/train-00000-of-00001.parquet"
SHA256 = "1c1de03640b168e410aabfca19e7cc2f3dfcd7f0e126e935674e56fb102c4529"
SOURCE = "multinli_train_oanc_da70db2"
GENRES = ("government", "slate", "telephone", "travel")   # fiction excluded (licence)
LABELS = {0: "entailment", 1: "neutral", 2: "contradiction"}
TRAIN_TARGET = 3000
PER_LABEL = {"train": TRAIN_TARGET // 3, "select": C.SPLIT_SIZES["select"] // 3, "test": C.SPLIT_SIZES["test"] // 3}
MIN_WORDS = 3

LICENCE = ("OANC licence (permissive: free to use, modify and share) for the MultiNLI government, slate, telephone and "
           "travel genres, per the MultiNLI data statement (Williams, Nangia and Bowman 2018); the fiction genre is "
           "excluded because one of its works is CC BY-SA 3.0 and rows do not identify it")
LICENCE_URL = "https://anc.org/OANC/license.txt"
NOTES = ("MultiNLI 1.0 train split (nyu-mll/multi_nli @ " + REVISION + "). Data statement: "
         "https://cims.nyu.edu/~sbowman/multinli/ and https://aclanthology.org/N18-1101/. Used genres: "
         + ", ".join(GENRES) + "; fiction excluded. Label from the 'label' field (0 entailment, 1 neutral, "
         "2 contradiction); label -1 dropped; pairs whose premise or hypothesis has fewer than 3 words dropped; pairs "
         "whose premise or hypothesis text equals a dev-set one dropped; duplicate (premise, hypothesis) pairs dropped. "
         "Group key = promptID; split = sha256 hash of the group key; at most one pair per premise; equal label thirds per "
         "split. Premise and hypothesis keep their own wording (whitespace collapsed only).")

# Layouts: the two field labels shown in the record and the nouns the question and the options use for them.
FRAMES = (
    ("Premise", "Hypothesis", "the premise", "the hypothesis"),
    ("Passage", "Statement", "the passage", "the statement"),
    ("Text", "Claim", "the text", "the claim"),
    ("Sentence 1", "Sentence 2", "sentence 1", "sentence 2"),
    ("Context", "Conclusion", "the context", "the conclusion"),
)

# Questions; {p} / {h} are the nouns of the frame.
QUESTIONS = (
    "What is the logical relationship between {p} and {h}?",
    "Taking {p} as true, what can be said about {h}?",
    "Classify {h} with respect to {p}.",
    "Assume everything in {p} is accurate. Which option best describes {h}?",
    "Judging only by {p}, without outside knowledge, how should {h} be labelled?",
    "Which inference label fits this pair?",
    "Decide how {p} bears on {h}.",
)

# Option phrasing sets: (entailment, neutral, contradiction). The three texts of a set name the same nouns.
OPTION_SETS = (
    ("{H} is entailed by {p}.", "{H} is neutral with respect to {p}.", "{H} is contradicted by {p}."),
    ("Entailment: {p} guarantees {h}.", "Neutral: {p} neither guarantees nor excludes {h}.",
     "Contradiction: {p} excludes {h}."),
    ("If {p} is accurate, {h} must also be true.", "If {p} is accurate, {h} could be either true or false.",
     "If {p} is accurate, {h} must be false."),
    ("entailment", "neutral", "contradiction"),
    ("{H} is supported by {p}.", "{H} is neither supported nor refuted by {p}.", "{H} is refuted by {p}."),
    ("Definitely true, given {p}", "Possibly true, given {p}", "Definitely false, given {p}"),
    ("{P} implies {h} (entailment)", "{P} leaves {h} undecided (neutral)", "{P} conflicts with {h} (contradiction)"),
)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def dev_texts() -> set[str]:
    """Normalised premise / hypothesis lines of the dev set's nli rows (dev uses SNLI; this is a belt-and-braces skip)."""
    import json

    out = set()
    for line in open(C.DEV, encoding="utf-8"):
        d = json.loads(line)
        if d["task_type"] != TASK:
            continue
        for q in d["questions"]:
            for ln in q["instructions"].split("\n"):
                if ":" in ln:
                    out.add(norm(ln.split(":", 1)[1]))
    out.discard("")
    return out


def render(premise: str, hypothesis: str, label: int, key: str) -> dict:
    r = C.rng(TASK, "render", key)
    p_lab, h_lab, p, h = FRAMES[r.randrange(len(FRAMES))]
    question = cap(QUESTIONS[r.randrange(len(QUESTIONS))].format(p=p, h=h))
    record = f"{p_lab}: {premise}\n{h_lab}: {hypothesis}"
    instructions = f"{question}\n\n{record}" if r.random() < 0.3 else f"{record}\n\n{question}"
    texts = [t.format(p=p, h=h, P=cap(p), H=cap(h)) for t in OPTION_SETS[r.randrange(len(OPTION_SETS))]]
    criteria, expected = C.mc(texts, label, r)
    return {"instructions": instructions, "criteria": criteria, "expected": expected}


def main() -> None:
    path = C.hf_file(TASK, REPO, REVISION, PATH, SHA256)
    C.record_source(TASK, [{"name": path.name, "url": f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{PATH}"}],
                    LICENCE, LICENCE_URL, NOTES)
    meta = C.dev_meta(TASK)
    t = pq.read_table(path, columns=["promptID", "pairID", "premise", "hypothesis", "genre", "label"])
    cols = {c: t.column(c).to_pylist() for c in t.column_names}
    skip = dev_texts()

    cands = []
    pair_seen: dict[tuple[str, str], int] = {}
    for pid, pair, prem, hyp, genre, label in zip(cols["promptID"], cols["pairID"], cols["premise"], cols["hypothesis"],
                                                  cols["genre"], cols["label"]):
        if genre not in GENRES or label not in LABELS:
            continue
        prem, hyp = clean(prem), clean(hyp)
        if len(prem.split()) < MIN_WORDS or len(hyp.split()) < MIN_WORDS:
            continue
        np_, nh = norm(prem), norm(hyp)
        if np_ in skip or nh in skip or not np_ or not nh:
            continue
        k = (np_, nh)
        pair_seen[k] = pair_seen.get(k, 0) + 1
        cands.append((C.unit("pick", TASK, pair), str(pid), pair, prem, hyp, label, k))

    # A premise text that occurs under promptIDs in different splits is a near-copy across splits: drop it.
    prem_splits: dict[str, set[str]] = {}
    for c in cands:
        prem_splits.setdefault(c[6][0], set()).add(C.split_of(TASK, c[1]))

    cands.sort()
    quota = {s: {lab: PER_LABEL[s] for lab in LABELS} for s in PER_LABEL}
    used_group: set[str] = set()
    used_prem: set[str] = set()
    used_hyp: set[str] = set()
    rows: dict[str, list[dict]] = {s: [] for s in PER_LABEL}
    for _, pid, pair, prem, hyp, label, k in cands:
        if pair_seen[k] > 1 or len(prem_splits[k[0]]) > 1:
            continue
        split = C.split_of(TASK, pid)
        if quota[split][label] == 0 or pid in used_group or k[0] in used_prem or k[1] in used_hyp:
            continue
        quota[split][label] -= 1
        used_group.add(pid)
        used_prem.add(k[0])
        used_hyp.add(k[1])
        rows[split].append(C.row(TASK, meta, SOURCE, pid, [render(prem, hyp, label, pair)]))
    short = {s: q for s, q in quota.items() if any(q.values())}
    if short:
        raise SystemExit(f"{TASK}: label quotas not filled: {short}")
    counts = C.write_splits(TASK, rows, TRAIN_TARGET)
    print(TASK, counts)


if __name__ == "__main__":
    main()
