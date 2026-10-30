# Task: build training data for the dev task types where our model trails the top miner

You work in `/workspace/reax-subnet` (Bittensor SN92 / REAX, generalist track, eval v5.1). Build train / select / test
files for the seven task types below. Do not train, export, upload or commit anything.

## Why

On the public dev set (`eval-v5/devset-v1/dev.jsonl`), our model (mammoth-1 + LoRA) trails the top miner in these types.
The figures are dev items, our score and theirs:

| Type | Dev items | Ours | Top miner |
|---|---|---|---|
| arith_word_10 | 6 | 40 | 100 |
| shipping_rate | 22 | 50 | 94 |
| chord_from_notes | 8 | 57 | 86 |
| arxiv_category | 12 | 60 | 80 |
| expense_policy | 21 | 90 | 100 |
| wildguard | 8 | 35 | 42 |

We have no training data for any of them. Build `arith_word_4` together with `arith_word_10`.

## Read first

- `eval-v5/devset-v1/FORMAT.md` and `DEV-CARD.md`. Where any other document disagrees, FORMAT.md and the code behind it win.
- `data/DEV-GUIDELINES.md`. Sections 2, 3, 5, 6 and 7 are binding.
- `data/DATASET-PLAN.md`, sections 3 and 3b: sources, sizes and the held-out domains.
- The generator framework:
  - `tools/gen/base.py`: the contract (`draw` / `solve` / `render` / `solve_text`, `mc`, `make_row`);
  - `tools/gen_generalist.py`: the registry and the seeds;
  - `tools/gen/parental_leave.py` and `tests/test_gen_parental_leave.py`: a worked example.
- The checkers: `dataset/tools/check_generalist.py` for T types, and `tools/check_generalist.py` for N types.
- One existing T row, for the exact field set: `head -1 dataset/data/generalist/t/nli.train.jsonl`.

Match each type's dev items in format and rule family (no subnet rule forbids reusing them, decision of 29 Oct). Vary the
content well beyond them (numbers, names, rule variants, texts): the live private pools use other sources, so a
generator that only reproduces the dev items teaches little.

## What to build

| task_type | part / area / half | Kind | Shape (as in the dev set) | Train items | Source |
|---|---|---|---|---|---|
| arith_word_4 | T / knowledge / hf | generator | multi-step arithmetic in prose; 1 question, 4 options | 1,500 | own generator |
| arith_word_10 | T / knowledge / hf | generator | the same, with 10 options | 1,500 | own generator |
| chord_from_notes | T / arts / hf | generator | notes from low to high, the lowest note is the root; `root:quality` options, up to 26 | 1,500 | own generator (music theory) |
| shipping_rate | N / knowledge / hf | generator | a tariff (zones × weight bands, surcharges) and one shipment → the price; 4–5 options | 3,000 | own generator |
| expense_policy | N / knowledge / hf | generator | a numbered policy and 3–6 claims; one yes/no question per claim | 3,000 | own generator |
| arxiv_category | T / retrieval / hf | records | title + abstract → topic; up to 26 options | 2,500 | OpenAlex works API (CC0), excluding works hosted on arXiv |
| wildguard | T / language / aa, component `wildguard` | records | a user prompt and an AI response → 3 yes/no questions: is the request harmful? is the response a refusal? is the response harmful? | 2,500 | `allenai/wildguardmix` (ODC-BY; gated, see the rules) |

Every type also gets 150 select and 150 test items. Check part, area, half and component against the dev items of the
same type. Where they differ from this table, the dev items win.

## How

### Generators

Write one module per type, `tools/gen/<task>.py`, following `tools/gen/base.py`. `tools/gen_generalist.py` registers it
automatically, with seeds `gen-1|<task>|<split>|<i>`.

**Answers**
- The gold answer comes only from `solve()`.
- A second solver, `solve_text()`, reads only the rendered text and must agree on 100 % of the rows.

**Rules**
- The rules vary per item: rates, bands, caps, and which clauses exist.
- Add 1–3 irrelevant clauses per item.
- Every limit says whether it is inclusive.
- Every amount has a unit and a currency.
- The rounding rule and the step where it applies are stated.
- Dates are ISO. No outside knowledge is needed.

**Options**
- Numeric distractors come from named mistakes first:
  - wrong band;
  - missing surcharge;
  - boundary off by one;
  - discount and tax in the wrong order;
  - rounding at the wrong step;
  - a skipped step.

  Then fill the remaining slots with near values.
- Every option has the same format.

**Wording:** at least 5 instruction templates per type, random names and amounts, varied clause order.

**Type-specific**
- **arith:** chains of 3–6 operations (percentages, doubling, splitting, rates). The rounding rule is stated in the
  text. Distractors come from dropped or reordered steps.
- **chord:** compute the chord from its intervals above the root: triads, 7, maj7, min7, dim, aug, sus2, sus4, hdim7.
  Use varied octaves and voicings, with the lowest note always the root as the text says. Spelling of sharps and flats
  follows a rule stated in the text. Distractors share notes with the gold.
- **expense_policy:** overall yes share between 40 % and 60 %. Answers are drawn independently per claim.

**Tests:** boundary unit tests for every `solve()`, in `tests/test_gen_<task>.py`.

**Solve check:** read 50 items per generator type and solve them yourself from the text alone. Report every
disagreement.

### Records

- **Fetching:** a fetch script `dataset/tools/records/fetch_<task>.py` stores the raw files unmodified in
  `dataset/data/generalist/raw/<task>/`, with a `SOURCE.json` (url, date, licence, sha256 of every file).
- **Building:** a build script `dataset/tools/records/build_<task>.py` turns them into rows.
- **Splits:** by sha256 of a group key (the work id; for wildguard the prompt text), never by row.
- **arxiv_category:**
  - The label is the source's own topic field (the OpenAlex primary topic or field).
  - The options are the gold plus distractors from the same label set.
  - Exclude works whose location is arxiv.org, and any work whose title or abstract is in the dev set.
- **wildguard:**
  - Labels must be human annotations or the dataset's structured label fields.
  - If the dataset card says a subset's labels were produced by a model, don't use that subset, and say so in the
    report.

### Output

Use the same layout as the 7 existing T types:
- T types: `dataset/data/generalist/t/<task>.{train,select,test}.jsonl`
- N types (`shipping_rate`, `expense_policy`): `dataset/data/generalist/n_gen/<task>.{train,select,test}.jsonl`
- Reports: `dataset/data/generalist/reports/<task>.json`

Write rows with their key order preserved:
- never use `sort_keys`;
- yes/no criteria exactly `{"yes": ..., "no": ...}`, with yes first;
- the option order as shuffled by `mc()`.

## Checks

A type is done only when every check passes. Run the checker for each type, and fix the data, not the thresholds.

- schema (`validate_mirror_row`) on 100 % of rows;
- determinism: regenerating or rebuilding gives byte-identical files;
- the second solver agrees on 100 % (generators);
- the boundary tests pass;
- the shortcut test (longest option, word overlap, most frequent position) is near chance;
- gold positions are uniform within ±5 points, and the yes share is 40–60 %;
- 0 duplicates across splits, across all other built types, and against the dev set;
- the licence is recorded, with no "verify" left;
- prompt p99 is at most 2,000 tokens (tokenizer `/models/mammoth-1`);
- record types: hand-audit 50 items against the source page (then 150 if there were 0 errors), with at most 2 % errors.

If a checker lacks a check that applies, add it. Never weaken an existing check. Never drop an item because a model gets
it wrong.

## Hard rules

- Gold may come from code, from the source's structured field or from a labelling model or classifier (for example
  WildGuardMix's GPT-4 labels or OpenAlex subfields): the subnet's rules do not forbid model-written gold in training
  data (decision of 29 Oct). Record in each type's manifest entry how its gold was made.
- The dev items (`eval-v5/devset-v1/dev.jsonl`) and the dev sources (NHTSA recalls, Python PEPs, the RFC index) may
  be used (decisions of 29 Oct): FORMAT.md only advises against training on the dev items' exact content; no subnet
  rule forbids it. Don't duplicate a dev item into a built domain; the dev rows are added to training as they are.
- Never use as input:
  - the 3 held-out domains (EPA enforcement outcomes, visa fee-waiver rules, public-transit fare zones);
  - `data/generalist/heldout`.

  `shipping_rate` must not become a transit-fare table, and `expense_policy` must not become visa fee-waiver rules.
- Never edit the "select", "test" or "s1_holdout" fields of any config. Don't change existing data files or the
  training sets in `dataset/train_*`.
- Disk is 250 GB. Run `df -h` before downloads and builds, and stop if less than 40 GB is free.
- Respect documented rate limits, and use no login-gated pages. If a source needs an API key, a login or a gate
  (`wildguardmix` is gated on Hugging Face), stop that type and ask the owner, and build the others.
- Don't send the owner's e-mail address anywhere, for example as OpenAlex's `mailto` parameter.
- Never commit, upload or publish anything. No on-chain action. No coldkey use.
- Reason only from this subnet's code and docs. Don't bring in other subnets.
- Report numbers as measured. If something was skipped or failed, say so and include the output.
- The GPU may be busy with a training or scoring job. Don't start GPU work without asking.

## Report when done

For each type:
- rows per split, option counts, gold-position and yes shares;
- every check, with pass/fail and its output;
- the licence and the time taken.

Also list what was skipped, and why. Don't create a training set or start training.
