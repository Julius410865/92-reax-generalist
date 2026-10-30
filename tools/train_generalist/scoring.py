"""Scores of one model's answers on a prepared eval split, and paired comparisons of two models on the same items.

An item counts only when all its questions are right; exact ties earn 1/k (``v5.item_table``). Each task type gets the
v5.1 chance-corrected type score (``v5.type_scores``: 0 = random or the best constant answer, 100 = perfect). Every source
(an eval entry of the stage config: ``hf``, ``dev``, ``gen``) is scored on its own:

* a source of typed v5.1 items (parts T / N) is aggregated as eval v5.1 does: T by area, N as a plain mean,
  S = 0.6 T + 0.4 N, unscaled (no panel statistics exist locally). ``dev`` is never trained on: the transfer check.
* an s1 source (the held-out HF rows, task type ``s1:<category>``) is the item-weighted mean of its category scores
  (with the licence filter some categories have only a few held-out items).

``local`` = the mean over sources (each source counts the same). ``transfer`` = every typed (v5.1-format) item of the split
pooled into one v5.1 source: the measure closest to the live eval, on which the stage and submit rules decide
(stage_check). With the dev set as the only typed source, ``transfer`` equals ``dev_v51``.
SE: paired bootstrap, resampling whole clusters (the held-out group of an s1 row, else the item) inside each task type of
each source, the same resample for both models. Rows of one template are correlated; resampling rows would understate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from reax_subnet.spec import v5

W_N = 0.4
BOOT = 1000
MIN_GROUP_ITEMS = 40       # task types / sources smaller than this are reported but never flagged as a regression


def responses_by_item(rows: Sequence[Mapping[str, Any]], probs: Sequence[Any]) -> dict[str, list]:
    """``v5wire.responses`` for prepared rows: item id -> one answer per question (None = failed, wrong for everyone)."""
    out: dict[str, list] = {}
    for r, p in zip(rows, probs):
        out.setdefault(r["item"], []).append(p)
    return out


@dataclass
class _Source:
    name: str
    items: list
    typed: bool                                   # v5.1 T / N items: aggregate as v5.1
    meta: dict
    clusters: dict = field(default_factory=dict)  # task type -> list of index arrays (one per cluster)


def _make_source(name: str, its: list) -> _Source:
    meta = {it["task_type"]: (it.get("area"), bool(it.get("gold")), it.get("part")) for it in its}
    src = _Source(name, its, any(m[2] in ("T", "N") for m in meta.values()), meta)
    for t in meta:
        cl: dict[str, list] = {}
        for i, it in enumerate(its):
            if it["task_type"] == t:
                cl.setdefault(str(it.get("group") or it["id"]), []).append(i)
        src.clusters[t] = [np.array(v) for v in cl.values()]
    return src


def _sources(items: Sequence[Mapping[str, Any]]) -> list[_Source]:
    by: dict[str, list] = {}
    for it in items:
        by.setdefault(str(it.get("source", "?")), []).append(it)
    return [_make_source(name, by[name]) for name in sorted(by)]


def _transfer(srcs: Sequence[_Source], names: Sequence[str] | None = None) -> _Source | None:
    """Every eval-v5.1-format item (the typed sources: dev, generated test files) pooled into one v5.1 source: the measure
    closest to the live eval. None without typed items. With the dev set alone it equals the dev source."""
    its = [it for s in srcs if (s.name in names if names is not None else s.typed) for it in s.items]
    return _make_source("transfer", its) if its else None


def _table(src: _Source, responses: Mapping[str, Any]):
    return v5.item_table(src.items, {it["id"]: _one(responses.get(it["id"]), len(it["questions"])) for it in src.items})


def _one(v, n):
    if v is None:
        return None
    return v[0] if n == 1 and isinstance(v, list) and len(v) == 1 else v


def _src_score(src: _Source, t, w: np.ndarray | None) -> tuple[float | None, dict[str, float]]:
    ts = v5.type_scores(t, w)
    if not ts:
        return None, ts
    if not src.typed:           # item-weighted: a 6-item category must not count as much as a 138-item one
        n = {g: float(len(t.idx[g]) if w is None else w[t.idx[g]].sum()) for g in ts}
        tot = sum(n.values())
        return (float(sum(ts[g] * n[g] for g in ts) / tot) if tot > 0 else None), ts
    tt = {g: s for g, s in ts.items() if src.meta[g][2] == "T"}
    nn = {g: s for g, s in ts.items() if src.meta[g][2] == "N"}
    T = v5.aggregate_areas(tt, src.meta)[0] if tt else None
    N = v5.aggregate_tasks(nn)
    if T is None and N is None:
        return float(np.mean(list(ts.values()))), ts
    return (T if N is None else N if T is None else (1 - W_N) * T + W_N * N), ts


def _summary(srcs: Sequence[_Source], tables: Sequence[Any], ws: Sequence[np.ndarray | None] | None = None,
             tr: _Source | None = None, ttab: Any = None, tw: np.ndarray | None = None) -> dict[str, Any]:
    ws = ws or [None] * len(srcs)
    sources, groups = {}, {}
    for src, t, w in zip(srcs, tables, ws):
        s, ts = _src_score(src, t, w)
        sources[src.name] = s
        groups.update({f"{src.name}/{g}": v for g, v in ts.items()})
    vals = [v for v in sources.values() if v is not None]
    return {"local": float(np.mean(vals)) if vals else None, "dev_v51": sources.get("dev"),
            "transfer": _src_score(tr, ttab, tw)[0] if tr is not None else None, "sources": sources, "groups": groups}


def score(items: Sequence[Mapping[str, Any]], responses: Mapping[str, Any],
          transfer_sources: Sequence[str] | None = None) -> dict[str, Any]:
    srcs = _sources(items)
    tables = [_table(s, responses) for s in srcs]
    tr = _transfer(srcs, transfer_sources)
    out = _summary(srcs, tables, tr=tr, ttab=_table(tr, responses) if tr else None)
    correct = np.concatenate([t.correct for t in tables]) if tables else np.zeros(0)
    out["items"] = len(items)
    out["item_accuracy"] = float(correct.mean()) if len(correct) else None
    out["group_items"] = {f"{s.name}/{g}": int(sum(len(c) for c in cl)) for s in srcs for g, cl in s.clusters.items()}
    out["source_items"] = {s.name: len(s.items) for s in srcs}
    out["failed_questions"] = sum(1 for v in responses.values() for p in (v or []) if p is None)
    return out


def _weights(src: _Source, rng: np.random.Generator) -> np.ndarray:
    """One bootstrap draw as item weights: whole clusters resampled with replacement inside every task type."""
    w = np.zeros(len(src.items))
    for cl in src.clusters.values():
        for k in rng.integers(0, len(cl), size=len(cl)):
            w[cl[k]] += 1.0
    return w


def paired(items: Sequence[Mapping[str, Any]], a: Mapping[str, Any], b: Mapping[str, Any], *, boot: int = BOOT,
           seed: int = 0, transfer_sources: Sequence[str] | None = None) -> dict[str, Any]:
    """Model a minus model b on the same items: gains and paired bootstrap SEs of ``local``, ``dev_v51``, every source and
    every task type."""
    srcs = _sources(items)
    ta, tb = [_table(s, a) for s in srcs], [_table(s, b) for s in srcs]
    tr = _transfer(srcs, transfer_sources)
    tra, trb = (_table(tr, a), _table(tr, b)) if tr else (None, None)
    sa, sb = _summary(srcs, ta, tr=tr, ttab=tra), _summary(srcs, tb, tr=tr, ttab=trb)
    rng = np.random.default_rng(seed)
    d: dict[str, list[float]] = {}

    def add(key, x, y):
        if x is not None and y is not None:
            d.setdefault(key, []).append(x - y)

    for _ in range(boot):
        ws = [_weights(s, rng) for s in srcs]
        tw = _weights(tr, rng) if tr else None
        xa, xb = _summary(srcs, ta, ws, tr, tra, tw), _summary(srcs, tb, ws, tr, trb, tw)
        add("local", xa["local"], xb["local"])
        add("dev_v51", xa["dev_v51"], xb["dev_v51"])
        add("transfer", xa["transfer"], xb["transfer"])
        for k in xa["sources"]:
            add("source:" + k, xa["sources"][k], xb["sources"].get(k))
        for k in xa["groups"]:
            add("group:" + k, xa["groups"][k], xb["groups"].get(k))

    def entry(x, y, key, n):
        v = d.get(key, [])
        return {"a": x, "b": y, "gain": None if x is None or y is None else x - y,
                "se": float(np.std(v, ddof=1)) if len(v) > 1 else None, "items": n}

    n_src = {s.name: len(s.items) for s in srcs}
    n_grp = {f"{s.name}/{g}": int(sum(len(c) for c in cl)) for s in srcs for g, cl in s.clusters.items()}
    out = {"local": entry(sa["local"], sb["local"], "local", len(items)),
           "dev_v51": entry(sa["dev_v51"], sb["dev_v51"], "dev_v51", n_src.get("dev", 0)),
           "transfer": entry(sa["transfer"], sb["transfer"], "transfer", len(tr.items) if tr else 0),
           "sources": {k: entry(sa["sources"][k], sb["sources"].get(k), "source:" + k, n_src[k]) for k in sa["sources"]},
           "groups": {k: entry(sa["groups"][k], sb["groups"].get(k), "group:" + k, n_grp[k]) for k in sa["groups"]}}
    out["changed_items"] = int(sum(np.sum(np.abs(x.correct - y.correct) > 1e-12) for x, y in zip(ta, tb)))
    out["items"] = len(items)
    return out
