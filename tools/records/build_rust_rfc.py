"""#2 Rust RFCs -> outcome of the RFC pull request: eval-v5.1 mirror rows (part N, task type ``rust_rfc_outcome``).

    python -I tools/records/build_rust_rfc.py --snapshot 2026-10-27

Records: the pull requests of rust-lang/rfcs from the raw GitHub REST API pull-list pages, read as data.
* Label, from structured fields only: merged (``merged_at`` set), closed without merge (state closed, ``merged_at`` empty,
  no ``postponed`` label), postponed (state closed, not merged, label ``postponed``). Second source: the accepted RFC texts
  under text/ in the repository tarball at the pinned commit (text/NNNN-name.md, NNNN the PR number, with an "RFC PR:"
  header naming the PR). Kept only where both agree: a merged PR must have its own RFC text, a closed or postponed one must
  have none and be named by no header (dropped: PRs closed on GitHub but accepted by a manual merge, and merged PRs without
  an own RFC text, such as fixes, amendments and follow-ups).
* Dropped for every class alike: open PRs (in progress); labels ``not-rfc`` (housekeeping) and ``april-1st`` (jokes); titles
  that mark an amendment or housekeeping (``HOUSEKEEPING``); earlier PRs of a resubmitted RFC (same normalised title: the
  latest PR is kept, so near-copies never sit in two splits); records whose title contains a SCRUB word; records with no
  description left after cleaning.
* Record text: opened date, title and the PR body, for every class (the text source does not differ by class), as plain
  text: no code blocks, URLs, images, tables, headings or link-only lines; struck-out text removed; @handles, emails and
  phone numbers masked; sentences crediting or thanking people or listing several of them removed; GitHub alert boxes
  (the PR template's boilerplate) removed; every sentence with a SCRUB word removed; cut at a sentence boundary. Not used:
  labels, state, merged / closed dates, comments, author, PR number.
* Group key: the PR number.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import random
import re
import sys
import tarfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "rust_rfc"
TASK = "rust_rfc_outcome"
AREA = "language"           # status / outcome domains, as the dev set's python_pep_status and rfc_status
EVAL_FRAC = 0.10            # fewer than ~3,300 records: about 10 % test and 10 % select
TEXT_LIMIT = 1000
MIN_DESC_WORDS = 5
LABELS = {"merged": "Merged: the RFC was accepted",
          "closed": "Closed without being merged",
          "postponed": "Postponed: closed for now, to be revisited later"}
DROP_LABELS = {"not-rfc", "april-1st"}
POSTPONED_LABEL = "postponed"
SCRUB = ("merged", "merge", "merges", "merging", "unmerged", "postponed", "postpone", "postpones", "postponing",
         "postponement", "closed", "close", "closes", "closing", "reopen", "reopened", "accepted", "accept", "accepts",
         "acceptance", "approved", "approve", "approval", "unapprove", "rejected", "reject", "rejects", "rejection",
         "declined", "decline", "withdrawn", "withdraw", "withdrew", "abandoned", "abandon", "superseded", "supersede",
         "supersedes", "obsolete", "fcp", "final comment period", "final-comment-period", "disposition", "rfcbot",
         "tracking issue", "tracking-issue", "tracking issues", "stabilized", "stabilised", "stabilization pr",
         "nightly", "landed", "in favor of", "in favour of", "revisit", "revisited", "revisiting", "status", "final",
         "finalized", "outcome", "decision", "decided", "consensus", "resolved", "concluded", "denied", "dismissed",
         "rfc pr", "rust issue")      # the last two: header fields of an accepted RFC text, filled in at the merge
SCRUB_RE = R.scrub_pattern(SCRUB)
HOUSEKEEPING = re.compile(r"\bamend(s|ed|ing|ment|ments)?\b|\btypos?\b|\breadme\b|\btemplate\b|\bspelling\b|"
                          r"\bgrammar flaw\b|\bhyper ?links?\b|\blink points\b|\b(rename|update)\s+\d{4}-|"
                          r"\b(is|as|to) complete(d)?\b", re.I)
CREDIT_RE = re.compile(r"\b(thanks?|thank you|thanking|kudos|credits?|acknowledg\w*|co-?authored|co-?written|written by|"
                       r"authored by|reported by|discovered by|found by|courtesy of|in collaboration with|with (the )?help "
                       r"(of|from)|with input from|feedback from|helped|inspired by)\b", re.I)
LINK_ONLY_WORDS = 4
LEAD_NOISE = re.compile(r"^(cc|r\?|r=|fixes|fix|refs?|see|related|previously|discussion|internals|zulip|pre-rfc)\b\W*", re.I)
QUESTIONS = ("What was the outcome of this RFC pull request?",
             "How did this RFC pull request end?",
             "What became of this RFC pull request?",
             "Which of these describes what happened to this RFC pull request?",
             "Where did this RFC pull request end up?")


# ------------------------------------------------------------------------------------------------------------ text

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w+])(\+\d{1,3}[\s.-]?\(?\d{1,4}\)?([\s.-]?\d{2,4}){2,4}|\(\d{3}\)\s?\d{3}[\s.-]\d{4})(?!\w)")
HANDLE_RE = re.compile(r"(?<![\w@./-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(/[A-Za-z0-9_.-]+)?(?![\w@])")


def mask_private(text: str) -> str:
    """Emails and phone numbers masked everywhere; @handles of people masked outside inline code (`@decorator` stays);
    team mentions (@org/team) keep the team name without the @."""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    def handles(p: str) -> str:
        return HANDLE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}" if m.group(2) else "[user]", p)
    return "".join(p if p.startswith("`") else handles(p) for p in re.split(r"(`[^`\n]+`)", text))


def inline_plain(s: str) -> tuple[str, bool]:
    """One markdown line as plain text, and whether a link or URL was removed from it."""
    had = bool(re.search(r"\]\(|https?://|www\.|<a\s", s, re.I))
    s = re.sub(r"~~.*?~~", " ", s)                                  # struck-out text: the author's own deletion
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)                       # images
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)                    # [text](url) -> text
    s = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", s)                   # [text][ref] -> text
    s = re.sub(r"<[^>\n]+>", " ", s)                                  # html tags, autolinks
    s = re.sub(r"\b(https?://|www\.)\S+", " ", s)                     # bare URLs
    s = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", s)            # bold
    s = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", s)  # *emphasis*
    s = re.sub(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])", r"\1", s)    # _emphasis_ (identifiers keep their underscores)
    return R.norm_ws(s), had


def md_units(md: str) -> list[str]:
    """A markdown body as a list of plain-text units (paragraphs and list items), each ending in sentence punctuation (a
    paragraph that leads into a list ends in ':'; a missing full stop is added, a trailing comma becomes one)."""
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    md = re.sub(r"<!--.*?(-->|\Z)", "\n", md, flags=re.S)
    md = re.sub(r"(?ms)^\s*(```|~~~).*?(^\s*\1[^\n]*$|\Z)", "\n\n", md)
    md = re.sub(r"(?is)<(details|summary|pre|code|table)\b.*?</\1>", "\n\n", md)
    units: list[tuple[str, bool, bool]] = []                          # (text, a link was removed, list item)
    for block in re.split(r"\n\s*\n", md):
        if re.match(r"^\s*>\s*\[!\w+\]", block):
            continue                                                  # GitHub alert box: the PR template's boilerplate
        cur: list[str] = []
        state = {"link": False, "item": False}

        def flush():
            nonlocal cur
            if cur:
                units.append((R.norm_ws(" ".join(cur)), state["link"], state["item"]))
            cur = []
            state["link"] = state["item"] = False
        for line in block.split("\n"):
            raw = line.rstrip()
            s = raw.strip()
            if not s:
                continue
            if s.startswith(("#", "|")) or re.match(r"^(\s{4,}|\t)", raw) and not cur or re.match(r"^([-*_=]\s*){3,}$", s) \
                    or re.match(r"^\[[^\]]+\]:\s*\S+", s):
                flush()                                               # heading, table, indented code, rule, link definition
                continue
            s = re.sub(r"^>+\s?", "", s) if s.startswith(">") else s
            item = re.match(r"^(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?(.*)$", s)
            if item:
                flush()
                s = item.group(1)
                state["item"] = True
            text, had = inline_plain(s)
            if text:
                cur.append(text)
                state["link"] = state["link"] or had
        flush()
    kept = []
    for text, had_link, is_item in units:
        if had_link and len(re.findall(r"[A-Za-z]{2,}", text)) <= LINK_ONLY_WORDS:
            continue                                                  # "Rendered", "Pre-RFC thread:", "Discussion here"
        if LEAD_NOISE.match(text) and len(text.split()) <= 6:
            continue
        if re.search(r"\brendered\b", text, re.I) and len(text.split()) <= 8:
            continue
        kept.append((text, is_item))
    out = []
    for i, (text, is_item) in enumerate(kept):
        if text.endswith((",", ";")):
            text = text[:-1].rstrip() + "."
        elif not re.search(r"[.!?:]$", text):
            text += ":" if not is_item and i + 1 < len(kept) and kept[i + 1][1] else "."
        out.append(text)
    return out


MASKED_LIST_RE = re.compile(r"\[user\].*\[user\]")


def description(body: str) -> str:
    text = " ".join(md_units(body))
    text = mask_private(text)
    text = R.drop_sentences(text, CREDIT_RE)
    text = R.drop_sentences(text, MASKED_LIST_RE)                     # lists of people (credits, cc lines)
    text = R.drop_sentences(text, SCRUB_RE)
    return R.clip(text, TEXT_LIMIT)


def clean_title(title: str) -> str:
    return mask_private(inline_plain(title or "")[0])


def title_key(title: str) -> str:
    """Normalised title, to find resubmissions of the same RFC ('RFC:' / 'WIP' prefixes, '(was #108)' notes ignored)."""
    t = (title or "").lower()
    t = re.sub(r"^\s*(\[?(pre-)?rfcs?\]?\s*[:#-]?\s*|\[wip\]\s*|wip:?\s*|\[draft\]\s*)+", "", t)
    t = re.sub(r"\(was #?\d+\)|\b(v\d+|take \d+|revised|redux|again|second attempt)\b", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ------------------------------------------------------------------------------------------------------------ records

def pulls(raw: str) -> list[dict]:
    out: dict[int, dict] = {}
    for p in sorted(glob.glob(os.path.join(raw, "pulls", "page-*.json"))):
        for pr in json.load(open(p, encoding="utf-8")):
            out[int(pr["number"])] = pr
    return [out[k] for k in sorted(out)]


def accepted_prs(raw: str) -> tuple[set[int], set[int]]:
    """The accepted RFC texts (text/*.md) of the pinned tarball: PR numbers named in their 'RFC PR:' header lines, and the
    numbers in their file names (text/NNNN-name.md, NNNN being the RFC's own PR number)."""
    named: set[int] = set()
    numbered: set[int] = set()
    tp = sorted(glob.glob(os.path.join(raw, "rfcs-*.tar.gz")))[0]
    with tarfile.open(tp, "r:gz") as tf:
        for m in tf.getmembers():
            if not (m.isfile() and re.search(r"^[^/]+/text/[^/]+\.md$", m.name)):
                continue
            num = re.match(r"^(\d+)-", os.path.basename(m.name))
            if num:
                numbered.add(int(num.group(1)))
            for line in tf.extractfile(m).read().decode("utf-8", "replace").splitlines()[:30]:
                if re.search(r"\bRFC PR\b", line, re.I):
                    named |= {int(x) for x in re.findall(r"rust-lang/rfcs(?:/pull/|/issues/|#)(\d+)", line)}
    return named, numbered


def label_of(pr: dict, accepted: tuple[set[int], set[int]]) -> str | None:
    """merged / closed / postponed from the structured fields, None if in progress, conflicting or not an RFC proposal.
    Agreement with the RFC texts: a merged PR has its own text (file number and 'RFC PR:' header), a closed one neither."""
    named, numbered = accepted
    names = {lb.get("name", "") for lb in pr.get("labels") or []}
    num = int(pr["number"])
    if pr.get("state") != "closed" or names & DROP_LABELS:
        return None
    if pr.get("merged_at"):
        return "merged" if num in named and num in numbered and POSTPONED_LABEL not in names else None
    if num in named or num in numbered:
        return None                                       # closed on GitHub, but an RFC text is its own: sources disagree
    return "postponed" if POSTPONED_LABEL in names else "closed"


def records(raw: str) -> tuple[list[dict], dict]:
    accepted = accepted_prs(raw)
    prs = pulls(raw)
    stats = {"pull_requests": len(prs), "open": 0, "not_rfc_or_joke": 0, "sources_disagree": 0, "housekeeping_title": 0,
             "earlier_resubmission": 0}
    cand = []
    for pr in prs:
        names = {lb.get("name", "") for lb in pr.get("labels") or []}
        lab = label_of(pr, accepted)
        if lab is None:
            key = "open" if pr.get("state") != "closed" else "not_rfc_or_joke" if names & DROP_LABELS else "sources_disagree"
            stats[key] += 1
            continue
        if HOUSEKEEPING.search(pr.get("title") or ""):
            stats["housekeeping_title"] += 1
            continue
        cand.append({"num": int(pr["number"]), "pr": pr, "label": lab, "key": f"rfc-pr-{int(pr['number'])}"})
    latest: dict[str, dict] = {}
    for rec in cand:                                      # PR numbers rise with the creation time: the last one wins
        tk = title_key(rec["pr"]["title"]) or str(rec["num"])
        latest[tk] = rec
    keep = {id(r) for r in latest.values()}
    out = [r for r in cand if id(r) in keep]
    stats["earlier_resubmission"] = len(cand) - len(out)
    return out, stats


def opened(pr: dict) -> dt.date | None:
    try:
        return dt.date.fromisoformat((pr.get("created_at") or "")[:10])
    except ValueError:
        return None


def render(rec: dict, rng: random.Random) -> str | None:
    pr = rec["pr"]
    title = clean_title(pr.get("title"))
    if not title or R.scrub_hits(title, SCRUB_RE):
        return None
    desc = description(pr.get("body") or "")
    if len(re.findall(r"[A-Za-z]{2,}", desc)) < MIN_DESC_WORDS:
        return None
    d = opened(pr)
    record = "\n".join([f"Rust RFC pull request (opened {d.isoformat() if d else 'unknown'})", f"Title: {title}",
                        f"Description: {desc}"])
    if R.scrub_hits(record, SCRUB_RE):      # the record text only: the question below is ours
        return None
    return record + "\n\n" + rng.choice(QUESTIONS)


def build(snapshot: str) -> dict:
    raw = os.path.join(R.RAW, DOMAIN, snapshot)
    problems = R.verify_raw(DOMAIN, snapshot)
    if problems:
        raise SystemExit(f"raw files: {problems}")
    recs, stats = records(raw)
    n_read = stats["pull_requests"]
    kept, unrendered = [], 0
    for rec in recs:
        rng = random.Random(f"{DOMAIN}|{rec['key']}")
        text = render(rec, rng)
        if text is None:
            unrendered += 1
            continue
        rec["text"], rec["split"] = text, R.split_of(DOMAIN, rec["key"], EVAL_FRAC)
        kept.append(rec)
    capped, class_report = R.cap_classes(kept, lambda r: r["label"], DOMAIN)
    final = R.take(capped, DOMAIN)
    present = {r["label"] for r in capped}
    labels = [LABELS[s] for s in LABELS if s in present]
    rows, idx = [], {s: 0 for s in R.SPLITS}
    for rec in sorted(final, key=lambda r: (r["split"], R.hash_order(DOMAIN, r["key"]))):
        rows.append(R.mc_row(domain=DOMAIN, task_type=TASK, area=AREA, split=rec["split"], index=idx[rec["split"]],
                             instructions=rec["text"], options=labels, gold=LABELS[rec["label"]], source="rust_rfc",
                             source_id=f"rust-lang/rfcs#{rec['num']}", snapshot=snapshot, record_date=opened(rec["pr"]),
                             shuffle_key=rec["key"]))
        idx[rec["split"]] += 1
    fetch = json.load(open(os.path.join(raw, "fetch.json")))
    manifest = {"domain": DOMAIN, "task_type": TASK, "area": AREA, "snapshot": snapshot, "licence": fetch.get("licence"),
                "sources": {n: {k: f[k] for k in ("url", "sha256")} for n, f in fetch["files"].items()},
                "label_field": "pull request 'merged_at' / 'state' and the 'postponed' label; agreement with the 'RFC PR:' "
                               "headers of text/*.md at the pinned commit",
                "labels": LABELS, "records_read": n_read, "selection": stats,
                "dropped_unrenderable_or_scrub": unrendered, **class_report}
    return R.write_domain(DOMAIN, rows, manifest)


# ------------------------------------------------------------------------------------------------------------ audit

def source_url(row: dict, snapshot: str) -> str:
    return f"https://github.com/rust-lang/rfcs/pull/{row['source_id'].rsplit('#', 1)[1]}"


_CACHE: dict[str, tuple[dict[int, dict], set[str]]] = {}


def _raw_cache(snapshot: str) -> tuple[dict[int, dict], set[str]]:
    """PR number -> raw pull-list entry, and the file names under text/ in the tarball, read once per process."""
    if snapshot not in _CACHE:
        raw = os.path.join(R.RAW, DOMAIN, snapshot)
        prs = {}
        for p in glob.glob(os.path.join(raw, "pulls", "page-*.json")):
            for pr in json.load(open(p, encoding="utf-8")):
                prs[pr["number"]] = pr
        with tarfile.open(glob.glob(os.path.join(raw, "rfcs-*.tar.gz"))[0], "r:gz") as tf:
            names = {m.name.split("/text/", 1)[1] for m in tf.getmembers() if m.isfile() and "/text/" in m.name}
        _CACHE[snapshot] = (prs, names)
    return _CACHE[snapshot]


def recheck(row: dict, snapshot: str) -> tuple[str | None, bool]:
    """The outcome read again from the raw page entry (merged_at, state, label names) and checked against the file names
    under text/ alone (an accepted RFC is text/NNNN-name.md with NNNN its PR number), and whether the item's title line is
    the PR's own title."""
    num = int(row["source_id"].rsplit("#", 1)[1])
    prs, names = _raw_cache(snapshot)
    pr = prs.get(num)
    if pr is None:
        return None, False
    has_text = any(n.startswith(f"{num:04d}-") and n.endswith(".md") for n in names)
    labels = [lb["name"] for lb in pr["labels"]]
    if pr["state"] != "closed":
        label = None
    elif pr["merged_at"]:
        label = "merged" if has_text else None
    elif has_text:
        label = None
    else:
        label = "postponed" if "postponed" in labels else "closed"
    title_line = row["questions"][0]["instructions"].split("\n")[1]
    text_ok = R.norm_ws(title_line.removeprefix("Title: ")) == R.norm_ws(clean_title(pr["title"]))
    return LABELS.get(label), text_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args(argv)
    m = build(a.snapshot)
    for s in R.SPLITS:
        sp = m["splits"][s]
        print(f"{s}: {sp['rows']} rows, classes {sp['class_prior']}, gold position {sp['gold_position']}, "
              f"fresh {sp['fresh']}")
    print(f"records read {m['records_read']}, selection {m['selection']}, dropped (scrub / no text) "
          f"{m['dropped_unrenderable_or_scrub']}, classes dropped {m['classes_dropped_under_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
