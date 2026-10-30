"""chess_best_move: find the solution move of a real Lichess tactics puzzle (T type, area knowledge, not gold).

    python -I tools/records/build_chess_best_move.py

Source: Lichess puzzle database as published on Hugging Face (Lichess/chess-puzzles, CC0 1.0), one pinned parquet shard.

Lichess convention: the FEN is the position BEFORE the opponent's move; Moves[0] is the opponent's move and the solution
starts with Moves[1]. We push Moves[0], the side to move is the solver, and the gold option is Moves[1] in SAN. The options
are every legal move of that position in SAN, shuffled per item. Every written item is replayed with python-chess and
checked (``self_check``) before the files are written.

Selection (all deterministic, by hash order of the puzzle id):
* Popularity >= 80, NbPlays >= 200, 700 <= Rating <= 2600, at least 4 legal moves for the solver;
* four rating bands (700-1199, 1200-1699, 1700-2199, 2200-2600) with a quarter of each split each;
* at most 18 % mate-in-one puzzles per band and split (so at most 20 % overall);
* longest-option cap: puzzle solutions are often captures with check (``Qxf7+``), so among questions with at most 26
  options "pick the longest SAN string" would beat chance by ~0.23. Within each split an item with <= 26 options is only
  accepted while the running longest-option accuracy of those items stays within chance + 0.10 (ties count 1/k, as in
  tools/check_generalist.py). Options stay plain SAN (check marks and capture signs are kept);
* one puzzle per Lichess game, and no repeated position; the group key (``source_id``) is the game id, so all
  puzzles of one game would land in the same split.

Gold-position balance: questions with at most 6 options get their gold position from a per-option-count rotation over
the final rows (the remaining options are still shuffled by ``common.rng``); with so few options a purely random shuffle
over a few dozen items drifts more than the checker's +-5 pts. Questions with 7+ options are shuffled fully at random.
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import chess  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from tools.records import common as C  # noqa: E402

TASK = "chess_best_move"
VERSION = "chess-1"
REPO = "Lichess/chess-puzzles"
REVISION = "461725966ea46898ec6481372a6326de3281bfbd"
SHARD = "data/train-00000-of-00003.parquet"
SHARD_SHA256 = "5352e3bff4d6163851c07a0cc922b1ff72875cc6f75d994bdfc3272a37ca9e87"
SOURCE = f"lichess_puzzles_{REVISION[:10]}"
LICENCE = "CC0 1.0 (Lichess puzzle database)"
LICENCE_URL = "https://database.lichess.org/#puzzles"

COLUMNS = ["PuzzleId", "GameId", "FEN", "Moves", "Rating", "Popularity", "NbPlays", "Themes"]
MIN_POPULARITY, MIN_PLAYS, MIN_RATING, MAX_RATING = 80, 200, 700, 2600
BANDS = [(700, 1199), (1200, 1699), (1700, 2199), (2200, 2600)]
MIN_LEGAL = 4
MATE1_SHARE = 0.18
TARGET = {"train": 2000, "select": 150, "test": 150}
SMALL_K = 6
SERVED = 26          # options served live per question; the checker's shortcut test looks at these questions
CUE_SLACK = 0.10     # longest-option accuracy may exceed chance by at most this much (checker allows 0.15)

PIECE_NAMES = {chess.KING: "king", chess.QUEEN: "queen", chess.ROOK: "rook", chess.BISHOP: "bishop",
               chess.KNIGHT: "knight", chess.PAWN: "pawn"}
PIECE_ORDER = [chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]


def game_id(raw: str) -> str:
    """'787zsVup/black#48' or 'F8M8OS71#53' -> the 8-character Lichess game id."""
    return raw.split("#", 1)[0].split("/", 1)[0]


def band_of(rating: int) -> int:
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= rating <= hi:
            return i
    raise ValueError(rating)


def band_quota(total: int) -> list[int]:
    base, extra = divmod(total, len(BANDS))
    return [base + (1 if i < extra else 0) for i in range(len(BANDS))]


# ---------------------------------------------------------------- rendering

def color_name(c: bool) -> str:
    return "White" if c == chess.WHITE else "Black"


def board_plain(b: chess.Board) -> str:
    return str(b)


def board_coords(b: chess.Board, flip: bool) -> str:
    ranks = range(8) if flip else range(7, -1, -1)
    files = range(7, -1, -1) if flip else range(8)
    lines = []
    for r in ranks:
        cells = []
        for f in files:
            p = b.piece_at(chess.square(f, r))
            cells.append(p.symbol() if p else ".")
        lines.append(f"{r + 1} | " + " ".join(cells))
    lines.append("    " + "-" * 15)
    lines.append("    " + " ".join(chess.FILE_NAMES[f] for f in files))
    return "\n".join(lines)


def piece_list(b: chess.Board) -> str:
    out = []
    for c in (chess.WHITE, chess.BLACK):
        parts = []
        for pt in PIECE_ORDER:
            sq = sorted(chess.square_name(s) for s in b.pieces(pt, c))
            if sq:
                name = PIECE_NAMES[pt] + ("s" if len(sq) > 1 else "")
                parts.append(f"{name} {', '.join(sq)}")
        out.append(f"{color_name(c)}: " + "; ".join(parts))
    return "\n".join(out)


def extras(b: chess.Board) -> str:
    rights = []
    for c in (chess.WHITE, chess.BLACK):
        s = []
        if b.has_kingside_castling_rights(c):
            s.append("king side")
        if b.has_queenside_castling_rights(c):
            s.append("queen side")
        rights.append(f"{color_name(c)} may still castle {' and '.join(s)}" if s else f"{color_name(c)} can no longer castle")
    txt = "; ".join(rights) + "."
    if b.ep_square is not None and b.has_legal_en_passant():
        txt += f" En passant capture on {chess.square_name(b.ep_square)} is possible."
    return txt


QUESTIONS = [
    "Which move should {side} play?",
    "What is the best continuation for {side}?",
    "Pick the move that solves the puzzle for {side}.",
    "Choose {side}'s strongest reply.",
    "Which listed move is the correct first move of the solution for {side}?",
    "Select the move a strong player would choose here as {side}.",
]


def render(b: chess.Board, last_san: str, opp: str, rv) -> str:
    side = color_name(b.turn)
    fen = b.fen()
    q = rv.choice(QUESTIONS).format(side=side)
    t = rv.randrange(6)
    if t == 0:
        return (f"FEN: {fen}\n\n{board_plain(b)}\n\nUppercase letters are White pieces, lowercase are Black; White plays up "
                f"the board.\n{side} to move. Every legal move is offered below in standard algebraic notation (SAN).\n{q}")
    if t == 1:
        return (f"Tactics puzzle. Position in Forsyth-Edwards Notation:\n{fen}\n\nIt is {side}'s turn. The options are all "
                f"legal moves, written in SAN.\n{q}")
    if t == 2:
        view = "Black's" if b.turn == chess.BLACK else "White's"
        return (f"The board below is shown from {view} side (rank numbers on the left, files underneath; uppercase = White, "
                f"lowercase = Black).\n\n{board_coords(b, b.turn == chess.BLACK)}\n\nFEN: {fen}\n{side} is to move. {q} "
                f"(All legal moves are listed, in SAN.)")
    if t == 3:
        return (f"Piece placement:\n{piece_list(b)}\n{extras(b)}\nSide to move: {side}.\nFEN for reference: {fen}\n\n"
                f"Each option is one legal move in standard algebraic notation. {q}")
    if t == 4:
        return (f"In this game {opp} has just played {last_san}, reaching the position below.\n\n"
                f"{board_coords(b, False)}\n\nFEN: {fen}\nNow {side} moves. The list holds every legal move in SAN. {q}")
    return (f"{side} to play and find the tactic.\nFEN {fen}\nLast move by {opp}: {last_san}.\n\n{board_plain(b)}\n"
            f"(White pieces in capitals, Black in lower case, rank 8 at the top.)\nAll legal moves are given as options. {q}")


# ---------------------------------------------------------------- selection

def candidates(path: Path) -> list[dict]:
    t = pq.read_table(path, columns=COLUMNS)
    keep = pc.and_(pc.and_(pc.greater_equal(t["Popularity"], MIN_POPULARITY), pc.greater_equal(t["NbPlays"], MIN_PLAYS)),
                   pc.and_(pc.greater_equal(t["Rating"], MIN_RATING), pc.less_equal(t["Rating"], MAX_RATING)))
    t = t.filter(keep)
    cols = {c: t.column(c).to_pylist() for c in COLUMNS}
    rows = [{c: cols[c][i] for c in COLUMNS} for i in range(t.num_rows)]
    rows.sort(key=lambda r: (C.unit(VERSION, TASK, "cand", r["PuzzleId"]), r["PuzzleId"]))
    return rows


def prepare(rec: dict):
    """The solver's position, the gold move and the opponent's last move, or None if the record is unusable."""
    moves = rec["Moves"].split()
    if len(moves) < 2:
        return None
    b = chess.Board(rec["FEN"])
    first = chess.Move.from_uci(moves[0])
    if first not in b.legal_moves:
        return None
    last_san = b.san(first)
    b.push(first)
    gold = chess.Move.from_uci(moves[1])
    if gold not in b.legal_moves:
        return None
    legal = list(b.legal_moves)
    if len(legal) < MIN_LEGAL:
        return None
    return b, gold, last_san, legal


def longest_credit(sans: list[str], gold_san: str) -> float:
    longest = max(len(s) for s in sans)
    top = [s for s in sans if len(s) == longest]
    return 1 / len(top) if gold_san in top else 0.0


def build() -> dict:
    path = C.hf_file(TASK, REPO, REVISION, SHARD, SHARD_SHA256)
    C.record_source(TASK, [{"name": path.name, "url": f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{SHARD}"}],
                    LICENCE, LICENCE_URL,
                    notes=("Hugging Face dataset Lichess/chess-puzzles at revision " + REVISION + ", shard " + SHARD +
                           " (one of three), read with pyarrow. Kept: Popularity >= 80, NbPlays >= 200, Rating 700-2600, "
                           ">= 4 legal moves, one puzzle per game, four rating bands of a quarter each, mate-in-one <= 18 % "
                           "per band, longest-option cue capped at chance + 0.10 on questions with <= 26 options. Gold = the puzzle's first solver move (Moves[1]) in SAN after pushing Moves[0]; "
                           "options = all legal moves. Group key = Lichess game id (GameId before '/' or '#'); the shard "
                           "has GameId instead of GameUrl."))
    meta = C.dev_meta(TASK)
    quota = {s: band_quota(n) for s, n in TARGET.items()}
    mate_cap = {s: [int(MATE1_SHARE * q) for q in quota[s]] for s in TARGET}
    got = {s: [[] for _ in BANDS] for s in TARGET}
    mates = {s: [0] * len(BANDS) for s in TARGET}
    seen_games: set[str] = set()
    seen_pos: set[str] = set()
    cue = {s: [0.0, 0.0, 0] for s in TARGET}   # per split: longest-cue credit, chance, n (questions with <= 26 options)
    for rec in candidates(path):
        g = game_id(rec["GameId"])
        if not g or g in seen_games:
            continue
        split = C.split_of(TASK, g)
        bi = band_of(rec["Rating"])
        if len(got[split][bi]) >= quota[split][bi]:
            continue
        is_m1 = "mateIn1" in (rec["Themes"] or [])
        if is_m1 and mates[split][bi] >= mate_cap[split][bi]:
            continue
        prep = prepare(rec)
        if prep is None:
            continue
        b, gold, last_san, legal = prep
        pos = b.epd()
        if pos in seen_pos:
            continue
        k = len(legal)
        if k <= SERVED:
            credit = longest_credit([b.san(m) for m in legal], b.san(gold))
            c_sum, ch_sum, n_small = cue[split]
            if c_sum + credit > ch_sum + 1 / k + CUE_SLACK * (n_small + 1):
                continue
            cue[split] = [c_sum + credit, ch_sum + 1 / k, n_small + 1]
        seen_games.add(g)
        seen_pos.add(pos)
        mates[split][bi] += is_m1
        got[split][bi].append({"rec": rec, "game": g, "band": bi, "mate1": is_m1, "board": b, "gold": gold,
                               "last_san": last_san, "legal": legal})
        if all(len(got[s][i]) >= quota[s][i] for s in TARGET for i in range(len(BANDS))):
            break

    rows_by_split: dict[str, list[dict]] = {}
    stats: dict = {}
    for split in TARGET:
        items = [it for band in got[split] for it in band]
        items.sort(key=lambda it: C.unit(VERSION, TASK, "pos", it["rec"]["PuzzleId"]))
        rot = collections.Counter()
        rows = []
        for it in items:
            b, gold = it["board"], it["gold"]
            pid = it["rec"]["PuzzleId"]
            r = C.rng(VERSION, TASK, "item", pid)
            sans = sorted(b.san(m) for m in it["legal"])
            gold_san = b.san(gold)
            k = len(sans)
            if k <= SMALL_K:
                others = [s for s in sans if s != gold_san]
                r.shuffle(others)
                pos = (rot[k] + C.rng(VERSION, TASK, "rot", split, k).randrange(k)) % k
                rot[k] += 1
                order = others[:pos] + [gold_san] + others[pos:]
            else:
                order = list(sans)
                r.shuffle(order)
            criteria = {C.code(i): s for i, s in enumerate(order)}
            expected = C.code(order.index(gold_san))
            opp = color_name(not b.turn)
            text = render(b, last_san, opp, C.rng(VERSION, TASK, "text", pid))
            rows.append(C.row(TASK, meta, SOURCE, it["game"],
                              [{"instructions": text, "criteria": criteria, "expected": expected}]))
            it["row"] = rows[-1]
        self_check(items)
        rows_by_split[split] = rows
        n = len(items)
        stats[split] = {"n": n, "bands": [len(x) for x in got[split]],
                        "longest_cue_small": [round(cue[split][0] / max(1, cue[split][2]), 3),
                                              round(cue[split][1] / max(1, cue[split][2]), 3), cue[split][2]],
                        "mate_in_one_share": round(sum(it["mate1"] for it in items) / max(1, n), 3)}
    counts = C.write_splits(TASK, rows_by_split, TARGET["train"])
    assert counts == TARGET, counts
    # replay the files as written (ids numbered by write_splits) against the raw records once more
    by_game = {it["game"]: it for split in TARGET for band in got[split] for it in band}
    for split in TARGET:
        written = []
        for line in open(C.OUT / f"{TASK}.{split}.jsonl", encoding="utf-8"):
            row = json.loads(line)
            it = dict(by_game[row["source_id"]], row=row)
            assert C.split_of(TASK, row["source_id"]) == split
            written.append(it)
        self_check(written)
    stats["counts"] = counts
    return stats


def self_check(items: list[dict]) -> None:
    """Replay every item from the raw record: gold legal, equal to the puzzle's Moves[1], options = all legal moves."""
    for it in items:
        rec, row = it["rec"], it["row"]
        q = row["questions"][0]
        moves = rec["Moves"].split()
        b = chess.Board(rec["FEN"])
        m0 = chess.Move.from_uci(moves[0])
        assert m0 in b.legal_moves, rec["PuzzleId"]
        b.push(m0)
        assert b.fen() in q["instructions"], rec["PuzzleId"]
        assert f"{color_name(b.turn)}" in q["instructions"], rec["PuzzleId"]
        gold = b.parse_san(q["criteria"][q["expected"]])
        assert gold in b.legal_moves, rec["PuzzleId"]
        assert gold.uci() == moves[1] or gold == chess.Move.from_uci(moves[1]), rec["PuzzleId"]
        legal = sorted(b.san(m) for m in b.legal_moves)
        assert sorted(q["criteria"].values()) == legal, rec["PuzzleId"]
        assert len(legal) >= MIN_LEGAL and len(set(legal)) == len(legal), rec["PuzzleId"]
        assert row["source_id"] == game_id(rec["GameId"]), rec["PuzzleId"]
        assert C.split_of(TASK, row["source_id"]) in TARGET


def main() -> None:
    stats = build()
    print(json.dumps(stats))
    for s in TARGET:
        p = C.OUT / f"{TASK}.{s}.jsonl"
        print(s, hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
