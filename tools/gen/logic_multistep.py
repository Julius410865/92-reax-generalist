"""logic_multistep: entities with properties, 3-8 rules, facts -> one query that needs 2-5 chained steps.

Rules (drawn per item, worded from several templates each) are universally quantified over the item's entities:
* if/then        ``a -> b``                (also read backwards: from "not b" follows "not a")
* only-if        ``b only if a`` = ``b -> a``
* exclusion      ``no entity is both a and b``
* conjunction    ``a and c -> b``
* exception      ``a -> b unless c; a and c -> not b``
where a, b, c are literals (a property or its negation). The query entity's facts start a chain of ``d`` rule
applications (d = 2..5); each step is one of the forms above (modus ponens, modus tollens, an exclusion, a side condition,
an exception). 1-3 further rules are traps or irrelevant: a converse trap (``wrong -> m`` with the entity having m), rules
over other properties, rules that never fire for the entity.

Queries (one question per item, as the dev items): yes/no ("is it true that X p?"), a True/False statement (options
A/B), "which entity certainly p?" (3-7 entities as options) and "which statement about X must be true?" (3-7 literals).

Gold: ``solve`` runs forward chaining (unit propagation in rounds; the round is the step count) over the case's clauses
and facts. ``draw`` builds a model for every entity (a full assignment satisfying every rule and fact, found by
enumeration), so the premises are consistent and "not entailed" is exact; it keeps an item only if the query is decided by
forward chaining at depth 2-5 and, for the multiple-choice kinds, exactly one option is entailed. Distractors are answers
reached by a slip: stopping one step early, using the converse of a rule, ignoring an exception, denying the antecedent.
``solve_text`` parses the rendered rules, facts, question and options and decides by truth-table enumeration
(an independent method).
"""

from __future__ import annotations

import re

from tools.gen.base import NAMES, Retry, pick

TASK = "logic_multistep"
PART, AREA, GOLD, HALF, COMPONENT = "T", "knowledge", True, "hf", None

# ------------------------------------------------------------------------------------------------------- vocabulary

THEMES = (
    {"noun": "animal", "art": "an", "plural": "animals", "names": "pets",
     "context": ("The keepers of a wildlife reserve wrote down rules about their animals.",
                 "A small zoo describes its animals with the rules below.",
                 "These rules come from the logbook of an animal sanctuary."),
     "preds": (("is nocturnal", "is not nocturnal"), ("eats insects", "does not eat insects"),
               ("lives near water", "does not live near water"), ("has striped fur", "does not have striped fur"),
               ("can climb trees", "cannot climb trees"), ("hibernates in winter", "does not hibernate in winter"),
               ("hunts in packs", "does not hunt in packs"), ("wears a collar tag", "does not wear a collar tag"),
               ("sleeps in a burrow", "does not sleep in a burrow"), ("is fed by hand", "is not fed by hand"),
               ("has a long tail", "does not have a long tail"), ("is kept in the east enclosure", "is not kept in the east enclosure"),
               ("migrates in autumn", "does not migrate in autumn"), ("is shy around visitors", "is not shy around visitors"))},
    {"noun": "member", "art": "a", "plural": "members", "names": "people", "it": "the member",
     "context": ("A hobby club keeps these rules about its members.", "The rules below describe the members of a rowing club.",
                 "A community choir has noted the following about its members."),
     "preds": (("plays the cello", "does not play the cello"), ("speaks Basque", "does not speak Basque"),
               ("owns a kayak", "does not own a kayak"), ("works night shifts", "does not work night shifts"),
               ("is left-handed", "is not left-handed"), ("commutes by train", "does not commute by train"),
               ("keeps bees", "does not keep bees"), ("sits on the board", "does not sit on the board"),
               ("bakes bread", "does not bake bread"), ("is a vegetarian", "is not a vegetarian"),
               ("has a library card", "does not have a library card"), ("volunteers on Sundays", "does not volunteer on Sundays"),
               ("collects stamps", "does not collect stamps"), ("can drive a van", "cannot drive a van"))},
    {"noun": "robot", "art": "a", "plural": "robots", "names": "codes",
     "context": ("A warehouse configures its robots according to the rules below.",
                 "The fleet manual of a logistics centre lists these rules for its robots.",
                 "These rules describe the robots working in a parcel depot."),
     "preds": (("has a gripper arm", "does not have a gripper arm"), ("runs on solar power", "does not run on solar power"),
               ("is rated for cold storage", "is not rated for cold storage"), ("carries a camera", "does not carry a camera"),
               ("works the loading dock", "does not work the loading dock"), ("needs daily charging", "does not need daily charging"),
               ("can climb ramps", "cannot climb ramps"), ("is painted yellow", "is not painted yellow"),
               ("logs its routes", "does not log its routes"), ("is on the night roster", "is not on the night roster"),
               ("has a spare battery", "does not have a spare battery"), ("handles fragile goods", "does not handle fragile goods"),
               ("is due for inspection", "is not due for inspection"))},
    {"noun": "plant", "art": "a", "plural": "plants", "names": "invented",
     "context": ("A botanical greenhouse follows these rules for its plants.", "The gardeners of a nursery wrote these rules about their plants.",
                 "These rules describe the plants in a research greenhouse."),
     "preds": (("needs full sun", "does not need full sun"), ("flowers in spring", "does not flower in spring"),
               ("has thorns", "does not have thorns"), ("is watered daily", "is not watered daily"),
               ("grows on a trellis", "does not grow on a trellis"), ("is grafted", "is not grafted"),
               ("bears fruit", "does not bear fruit"), ("sits in the north bed", "does not sit in the north bed"),
               ("attracts bees", "does not attract bees"), ("is pruned in autumn", "is not pruned in autumn"),
               ("has variegated leaves", "does not have variegated leaves"), ("is kept indoors", "is not kept indoors"),
               ("needs acidic soil", "does not need acidic soil"))},
    {"noun": "creature", "art": "a", "plural": "creatures", "names": "invented",
     "context": ("In an invented world, creatures obey the rules below.", "A fantasy bestiary states these rules about its creatures.",
                 "The following rules hold for the creatures of an imaginary island."),
     "preds": (("is a quindle", "is not a quindle"), ("is glimmery", "is not glimmery"), ("hums at dusk", "does not hum at dusk"),
               ("has blue scales", "does not have blue scales"), ("is a plorb", "is not a plorb"),
               ("eats moonberries", "does not eat moonberries"), ("is fluffy", "is not fluffy"), ("can teleport", "cannot teleport"),
               ("is a vexil", "is not a vexil"), ("glows in the dark", "does not glow in the dark"),
               ("lays silver eggs", "does not lay silver eggs"), ("is a drummet", "is not a drummet"),
               ("sings backwards", "does not sing backwards"))},
    {"noun": "vessel", "art": "a", "plural": "vessels", "names": "invented",
     "context": ("The harbour office applies the rules below to vessels in port.", "A port authority lists these rules for the vessels it handles.",
                 "These rules describe the vessels moored in a small harbour."),
     "preds": (("flies a red pennant", "does not fly a red pennant"), ("carries passengers", "does not carry passengers"),
               ("has a steel hull", "does not have a steel hull"), ("is moored at the outer pier", "is not moored at the outer pier"),
               ("runs on diesel", "does not run on diesel"), ("needs a pilot to dock", "does not need a pilot to dock"),
               ("is inspected monthly", "is not inspected monthly"), ("sails at night", "does not sail at night"),
               ("has a crane on deck", "does not have a crane on deck"), ("carries refrigerated cargo", "does not carry refrigerated cargo"),
               ("is registered abroad", "is not registered abroad"), ("pays the winter fee", "does not pay the winter fee"),
               ("tows a barge", "does not tow a barge"))},
    {"noun": "student", "art": "a", "plural": "students", "names": "people", "it": "the student",
     "context": ("A school records the following rules about its students.", "The rules below apply to the students of a summer camp.",
                 "A language academy describes its students with these rules."),
     "preds": (("takes chemistry", "does not take chemistry"), ("sings in the choir", "does not sing in the choir"),
               ("walks to school", "does not walk to school"), ("wears glasses", "does not wear glasses"),
               ("is on the chess team", "is not on the chess team"), ("has a locker upstairs", "does not have a locker upstairs"),
               ("plays the trumpet", "does not play the trumpet"), ("joins the field trip", "does not join the field trip"),
               ("eats in the canteen", "does not eat in the canteen"), ("is a prefect", "is not a prefect"),
               ("rides the early bus", "does not ride the early bus"), ("studies Latin", "does not study Latin"),
               ("is in the robotics club", "is not in the robotics club"))},
)

PEOPLE = NAMES + ("Anouk", "Bettina", "Cosmin", "Daria", "Eamon", "Fiona", "Gustav", "Helga", "Ivo", "Jorun", "Kasimir",
                  "Liesel", "Marius", "Nilufar", "Orla", "Petra", "Ruben", "Selma", "Teodor", "Ulla", "Viktor", "Wiebke",
                  "Yannick", "Zainab", "Alvaro", "Brigid", "Cormac", "Dagny", "Esben", "Fenna", "Gunnar", "Hedda", "Ismael",
                  "Jelena", "Kerstin", "Lorcan", "Maelis", "Nikos", "Oona", "Pavel", "Rhea", "Sanne", "Tiago", "Valeska")
PETS = ("Biscuit", "Clover", "Pippin", "Juniper", "Mocha", "Pepper", "Sable", "Thistle", "Nutmeg", "Bramble", "Cinder",
        "Dusty", "Fennel", "Gizmo", "Hazel", "Indy", "Jasper", "Kiwi", "Lupin", "Maple", "Nugget", "Olive", "Pickle",
        "Quill", "Rusty", "Saffron", "Tango", "Umber", "Velvet", "Waffle", "Ziggy", "Acorn", "Basil", "Cocoa", "Dumpling",
        "Echo", "Fable", "Ginger", "Honey", "Inky", "Jelly", "Koko", "Lentil", "Mango", "Noodle", "Oreo", "Pumpkin")
ONSETS = ("B", "D", "F", "G", "K", "L", "M", "N", "P", "R", "S", "T", "V", "Z", "Br", "Dr", "Gl", "Kr", "Pl", "St", "Tr", "Vr")
VOWELS = ("a", "e", "i", "o", "u", "ae", "ia", "ou")
MIDS = ("l", "n", "r", "s", "v", "m", "th", "nd", "rk", "sh", "lv", "z")
ENDS = ("", "", "a", "o", "in", "en", "ar", "is", "ix", "um", "et", "or")

KINDS = (("yesno", 30), ("tf", 15), ("who", 30), ("what", 25))
# TRAP_P: a converse trap on the wrong answer; MENTION_P: else a rule that mentions the right one (together they keep
# "the asked phrase is written in the rules" from saying anything about the answer); WRITTEN_P: share of "what"
# distractors whose phrase is written in the text (the gold's phrase usually is). Measured on 3,000 draws.
TRAP_P, MENTION_P, WRITTEN_P = 0.55, 0.45, 0.9
MC_OPTIONS = ((3, 1), (4, 1), (5, 5), (6, 1), (7, 3))

# ---------------------------------------------------------------------------------------------------- templates

RULE_TEMPLATES = {
    "imp": ("Every {noun} that {A} {B}.", "If {art} {noun} {A}, then {it} {B}.", "Whenever {art} {noun} {A}, {it} {B}.",
            "Each {noun} that {A} {B}.", "Any {noun} that {A} {B}."),
    "onlyif": ("{Art} {noun} {B} only if {it} {A}.", "For every {noun}: {it} {B} only if {it} {A}."),
    "excl": ("No {noun} that {A} {B}.", "There is no {noun} that both {A} and {B}."),
    "conj": ("Every {noun} that {A} and {C} {B}.", "If {art} {noun} {A} and {C}, then {it} {B}.",
             "Any {noun} that both {A} and {C} {B}."),
    "unless": ("Every {noun} that {A} {B}, unless {it} {C}; in that case {it} {NB}.",
               "If {art} {noun} {A}, {it} {B}, except when {it} {C}: then {it} {NB}.",
               "Any {noun} that {A} {B} - but one that also {C} {NB}."),
}
INTROS = (
    "{context} Every rule applies to each {noun} mentioned, even where it sounds unusual.",
    "{context} Treat each rule as strictly true for every {noun}, whatever the real world suggests.",
    "Read the rules and facts below. {context} The rules hold without exception for every {noun} named.",
    "{context} Use only the rules and facts given here; ignore what you know from the real world.",
    "Logic puzzle. {context} Each rule is true for every {noun} that appears below.",
    "{context} Reason only from what is written; the rules are always obeyed.",
)
NOTES = ("The rules and facts are enough to settle the question.", "The question can be decided from the rules and facts alone.",
         "Chain the rules carefully: the answer follows from what is given.", "Nothing outside the text is needed.",
         "Several steps of reasoning may be needed.")
RULE_HEADERS = ("Rules:", "The rules:", "These rules always hold:", "Rules (valid for every {noun}):", "General rules:")
FACT_HEADERS = ("Facts:", "What is known:", "Known facts:", "Observations:", "Records:")
Q_YESNO = ("Is it true that {N} {P}?", "Answer yes or no: does it follow that {N} {P}?",
           "Question: must it be the case that {N} {P}?",
           "Can one conclude that {N} {P}? Answer yes if it follows, no if its opposite follows.",
           "Given the rules and facts, is the claim that {N} {P} correct?")
Q_TF = ("Is this statement true or false?", "Based only on the rules and facts, is the statement true or false?",
        "Decide whether the statement is true or false.", "Does the statement hold (True) or not (False)?",
        "Judge the statement: True or False?")
Q_WHO = ("Which {noun} {P}, for certain?", "For which {noun} does it follow that {it} {P}?",
         "Exactly one of the {plural} must be one that {P}. Which one?", "Which {noun} is certain to be one that {P}?",
         "Which {noun} can be proven to be one that {P}?")
Q_WHAT = ("Which statement about {N} must be true?", "Which of the following follows from the rules and facts?",
          "What can be concluded for certain about {N}?", "Exactly one of the statements below is certain. Which one?",
          "Which conclusion about {N} is justified by the rules and facts?")


def _phrase(theme, lit):
    p, s = lit
    return THEMES[theme]["preds"][p][0 if s else 1]


def _neg(lit):
    return [lit[0], not lit[1]]


# ------------------------------------------------------------------------------------------------- clause logic

def rule_clauses(rule) -> list[list[list]]:
    """The clauses (disjunctions of literals [pred, sign]) a rule stands for."""
    k = rule["kind"]
    if k == "imp":
        return [[_neg(rule["a"]), rule["b"]]]
    if k == "onlyif":
        return [[_neg(rule["b"]), rule["a"]]]
    if k == "excl":
        return [[_neg(rule["a"]), _neg(rule["b"])]]
    if k == "conj":
        return [[_neg(rule["a"]), _neg(rule["c"]), rule["b"]]]
    if k == "unless":
        return [[_neg(rule["a"]), rule["c"], rule["b"]], [_neg(rule["a"]), _neg(rule["c"]), _neg(rule["b"])]]
    raise ValueError(k)


class Contradiction(Exception):
    pass


def forward(clauses, facts, max_rounds: int | None = None) -> dict[int, tuple[bool, int]]:
    """Forward chaining (unit propagation in synchronous rounds): {pred: (sign, round derived)}; facts are round 0."""
    known: dict[int, tuple[bool, int]] = {}
    for p, s in facts:
        if p in known and known[p][0] != s:
            raise Contradiction("facts")
        known[p] = (bool(s), 0)
    rnd = 0
    while max_rounds is None or rnd < max_rounds:
        rnd += 1
        new: dict[int, bool] = {}
        for cl in clauses:
            open_ = []
            sat = False
            for p, s in cl:
                if p in known:
                    if known[p][0] == s:
                        sat = True
                        break
                else:
                    open_.append((p, s))
            if sat:
                continue
            if not open_:
                raise Contradiction("clause violated")
            if len(open_) == 1:
                p, s = open_[0]
                if p in new and new[p] != s:
                    raise Contradiction("both signs derived")
                new[p] = s
        if not new:
            break
        for p, s in new.items():
            known[p] = (s, rnd)
    return known


def models(clauses, facts, preds) -> dict:
    """Every assignment of ``preds`` that satisfies the facts and all clauses (truth-table enumeration, as bitmasks)."""
    idx = {p: i for i, p in enumerate(preds)}
    fmask = fval = 0
    for p, s in facts:
        b = 1 << idx[p]
        if fmask & b and bool(fval & b) != bool(s):
            return {"idx": idx, "ms": []}
        fmask |= b
        fval |= b if s else 0
    cls = [(sum(1 << idx[p] for p, s in c if s), sum(1 << idx[p] for p, s in c if not s)) for c in clauses]
    full = (1 << len(preds)) - 1
    out = []
    for x in range(1 << len(preds)):
        if x & fmask != fval:
            continue
        nx = ~x & full
        if all((x & pm) or (nx & nm) for pm, nm in cls):
            out.append(x)
    return {"idx": idx, "ms": out}


def entailed(m: dict, lit) -> bool:
    """True in every model (and there is a model)."""
    b = 1 << m["idx"][lit[0]]
    return bool(m["ms"]) and all(bool(x & b) == bool(lit[1]) for x in m["ms"])


# ------------------------------------------------------------------------------------------------------- drawing

def _names(rng, kind, k):
    if kind == "people":
        return pick(rng, PEOPLE, k)
    if kind == "pets":
        return pick(rng, PETS, k)
    out = []
    while len(out) < k:
        if kind == "codes":
            n = rng.choice("ABCDEFGHKLMNPRSTVXZ") + rng.choice("ABCDEFGHKLMNPRSTVXZ") + "-" + str(rng.randint(10, 99))
        else:
            n = rng.choice(ONSETS) + rng.choice(VOWELS) + (rng.choice(MIDS) + rng.choice(VOWELS) if rng.random() < 0.7 else "") \
                + rng.choice(ENDS)
            n = n[:1] + n[1:].lower()
        if n not in out and 3 <= len(n) <= 10:
            out.append(n)
    return out


def _step_rule(rng, cur, nxt, side=None, exc=None):
    """A rule that yields literal ``nxt`` from ``cur`` (plus a side literal for conj / the exception literal)."""
    if side is not None:
        return {"kind": "conj", "a": cur, "c": side, "b": nxt}
    if exc is not None:                    # exc = (exception literal, entity has it?)
        lit, has = exc
        return {"kind": "unless", "a": cur, "c": lit, "b": _neg(nxt) if has else nxt}
    forms = [({"kind": "imp", "a": cur, "b": nxt}, 3), ({"kind": "imp", "a": _neg(nxt), "b": _neg(cur)}, 2),
             ({"kind": "onlyif", "b": cur, "a": nxt}, 2), ({"kind": "onlyif", "b": _neg(nxt), "a": _neg(cur)}, 1)]
    if cur[1] and not nxt[1]:
        forms.append(({"kind": "excl", "a": cur, "b": _neg(nxt)}, 4))
    if not cur[1] and nxt[1]:
        forms.append(({"kind": "excl", "a": _neg(nxt), "b": _neg(cur)}, 0))
    scored = []
    for r, w in forms:
        negs = sum(not r[k][1] for k in ("a", "b"))
        scored.append((r, w + (3 if negs == 0 else 1 if negs == 1 else 0)))
    return rng.choices([r for r, _ in scored], [w for _, w in scored])[0]


def _random_rule(rng, preds):
    p, q = rng.sample(preds, 2)
    a, b = [p, rng.random() < 0.7], [q, rng.random() < 0.6]
    kind = rng.choice(["imp", "imp", "onlyif", "excl"])
    if kind == "excl":
        return {"kind": "excl", "a": [p, True], "b": [q, rng.random() < 0.8]}
    return {"kind": kind, "a": a, "b": b}


def _slip_answers(rules, facts, lit, depth) -> dict[str, bool | None]:
    """What a reader concludes about ``lit`` after a common slip (closed-world reading: not derived means no)."""
    base = [c for r in rules for c in rule_clauses(r)]
    out = {}
    try:
        out["stop one step early"] = forward(base, facts, max_rounds=depth - 1).get(lit[0], (None,))[0] == lit[1]
    except Contradiction:
        out["stop one step early"] = None
    conv = list(base)
    for r in rules:
        if r["kind"] == "imp":
            conv.append([_neg(r["b"]), r["a"]])
        elif r["kind"] == "onlyif":
            conv.append([_neg(r["a"]), r["b"]])
    noexc = []
    for r in rules:
        if r["kind"] == "unless":
            noexc.append([_neg(r["a"]), r["b"]])
        elif r["kind"] != "excl":
            noexc += rule_clauses(r)
    for name, cls in (("converse of a rule", conv), ("ignoring an exclusion or exception", noexc)):
        try:
            out[name] = forward(cls, facts).get(lit[0], (None,))[0] == lit[1]
        except Contradiction:
            out[name] = None
    return out


def draw(rng):
    ti = rng.randrange(len(THEMES))
    th = THEMES[ti]
    qkind = rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
    n_opt = 2 if qkind in ("yesno", "tf") else rng.choices([n for n, _ in MC_OPTIONS], [w for _, w in MC_OPTIONS])[0]
    d = rng.choice([2, 3, 3, 4, 4, 5])
    n_preds = len(th["preds"])
    order = pick(rng, range(n_preds), n_preds)
    chain_p, rest = order[:d + 1], order[d + 1:]
    chain = [[p, rng.random() < 0.6] for p in chain_p]
    chain[-1][1] = rng.random() < 0.5                 # the queried literal: either sign equally often
    x_facts = [chain[0]]
    rules = []
    for i in range(d):
        form = rng.choices(["plain", "conj", "unless"], [70, 15, 15])[0]
        if form != "plain" and rest:
            q = rest.pop(0)
            if form == "conj":
                side = [q, rng.random() < 0.6]
                x_facts.append(side)
                rules.append(_step_rule(rng, chain[i], chain[i + 1], side=side))
            else:
                lit, has = [q, rng.random() < 0.6], rng.random() < 0.5
                x_facts.append(lit if has else _neg(lit))
                rules.append(_step_rule(rng, chain[i], chain[i + 1], exc=(lit, has)))
        else:
            rules.append(_step_rule(rng, chain[i], chain[i + 1]))
    target = chain[-1]
    used = list(chain_p) + [f[0] for f in x_facts[1:]]
    # a converse trap: "wrong -> m" where X has m (a fact or a chain literal); a reader who reverses it concludes "wrong"
    wrong = _neg(target)
    traps = []
    if qkind == "who":
        m_lit = [rest.pop(0), rng.random() < 0.6] if rest else None
        if m_lit:
            traps.append({"kind": "imp", "a": target, "b": m_lit})
            used.append(m_lit[0])
    elif rng.random() < TRAP_P:
        m_lit = rng.choice(chain[1:-1] + x_facts) if d > 2 else rng.choice(x_facts)
        traps.append({"kind": "imp", "a": wrong, "b": m_lit})
    elif rest and rng.random() < MENTION_P:
        traps.append({"kind": "imp", "a": target, "b": [rest.pop(0), rng.random() < 0.6]})   # fires, changes nothing asked
    extra_preds = rest[:rng.randint(1, 3)]
    used += extra_preds
    n_irr = rng.randint(1, 3)
    if len(rules) + len(traps) + n_irr > 8:
        n_irr = max(0, 8 - len(rules) - len(traps))
    for _ in range(n_irr):
        pool = sorted(set(extra_preds + rng.sample(used, min(2, len(used))))) if extra_preds else used
        r = _random_rule(rng, pool)
        if all(sorted(map(tuple, c)) not in [sorted(map(tuple, c2)) for r2 in rules for c2 in rule_clauses(r2)]
               for c in rule_clauses(r)):
            rules.append(r)
    rules += traps
    if not 3 <= len(rules) <= 8:
        raise Retry("rule count")
    rng.shuffle(rules)
    used = sorted({p for r in rules for c in rule_clauses(r) for p, _ in c} | {p for p, _ in x_facts})
    if len(used) > 11:
        raise Retry("too many properties")
    clauses = [c for r in rules for c in rule_clauses(r)]
    # sometimes an irrelevant fact about X
    if rng.random() < 0.5:
        free = [u for u in used if u not in [f[0] for f in x_facts] and u not in chain_p]
        if free:
            x_facts.append([rng.choice(free), rng.random() < 0.5])
    # entities
    n_ent = n_opt if qkind == "who" else rng.randint(1, 4)
    names = _names(rng, th["names"], n_ent)
    ents = [{"name": names[0], "facts": x_facts}]
    ms_all = [models(clauses, x_facts, used)]
    if not ms_all[0]["ms"]:
        raise Retry("inconsistent query entity")
    # "who": 1-2 decoy seeds besides the query entity, and every further entity a near-copy (one fact flipped) of a
    # seed chosen uniformly - the query entity is then one cluster centre among several, not the only one
    seeds = [x_facts]
    n_seeds = (1 if n_ent <= 4 else 2) if qkind == "who" else 0
    for k, nm in enumerate(names[1:]):
        # the number of facts is fixed before the redraws: redrawing until the target is absent would otherwise favour
        # entities with few facts
        want = 1 + sum(rng.random() < 0.3 for _ in range(d)) + (rng.random() < 0.5)
        for _ in range(12):          # redraw this entity until it is consistent (and, for "who", lacks the target)
            if qkind != "who":
                fs = _other_facts(rng, qkind, chain, x_facts, rules, traps, used, want=want)
            elif k < n_seeds:
                fs = _other_facts(rng, qkind, chain, x_facts, rules, traps, used, want=want, style=rng.choice(["trap", "random"]))
            else:
                fs = _near_copy(rng, rng.choice(seeds))
            m = models(clauses, fs, used)
            if m["ms"] and not (qkind == "who" and entailed(m, target)):
                break
        else:
            raise Retry("no usable second entity")
        if qkind == "who" and k < n_seeds:
            seeds.append(fs)
        ents.append({"name": nm, "facts": fs})
        ms_all.append(m)
    try:
        known = forward(clauses, x_facts)
    except Contradiction:
        raise Retry("contradiction") from None
    if target[0] not in known or known[target[0]][0] != target[1] or not 2 <= known[target[0]][1] <= 5:
        raise Retry("target not derived at depth 2-5")
    depth = known[target[0]][1]
    case = {"theme": ti, "preds": used, "rules": rules, "entities": ents, "depth": depth, "kind": qkind}
    if qkind in ("yesno", "tf"):
        asked = target if rng.random() < 0.5 else wrong          # the answer polarity is a fair coin
        case.update(entity=0, asked=asked, slips=_slip_answers(rules, x_facts, asked, depth))
        if qkind == "tf":
            case["options"] = ["True", "False"]
        return case
    if qkind == "who":
        rng.shuffle(ents)
        case.update(entities=ents, target=target, options=[e["name"] for e in ents])
        return case
    # what: statements about X; exactly one entailed
    ms = ms_all[0]
    opts = [target]
    slip_lits = []          # one statement per property: a listed complement would point at the pair holding the gold
    for r in rules:
        if r["kind"] == "imp" and entailed(ms, r["b"]) and not entailed(ms, r["a"]):
            slip_lits.append(r["a"])                                        # converse
        if r["kind"] == "unless" and entailed(ms, r["a"]) and entailed(ms, r["c"]):
            slip_lits.append(r["b"])                                        # exception ignored
        if r["kind"] == "imp" and entailed(ms, _neg(r["a"])) and not entailed(ms, _neg(r["b"])):
            slip_lits.append(_neg(r["b"]))                                  # antecedent denied
        if r["kind"] == "onlyif" and entailed(ms, r["a"]) and not entailed(ms, r["b"]):
            slip_lits.append(r["b"])                                        # "only if" read as "if"
    written = [list(r[k]) for r in rules for k in ("a", "b", "c") if k in r] + [_neg(r["b"]) for r in rules if r["kind"] == "unless"] \
        + [list(f) for e in ents for f in e["facts"]]
    fill = []
    for p in pick(rng, used, len(used)):
        cands = [lit for lit in ([p, True], [p, False]) if not entailed(ms, lit)]
        inside = [lit for lit in cands if lit in written]
        if len(cands) == 2 and len(inside) == 1 and rng.random() < 0.8:
            cands = inside                                  # mostly a polarity that is written in the text, like the gold
        if cands:
            fill.append(rng.choice(cands))
    # the gold is usually a phrase written in the rules; distractors are written phrases about as often
    pool_w = [lit for lit in slip_lits + fill if lit in written]
    pool_u = [lit for lit in slip_lits + fill if lit not in written]
    while len(opts) < n_opt and (pool_w or pool_u):
        pool = pool_w if (pool_w and (rng.random() < WRITTEN_P or not pool_u)) else pool_u
        lit = pool.pop(0)
        if lit[0] not in [o[0] for o in opts] and not entailed(ms, lit):
            opts.append(lit)
    if len(opts) < n_opt:
        raise Retry("not enough statements")
    case.update(entity=0, options=opts)
    return case


def _near_copy(rng, facts):
    """The same facts with one of them flipped (a side condition, an exception or the start of a chain)."""
    fs = [list(f) for f in facts]
    k = rng.randrange(len(fs))
    fs[k] = _neg(fs[k])
    rng.shuffle(fs)
    return fs


def _other_facts(rng, qkind, chain, x_facts, rules, traps, used, want, style=None):
    """Facts of a non-query entity: a near-copy of the query entity with one condition changed, a converse trap, or
    ``want`` random facts. ``want`` is drawn like the query entity's count (1 start fact, a side fact for ~30 % of the
    steps, sometimes an irrelevant fact), so the count does not point at the answer."""
    style = style or rng.choice(["near", "random", "random"])
    if style == "near" and len(x_facts) > 1:
        fs = [list(f) for f in x_facts]
        k = rng.randrange(1, len(fs))
        fs[k] = _neg(fs[k])                                                # the side condition / exception flips
    elif style == "near":
        fs = [_neg(chain[0])]
    elif style == "trap" and traps:
        fs = [list(traps[0]["b"])]
    else:
        fs = []
    have = [f[0] for f in fs]
    extra = [p for p in used if p not in have]
    for p in rng.sample(extra, max(0, min(want - len(fs), len(extra)))):
        fs.append([p, rng.random() < 0.5])
    if len(fs) > want and style != "near":
        fs = fs[:want]
    rng.shuffle(fs)
    return fs


# ------------------------------------------------------------------------------------------------------- solving

def solve(case):
    """Forward chaining over the case's clauses and facts; the gold for the item's single question."""
    clauses = [c for r in case["rules"] for c in rule_clauses(r)]
    ents = case["entities"]

    def derived(e, lit):
        try:
            k = forward(clauses, e["facts"])
        except Contradiction:
            raise Retry("contradiction") from None
        if lit[0] not in k:
            return None
        return k[lit[0]][0] == lit[1]

    kind = case["kind"]
    if kind in ("yesno", "tf"):
        v = derived(ents[case["entity"]], case["asked"])
        if v is None:
            raise Retry("query not decided by forward chaining")
        return [v] if kind == "yesno" else [0 if v else 1]
    if kind == "who":
        hits = [i for i, e in enumerate(ents) if derived(e, case["target"])]
        if len(hits) != 1:
            raise Retry("not exactly one entity derived")
        return [case["options"].index(ents[hits[0]]["name"])]
    hits = [i for i, lit in enumerate(case["options"]) if derived(ents[case["entity"]], lit)]
    if len(hits) != 1:
        raise Retry("not exactly one statement derived")
    return [hits[0]]


# ------------------------------------------------------------------------------------------------------ rendering

def _cap(s):
    return s[:1].upper() + s[1:]


def _render_rule(rng, theme, r):
    th = THEMES[theme]
    tpl = rng.choice(RULE_TEMPLATES[r["kind"]])
    f = {"noun": th["noun"], "art": th["art"], "Art": _cap(th["art"]), "it": th.get("it", "it")}
    for k in ("a", "b", "c"):
        if k in r:
            f[k.upper()] = _phrase(theme, r[k])
    if r["kind"] == "unless":
        f["NB"] = _phrase(theme, _neg(r["b"]))
    if r["kind"] == "excl" and rng.random() < 0.5:
        f["A"], f["B"] = f["B"], f["A"]                                   # an exclusion reads both ways
    return tpl.format(**f)


def render(case, rng):
    ti = case["theme"]
    th = THEMES[ti]
    intro = rng.choice(INTROS).format(context=rng.choice(th["context"]), noun=th["noun"]) + " " + rng.choice(NOTES)
    rule_lines = [_render_rule(rng, ti, r) for r in case["rules"]]
    style = rng.randrange(3)
    pref = (lambda i: f"{i}. ", lambda i: "- ", lambda i: f"Rule {i}: ")[style]
    rules_block = rng.choice(RULE_HEADERS).format(noun=th["noun"]) + "\n" + "\n".join(pref(i) + ln for i, ln in enumerate(rule_lines, 1))
    facts = [(e["name"], f) for e in case["entities"] for f in e["facts"]]
    fstyle = rng.randrange(4)
    if fstyle == 3:
        lines = [" ".join(f"{e['name']} {_phrase(ti, f)}." for f in e["facts"]) for e in case["entities"]]
    else:
        if rng.random() < 0.5:
            rng.shuffle(facts)
        lines = [f"{n} {_phrase(ti, f)}." for n, f in facts]
        fp = (lambda i: "- ", lambda i: f"{i}. ", lambda i: f"Fact {i}: ")[fstyle]
        lines = [fp(i) + ln for i, ln in enumerate(lines, 1)]
    facts_block = rng.choice(FACT_HEADERS) + "\n" + "\n".join(lines)
    kind = case["kind"]
    if kind in ("yesno", "tf", "what"):
        name = case["entities"][case["entity"]]["name"]
    if kind == "yesno":
        q = rng.choice(Q_YESNO).format(N=name, P=_phrase(ti, case["asked"]))
        opts = None
    elif kind == "tf":
        q = f"Statement: {name} {_phrase(ti, case['asked'])}.\n" + rng.choice(Q_TF)
        opts = list(case["options"])
    elif kind == "who":
        q = rng.choice(Q_WHO).format(noun=th["noun"], plural=th["plural"], it=th.get("it", "it"), P=_phrase(ti, case["target"]))
        opts = list(case["options"])
    else:
        q = rng.choice(Q_WHAT).format(N=name)
        opts = [f"{name} {_phrase(ti, lit)}." for lit in case["options"]]
    blocks = [rules_block, facts_block]
    if rng.random() < 0.2:
        blocks.reverse()
    return [{"instructions": "\n\n".join([intro] + blocks + [q]), "options": opts}]


# ------------------------------------------------------------------------------------------------- second solver

_PHRASES: dict[str, tuple[str, bool]] = {}
for _th in THEMES:
    for _pos, _negp in _th["preds"]:
        _PHRASES[_pos] = (_pos, True)
        _PHRASES[_negp] = (_pos, False)
_PH = "|".join(re.escape(p) for p in sorted(_PHRASES, key=len, reverse=True))
_NAME = r"[A-Z][A-Za-z0-9-]*"


def _tpl_regex(tpl):
    out = re.escape(tpl)
    for key, pat in (("{noun}", r"(?P<noun>[a-z]+)"), ("{art}", r"(?:a|an)"), ("{Art}", r"(?:A|An)"), ("{it}", r"(?:it|the [a-z]+)"),
                     ("{A}", f"(?P<A>{_PH})"),
                     ("{B}", f"(?P<B>{_PH})"), ("{C}", f"(?P<C>{_PH})"), ("{NB}", f"(?P<NB>{_PH})")):
        out = out.replace(re.escape(key), pat)
    return re.compile("^" + out + "$")


_RULE_RES = [(kind, _tpl_regex(t)) for kind in ("unless", "conj", "excl", "onlyif", "imp") for t in RULE_TEMPLATES[kind]]
_PREFIX = re.compile(r"^(?:\d+\. |- |Rule \d+: |Fact \d+: )")
_FACT_RE = re.compile(f"^({_NAME}) ({_PH})\\.$")


def _lit(phrase):
    return _PHRASES[phrase]


def _parse_rule(sentence):
    for kind, rx in _RULE_RES:
        m = rx.match(sentence)
        if not m:
            continue
        g = {k: _lit(v) for k, v in m.groupdict().items() if k != "noun" and v}
        n = lambda l: (l[0], not l[1])   # noqa: E731
        if kind == "imp":
            return [[n(g["A"]), g["B"]]]
        if kind == "onlyif":
            return [[n(g["B"]), g["A"]]]
        if kind == "excl":
            return [[n(g["A"]), n(g["B"])]]
        if kind == "conj":
            return [[n(g["A"]), n(g["C"]), g["B"]]]
        if g["NB"] != n(g["B"]):
            raise ValueError(f"exception clause does not negate the default: {sentence}")
        return [[n(g["A"]), g["C"], g["B"]], [n(g["A"]), n(g["C"]), n(g["B"])]]
    return None


def solve_text(q: dict) -> str:
    """Reads only the rendered question: parses every rule and fact sentence, then decides by truth-table enumeration
    over the properties mentioned (exact entailment, independent of the forward chaining in solve)."""
    text = q["instructions"]
    body, _, question = text.rpartition("\n\n")
    clauses, facts = [], {}
    for line in body.splitlines():
        line = _PREFIX.sub("", line.strip())
        for sent in re.split(r"(?<=\.) (?=[A-Z])", line):
            cl = _parse_rule(sent)
            if cl is not None:
                clauses += cl
                continue
            m = _FACT_RE.match(sent)
            if m:
                facts.setdefault(m.group(1), []).append(_lit(m.group(2)))
    preds = sorted({p for cl in clauses for p, _ in cl} | {p for fs in facts.values() for p, _ in fs})

    def ent(name, lit):
        ms = models(clauses, facts.get(name, []), preds + ([lit[0]] if lit[0] not in preds else []))
        if not ms:
            raise ValueError(f"no model for {name}")
        return entailed(ms, lit), entailed(ms, (lit[0], not lit[1]))

    keys = list(q["criteria"])
    if keys == ["yes", "no"]:
        m = re.search(f"({_NAME}) ({_PH})", question)
        yes, no = ent(m.group(1), _lit(m.group(2)))
        if yes == no:
            raise ValueError("undecided")
        return "yes" if yes else "no"
    texts = [q["criteria"][k] for k in keys]
    if sorted(texts) == ["False", "True"]:
        m = re.search(f"Statement: ({_NAME}) ({_PH})\\.", question)
        yes, no = ent(m.group(1), _lit(m.group(2)))
        if yes == no:
            raise ValueError("undecided")
        return keys[texts.index("True" if yes else "False")]
    if all(re.fullmatch(_NAME, t) for t in texts):
        lit = _lit(re.search(f"({_PH})", question).group(1))
        hits = [k for k, t in zip(keys, texts) if ent(t, lit)[0]]
    else:
        hits = []
        for k, t in zip(keys, texts):
            m = _FACT_RE.match(t)
            if ent(m.group(1), _lit(m.group(2)))[0]:
                hits.append(k)
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} options entailed")
    return hits[0]
