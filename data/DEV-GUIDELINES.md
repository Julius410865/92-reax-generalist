# Generalist track: development guidelines for training-data domains

Rules for adding a domain to the generalist training set (DATASET-PLAN.md section 3b), for both computed-rule generators and
real-record builders. A domain is merged into `train.json` only when it meets every "must" below and passes the checks in
section 7. Where this text and `eval-v5/devset-v1/FORMAT.md` differ, FORMAT.md (and the code behind it) wins.

## 1. Where things go

| What | Path |
|---|---|
| Computed-rule generators | `tools/gen_generalist.py` (one `gen_<domain>` + one `TASKS` entry per domain) |
| Real-record download, one script per source | `tools/records/fetch_<domain>.py` → `data/generalist/raw/<domain>/<snapshot-date>/` |
| Real-record build (raw → v5.1 rows) | `tools/records/build_<domain>.py` → `data/generalist/rec/<domain>.<split>.jsonl` |
| Held-out domains (never trained on) | output to `data/generalist/heldout/` only |
| Quality checker and reports | `tools/check_generalist.py` → `data/generalist/reports/<domain>.json` |
| Tests | `tests/test_gen_generalist.py`, `tests/test_records.py` |

Naming: task type `snake_case` as `<source>_<label>` (`eip_status`, `cpsc_hazard`, `parking_fee`). Row ids
`gen-<task>-<split>-<i>` (computed) and `rec-<task>-<split>-<i>` (records).

## 2. Row contract (every row, both kinds)

* **Must** pass `reax_subnet.spec.v5.validate_mirror_row`.
* `tier "mirror"`, `part "N"`, `scope "new_domain"`, `public false`, `split` set, `area` / `gold` / `half` fixed per task type.
* The record or the rules go into `questions[].instructions`; no `state` (the dev N types have none).
* Multiple-choice keys are position codes `A`, `B`, …; yes/no questions use exactly `yes` / `no`. Never add an IDK key.
* Options: 2–26 per question for computed domains. A real-record domain may keep its full official category list (up to
  255); the trainer caps it to 26 per draw the way the live eval does.
* `fresh: true` only if the record (or the generator run) is dated on or after 1 Aug 2026. Old records are `fresh: false`.
* `source` names the source and snapshot (`eip_2026-10-27`); `source_id` is the record's own id (`EIP-1559`) for records
  and the generator id for computed rows, so every row can be traced back.
* One prompt with all its options stays under ~2,000 tokens; the manifest reports the p99.

## 3. Computed-rule domains

**Structure.** Write each domain as three separate steps:

1. `case = draw_<domain>(rng)`: a structured instance (the rules' parameters and the cases), all as plain data.
2. `answer = solve_<domain>(case)`: a pure function, no randomness, no text.
3. `text = render_<domain>(case, rng)`: the instructions and options.

The gold answer comes from `solve_`, never from text. A **second solver** in `tools/check_generalist.py` reads the rendered
text only and must reach the same answer (section 7).

**Determinism.**

* All randomness comes from the `rng` passed in. No `random` module globals, no clock, no environment.
* Never iterate over a `set` or over dict keys built from a set when drawing: string hashing changes between runs. Use lists
  or `sorted()`.
* Raise `Retry` for an unusable draw; never loop forever inside a generator.

**Rule text must be unambiguous.**

* Every limit says whether it is inclusive: "40 hours or more", "under 2 kg", "within 30 days of the purchase date,
  counting the purchase date as day 0".
* Every amount has a unit and a currency. Every computed value has a rounding rule ("round the total to the nearest cent,
  halves up") applied at a stated step.
* Order of operations is stated where it matters ("apply the coupon before tax"; "at most one coupon per order").
* Dates are ISO (`2026-03-14`); weekdays, if used, are given explicitly.
* No outside knowledge is needed unless it is the skill being tested (no public holidays, tax law or exchange rates that
  are not in the text).

**Rules vary per item.** Each item draws its own rule parameters (bands, rates, caps, thresholds, which clauses exist),
otherwise the model learns one fixed policy instead of reading the rules. Add 1–3 irrelevant clauses per item so that every
clause has to be read.

**Options.**

* Numeric distractors come from **named mistakes**: missing fixed fee, wrong band, boundary off by one, discount applied in
  the wrong order, rounding at the wrong step. Add near values only to fill the remaining slots.
* All options use the same format (same decimals, same currency sign, same unit) so that no option stands out.
* `mc()` shuffles the gold position; the manifest must show it close to uniform.
* Yes/no domains: overall yes share between 40 % and 60 %. Answers within an item are drawn independently (no forced mix,
  which would itself be a cue).

**Multi-question items.** 3–6 cases per item, each case different, each decided by the rules alone. All questions must be
right for the item to count, so keep each one decidable in a few steps.

**Wording.** At least 5 instruction templates per domain, random entity names and amounts, varied clause order. Nothing
copied from the dev set: no templates, numbers or rule sets.

## 4. Real-record domains

**Download.**

* Official bulk files or APIs only, at their documented rate limits. No pages behind a login. No scraping against a
  site's terms.
* Store the raw responses unmodified, with the snapshot date, the URL list and a sha256 per file.
* Raw files are untrusted data: parse them from a separate directory with `python -I`, and never execute anything in them.

**Licence.**

* Record the licence and its URL for each source in the domain's manifest.
* A source marked "verify" in DATASET-PLAN.md stays out of `train.json` until its terms have been read and recorded.
* Keep the attribution list current: it goes into the model card and NOTICE.

**Labels.**

* Take labels from the source's **structured field** only (EIP `status:` header, bill latest-action code, recall
  `classification`). Never take them from free text.
* Keep only final states (Final, Withdrawn, Became law, Completed, Terminated, Retired). Drop records still in progress, or
  with a missing, conflicting or multiple label.
* Code-to-label maps (NAICS → sector, CPV → division, CPC → section, SIC → division) live in code as plain dicts, and are
  tested against the official code list.
* Where a second source exists, keep only records on which both sources agree.

**Record text.**

* Use a fixed labelled layout (`Title:`, `Summary:`, `Submitted:` …) with the record's own wording, cut at a sentence
  boundary to a per-domain character limit.
* Remove every field and phrase that states or implies the outcome: label words and their synonyms, resolution dates,
  "superseded by", "replaced by", final-action fields. Each domain keeps its scrub list in code, and the tests assert that
  none of its words remain.
* Privacy: mask the names, addresses and contact details of private individuals (accident narratives, inspection records,
  complaints). Names of companies, agencies and public officials acting in office may stay.

**Balance.**

* Cap each class in train at 3× the median class count.
* Build select and test with the same caps, and record the class prior in the manifest.
* Drop classes with fewer than 20 records rather than letting them appear only in test.

**Size.** Up to 3,000 train items per domain plus 150 select and 150 test. A source with fewer records uses what it has;
never duplicate records to reach the target.

## 5. Splits and leakage

* Computed domains: disjoint seed streams `<version>|<task>|<split>|<i>` (as in `gen_generalist.py`).
* Records: assign each record's split by `sha256(group key)`, never by row or by random draw. The group key is the recall
  number, bill id, trial id and so on, so that near-copies stay together and a record never changes split on a re-fetch.
* Deduplicate on normalised instruction text across all splits, all domains and `eval-v5/devset-v1/dev.jsonl`.
* The dev items (`eval-v5/devset-v1`) and the dev sources (NHTSA recalls, Python PEPs, the RFC index) may be trained on
  since 29 Oct: FORMAT.md only advises against training on the dev items' exact content; no subnet rule forbids it.
  The dev rows are added as they are, so a built domain must still not duplicate them (the dedup rule above).
* Never use as training input:
  * anything from the sealed live pools;
  * the held-out domains.
* `train.json` globs must not match `heldout/`. The checker asserts this.

## 6. Model-written content

* Gold labels of mirror rows may be computed, taken from the source's structured field, or assigned by a labelling model
  or classifier (for example WildGuardMix's GPT-4 labels, OpenAlex subfields): the subnet's rules do not forbid
  model-written gold in training data (decision of 29 Oct). The manifest records which of these a domain's gold is.
* Anchors (`kind: anchor`) are labelled by the declared base.

## 7. Checks before a domain is merged

`tools/check_generalist.py <domain>` writes `reports/<domain>.json`. A domain is merged only if every line passes:

| Check | Applies to | Pass condition |
|---|---|---|
| Schema (`validate_mirror_row`) | all | 100 % of rows |
| Determinism: generate twice, compare sha256 | computed | identical |
| Second solver (from rendered text) agrees with gold | computed | 100 % of all splits |
| Boundary unit tests on `solve_` | computed | all pass |
| Solve check: strong reasoning model on 50 items, every disagreement read by hand | computed | 0 unresolved |
| Hand audit against the original source page: 50 items, then 150 if 0 errors | records | ≤ 2 % errors |
| Leak test: bag-of-words classifier on record text only | records | not far above a deliberately weak baseline |
| Scrub test: no scrub-list word in any row | records | 0 hits |
| Shortcut test: answer predicted from option length, position or word overlap | all | close to chance |
| Gold-position balance and yes share | all | uniform ± 5 pts; yes 40–60 % |
| Duplicates across splits / domains / dev set | all | 0 |
| Licence recorded, no "verify" left | records | yes |
| Prompt length p99 | all | ≤ ~2,000 tokens |

**Never drop an item because the base model gets it wrong.** That removes exactly the hard items. Base-model misses only
decide which items are audited first.

## 8. Versioning

* Bump `GEN_VERSION` (or the builder's version) whenever any output row could change, and record why in the changelog
  below.
* A **test** split is frozen once any model has been scored on it. Changing it means a new version, and the base and the
  bar model (uid 250) are scored again on the new split.
* `manifest.json` holds counts, option counts, balance statistics and the sha256 of every file. Commit the manifest with
  the code that produced it.

## 9. Review checklist (per domain)

* [ ] Generator / builder follows sections 3 or 4; `TASKS` or the build entry is added.
* [ ] Tests in `tests/` cover the solver boundaries, the label map, the scrub list and split stability.
* [ ] `reports/<domain>.json` passes every check in section 7.
* [ ] One full row per task type added to `EXAMPLES.md` and read by a second person.
* [ ] Licence and attribution recorded (records).
* [ ] DATASET-PLAN.md section 3b updated with the actual counts.

## Changelog

* 2026-10-27: first version. Fixed `gen_next_api` drawing in set order (output changed with PYTHONHASHSEED); next_api
  rows regenerated under gen-1, before any model was scored on them. All 12 task types now reproduce byte for byte.
