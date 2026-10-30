"""intent_utterance: a user utterance -> which intent, over the FULL intent list of the utterance's source.

    python -I tools/records/build_intent_utterance.py

Sources (pinned, sha256-checked; raw files are parsed as data, nothing in them is executed):

* CLINC150 (clinc/clinc_oos, config ``plus``, train + validation parquet; CC BY 3.0). The out-of-scope intent ``oos`` is
  dropped, leaving 150 intents. Intent names come from the parquet's ``huggingface`` schema metadata.
* Banking77 (PolyAI, CC BY 4.0). The HF repo only holds a loading script; it is downloaded as text (``banking77.py.txt``),
  never run, and only checked to point at the PolyAI GitHub CSVs, which are fetched at a pinned commit (train.csv only;
  the official test.csv is left untouched). Intent names come from ``categories.json``.

One question per item; the options are the source's whole intent list (150 or 77, two-letter codes after Z) in a per-item
shuffled order. The two sources' label sets are never mixed. Group key (source_id) = source name + normalised utterance;
exact duplicates stay in one group, and a group whose copies carry different intents is dropped. Train is balanced by a
round robin over intents (no intent above 3x the median train count, asserted).
"""
from __future__ import annotations

import collections
import csv
import io
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.records import common as C  # noqa: E402

TASK = "intent_utterance"
VERSION = "iu-1"
PER_SOURCE = {"train": 1500, "select": 75, "test": 75}

CLINC_REPO, CLINC_REV = "clinc/clinc_oos", "155b9c710419136e17307b80d0a13e68cd46b4ec"
B77_REPO, B77_REV = "PolyAI/banking77", "90d4e2ee5521c04fc1488f065b8b083658768c57"
GH_REPO, GH_REV = "PolyAI-LDN/task-specific-datasets", "57ec275d8078af65b7731c2a98be812d844a6d6b"
GH_RAW = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_REV}/"
HF = "https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}"

# name -> (url, sha256)
FILES = {
    "clinc__plus__train-00000-of-00001.parquet": (
        HF.format(repo=CLINC_REPO, rev=CLINC_REV, path="plus/train-00000-of-00001.parquet"),
        "30188119cf9f86fc9db27e1c22442d091cb5cb0913c9496f945fe11e7a02a28f"),
    "clinc__plus__validation-00000-of-00001.parquet": (
        HF.format(repo=CLINC_REPO, rev=CLINC_REV, path="plus/validation-00000-of-00001.parquet"),
        "fbd545b46c611c4a7ba4b48cae6c7f09bb5b59f33ff56206ad1cd366c85cdfaa"),
    "clinc__README.md": (
        HF.format(repo=CLINC_REPO, rev=CLINC_REV, path="README.md"),
        "e28704a3c04f6b05c286ca2a8891bbf32c69c000dedfc5825d6e1713369b7a89"),
    "banking77__README.md": (
        HF.format(repo=B77_REPO, rev=B77_REV, path="README.md"),
        "b494ae99274ad98adfedfefcb504469197a8732f9726f678320f4aaafc5502bf"),
    "banking77__banking77.py.txt": (
        HF.format(repo=B77_REPO, rev=B77_REV, path="banking77.py"),
        "0e2b20c18def828886300332b15c6f647b77cdc289d1b49fffe65d8fde1d0834"),
    "banking77__train.csv": (
        GH_RAW + "banking_data/train.csv",
        "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b"),
    "banking77__categories.json": (
        GH_RAW + "banking_data/categories.json",
        "53261da888122daf2d120d925458631d9619e15d82e56052e7a42e535ce32b63"),
    "banking77__LICENSE": (
        GH_RAW + "LICENSE",
        "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661"),
}

SOURCES = {
    "clinc150": {"source": "clinc150_plus_155b9c7_cc_by_3", "label": "CLINC150 (clinc/clinc_oos, plus)"},
    "banking77": {"source": "banking77_57ec275_cc_by_4", "label": "Banking77 (PolyAI)"},
}

LICENCE = "CLINC150: CC BY 3.0; Banking77: CC BY 4.0"
LICENCE_URL = ("CLINC150: https://creativecommons.org/licenses/by/3.0/ (dataset card "
               f"https://huggingface.co/datasets/{CLINC_REPO}); Banking77: https://creativecommons.org/licenses/by/4.0/ "
               f"(https://github.com/{GH_REPO}/blob/{GH_REV}/LICENSE)")
ATTRIBUTION = (
    "CLINC150: Larson et al., 'An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction', EMNLP-IJCNLP "
    "2019; data by Clinc, Inc., https://github.com/clinc/oos-eval, CC BY 3.0. "
    "Banking77: Casanueva et al., 'Efficient Intent Detection with Dual Sentence Encoders', NLP4ConvAI 2020; data by "
    "PolyAI, https://github.com/PolyAI-LDN/task-specific-datasets, CC BY 4.0. "
    "Changes: utterances wrapped in question templates, intent names shown with underscores as spaces (lower case), "
    "CLINC out-of-scope class dropped, duplicates and conflicting labels removed, subsampled.")

# Own wording; {u} = the utterance, {where} = a source-specific setting.
WHERE = {"clinc150": ["a general-purpose virtual assistant", "a voice-and-text personal assistant"],
         "banking77": ["a bank's customer-support chat", "the help chat of a mobile banking app"]}
TEMPLATES = [
    'Customer message: "{u}"\n\nWhich listed intent best describes what this person wants?',
    "The following request was typed into {where}:\n{u}\n\nPick the intent label it should be routed to.",
    "Classify the intent of this user query.\n\nQuery: {u}",
    'Utterance: "{u}"\n\nWhat is the speaker trying to get done? Choose the matching intent.',
    'Someone wrote to {where}: "{u}"\n\nWhich intent category fits the message?',
    "Route this message to exactly one intent.\n\nMessage: {u}\n\nWhich intent applies?",
    'Here is what a user said: "{u}"\nSelect the intent that the request expresses.',
]


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def readable(name: str) -> str:
    return name.replace("_", " ").strip().lower()


def load_clinc(paths: dict[str, Path]) -> tuple[list[str], list[tuple[str, str]]]:
    import pyarrow.parquet as pq

    names = None
    recs = []
    for key in ("clinc__plus__train-00000-of-00001.parquet", "clinc__plus__validation-00000-of-00001.parquet"):
        t = pq.read_table(paths[key])
        n = json.loads(t.schema.metadata[b"huggingface"])["info"]["features"]["intent"]["names"]
        if names is not None and n != names:
            raise SystemExit("CLINC: label names differ between files")
        names = n
        for r in t.to_pylist():
            recs.append((clean(r["text"]), names[r["intent"]]))
    assert len(names) == 151 and "oos" in names, len(names)
    labels = [x for x in names if x != "oos"]
    return labels, [(u, l) for u, l in recs if l != "oos"]


def load_banking(paths: dict[str, Path]) -> tuple[list[str], list[tuple[str, str]]]:
    script = paths["banking77__banking77.py.txt"].read_text(encoding="utf-8")  # read as text only, never executed
    if "PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv" not in script:
        raise SystemExit("banking77.py no longer points at the PolyAI GitHub train.csv")
    labels = json.loads(paths["banking77__categories.json"].read_text(encoding="utf-8"))
    assert len(labels) == 77 and len(set(labels)) == 77
    missing = [x for x in labels if f'"{x}"' not in script]
    if missing:
        raise SystemExit(f"categories.json names not in the loading script: {missing}")
    rd = csv.reader(io.StringIO(paths["banking77__train.csv"].read_text(encoding="utf-8")), quotechar='"',
                    delimiter=",", quoting=csv.QUOTE_ALL, skipinitialspace=True)
    assert next(rd) == ["text", "category"]
    recs = []
    known = set(labels)
    for r in rd:
        if len(r) != 2 or r[1] not in known:
            raise SystemExit(f"banking77: bad row {r!r}")
        recs.append((clean(r[0]), r[1]))
    return labels, recs


def dev_utterances() -> set[str]:
    out = set()
    for line in open(C.DEV, encoding="utf-8"):
        d = json.loads(line)
        if d["task_type"] == TASK:
            for q in d["questions"]:
                out.update(norm(m) for m in re.findall(r'"([^"]+)"', q["instructions"]))
    return out


def main() -> None:
    paths = {name: C.fetch(TASK, url, name, sha) for name, (url, sha) in FILES.items()}
    C.record_source(TASK, [{"name": n, "url": u} for n, (u, _) in FILES.items()], LICENCE, LICENCE_URL,
                    notes=f"Builder {VERSION}. {ATTRIBUTION} CLINC150 uses plus/train + plus/validation (oos dropped); "
                          "Banking77 uses banking_data/train.csv only (the official test.csv is not used). The HF "
                          "banking77.py loading script is stored as text and never executed.")
    meta = C.dev_meta(TASK)
    dev_u = dev_utterances()

    rows = {s: [] for s in ("train", "select", "test")}
    stats: dict = {"version": VERSION, "sources": {}}
    for src, loader in (("clinc150", load_clinc), ("banking77", load_banking)):
        labels, recs = loader(paths)
        names = [readable(x) for x in labels]
        assert len(set(names)) == len(names), f"{src}: readable names collide"
        idx = {x: i for i, x in enumerate(labels)}
        groups: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
        for u, l in recs:
            if norm(u):
                groups[norm(u)].append((u, l))
        n_conflict = n_dev = 0
        cand: dict[str, dict[str, list[tuple[str, str, str]]]] = {s: collections.defaultdict(list) for s in rows}
        for key in sorted(groups):
            members = groups[key]
            if len({l for _, l in members}) > 1:
                n_conflict += 1
                continue
            if key in dev_u:
                n_dev += 1
                continue
            sid = f"{src}|{key}"
            u = sorted(m for m, _ in members)[0]
            cand[C.split_of(TASK, sid)][members[0][1]].append((sid, u, members[0][1]))
        src_stats = {"intents": len(labels), "records": len(recs), "groups": len(groups),
                     "conflicting_groups_dropped": n_conflict, "dev_matches_dropped": n_dev, "splits": {}}
        for split, target in PER_SOURCE.items():
            pools = {l: sorted(v, key=lambda x: C.unit("pick", TASK, x[0])) for l, v in cand[split].items()}
            order = sorted(pools, key=lambda l: C.unit("intent-order", TASK, src, split, l))
            picked: list[tuple[str, str, str]] = []
            depth = 0
            while len(picked) < target and any(len(pools[l]) > depth for l in order):
                for l in order:
                    if len(picked) < target and len(pools[l]) > depth:
                        picked.append(pools[l][depth])
                depth += 1
            per_intent = collections.Counter(l for _, _, l in picked)
            src_stats["splits"][split] = {"candidates": sum(len(v) for v in pools.values()), "items": len(picked),
                                          "intents_present": len(per_intent),
                                          "per_intent": {readable(l): per_intent[l] for l in labels if per_intent[l]}}
            for sid, u, l in picked:
                r = C.rng(TASK, VERSION, "item", sid)
                tpl = r.choice(TEMPLATES)
                text = tpl.format(u=u, where=r.choice(WHERE[src]))
                crit, exp = C.mc(names, idx[l], r)
                rows[split].append(C.row(TASK, meta, SOURCES[src]["source"], sid,
                                         [{"instructions": text, "criteria": crit, "expected": exp}]))
        stats["sources"][src] = src_stats

    # balance cap: no intent above 3x the median train count (intents are per source; the two label sets are distinct)
    for split in rows:
        counts = [c for s in stats["sources"].values() for c in s["splits"][split]["per_intent"].values()]
        med = statistics.median(counts)
        stats.setdefault("cap", {})[split] = {"median": med, "max": max(counts), "cap_3x_median": 3 * med}
    cap = stats["cap"]["train"]
    if cap["max"] > cap["cap_3x_median"]:
        raise SystemExit(f"train intent cap violated: {cap}")

    counts = C.write_splits(TASK, rows, train_target=PER_SOURCE["train"] * len(SOURCES))
    stats["counts"] = counts
    (C.RAW / TASK / "build_stats.json").write_text(json.dumps(stats, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"counts": counts, "cap": stats["cap"]}))


if __name__ == "__main__":
    main()
