# Generalist track: training-data plan for eval v5.1

Built from `eval-v5/devset-v1/FORMAT.md` and `DEV-CARD.md` (reax-subnet a0310f9) and the live state on 26 Oct 2026.
Goal: a 27 B model that beats the co-champions by a confirmed paired margin (~3-5 points) under v5.1.

## 0. Ground rules

* **The 300 dev items may be trained on** (decision of 29 Oct): FORMAT.md only advises against training on their exact
  content, and the dev set has weight 0 in every live score. Dev items that are trained on are no longer a check: score
  only dev items left out of training, or judge on other held-out data.
* **The dev sources may be trained on** (NHTSA recalls, Python PEPs, the RFC index; decision of 29 Oct): no subnet rule
  forbids it. Their three dev task types are then inflated, so report the dev score also without them (223 items).
* **Gold may be model-written** (a labelling model or classifier, decision of 29 Oct): no subnet rule forbids it.
* **The live pools use other sources than the dev set.** Treat the dev task types as a map of skills and formats, not of
  test content. Expect the live N part in particular to contain domains the dev set doesn't show.
* **Gap check.** Awards are held if your gain on public items is much larger than on sealed items. Its public items are
  the sealed pool's own public tiers (`same_family` / `proc_sealed`, docs/EVAL-V5.md), not the dev set. Spread each
  skill over several sources.
* **Overlap rule.** A task type whose source you trained on is capped at min(entry, base). Record which sources you used;
  ask in #92 how entrants declare overlap.
* **Licences.** The model must be Apache-2.0 / MIT / BSD. Prefer CC0, CC BY, MIT, Apache data. Avoid NC (non-commercial)
  sets. Every "verify" below means: read the dataset card before use.

## 1. What a point is worth (from the v5.1 weights)

Score = 0.6 T + 0.4 N (after panel scaling). Approximate share of the total score per task type, **if** the live types
match the dev types (they may not; more types = smaller shares):

| Part / area | Task type | gold | ≈ share of score |
|---|---|---|---|
| N (new domain) | each of 5 types | | **≈ 8 % each** |
| T language | nli, story_continuation | yes | ≈ 4.2 % each |
| T language | stance, wildguard | | ≈ 3.5 % each |
| T retrieval | arxiv_category, best_of_32, intent_utterance | yes | ≈ 4.0 % each |
| T arts | chord_from_notes, poem_pair | | ≈ 3.0 % each |
| T tools | next_api, tool_call_decision | yes | ≈ 3.0 % each |
| T tools | tool_retrieval, when2call | | ≈ 2.5 % each |
| T knowledge | logic_multistep | yes | ≈ 2.6 % |
| T knowledge | arith ×2, causal, chess, code_output, omniscience | | ≈ 2.2 % each |

**N is the biggest lever:** 40 % of the score over few task types, and "decisions from fresh public records or computed
rules" is exactly what generic data covers worst.

## 2. Format requirements (every row)

* Render with the v5 prompt (`v5.render_question`: system + "SHARED STATE … QUESTION … OPTIONS A: …"), not the old SN92
  prompt; train on both if you keep the SN92 data.
* **Many options:** live questions serve up to **26 options (A–Z)**. Include plenty of 10–26-option questions.
* **Multi-question items:** an item counts only if **all** its questions are right (e.g. WildGuard = exactly 3 yes/no,
  tool_call_decision and expense_policy have several). Train on grouped questions over one shared state.
* **IDK:** omniscience rows offer a last option "I don't know" (correct +1, wrong −1, IDK 0). Train the model to pick IDK
  when the answer isn't knowable from the state or its knowledge.
* **Balance:** shuffle option order; balance gold positions and yes/no shares (chance-corrected scoring zeroes a
  "first option" or "always yes" bias).
* **Fresh:** sealed items prefer records after 1 Aug 2026 (`fresh`), so reasoning over the given state matters more than
  memorised facts.

## 3. Per-task-type sources (the dev sources may be used too, since 29 Oct)

| Task type | Skill | Format | Source idea (besides the dev source) | Rows |
|---|---|---|---|---|
| arith_word_4 / _10 | multi-step arithmetic in prose | 4 / 10 options | **own generator** (exact gold, distractors from common slips); openai/gsm8k train (MIT, checked) converted to MC | 3 k |
| causal_yesno | cause/effect judgement | yes/no | own generator; COPA-style templates (verify licence) | 1.5 k |
| chess_best_move | pick the best legal move | up to 26 options (legal moves) | **Lichess/chess-puzzles (CC0, checked)**, legal moves listed as options | 2 k |
| code_output | predict program output | 2–10 options | **own generator**: random short Python programs, executed for gold; cruxeval-org/cruxeval (MIT, checked) | 3 k |
| logic_multistep (gold) | chained rules, multi-question | 2–7 options, several questions | own generator (rules → entities → queries), ProntoQA-style | 3 k |
| omniscience | facts with abstention | 5 options + IDK | **Wikidata (CC0)** fact questions + matched unanswerable/obscure variants whose correct label is IDK; avoid Nobel-prize facts | 3 k |
| nli (gold) | entailment / neutral / contradiction | 3 options | alisawuffles/WANLI (CC BY 4.0, checked); MultiNLI only its CC BY / MIT genres (mixed licences incl. CC BY-SA and 'other'); not SNLI | 3 k |
| stance | pro/con of an argument | yes/no | webis/args_me (CC BY 4.0, checked); own drafted + 2-model-verified pairs | 1.5 k |
| story_continuation (gold) | pick the true next passage | 4 options | public-domain fiction from Project Gutenberg, excluding titles the dev card lists | 2.5 k |
| wildguard | prompt harmful? response refusal? response harmful? | exactly 3 yes/no | allenai/wildguardmix (ODC-BY, checked; accept the HF gate); not Aegis 2.0 | 2.5 k |
| arxiv_category (gold) | topic of a paper from title+abstract | up to 26 options | **OpenAlex (CC0)** works with topics, excluding arXiv-hosted works | 2.5 k |
| best_of_32 (gold) | best matching document among many | up to 26 options | OpenAlex / PubMed Central OA abstracts: title → pick its abstract among distractors | 2.5 k |
| intent_utterance (gold) | utterance → intent among many | up to 26 options | **clinc/clinc_oos (CC BY 3.0), PolyAI/banking77 (CC BY 4.0), both checked**; not MASSIVE/SLURP/HWU64 (MASSIVE derives from SLURP) | 3 k |
| next_api (gold) | which API to call next | up to 26 options | **own fictional-API generator**; Salesforce/xlam-function-calling-60k (CC BY 4.0, checked; HF gate), glaiveai/glaive-function-calling-v2 (Apache-2.0, checked) | 2.5 k |
| tool_call_decision (gold) | per call: needed or not | several yes/no | own generator over fictional tool specs | 2.5 k |
| tool_retrieval | right tool for a request | up to 26 options | own generator; tool descriptions from public OpenAPI specs (verify licences) | 2 k |
| when2call | call / ask / answer / decline | 4 options | own generator; nvidia/When2Call (CC BY 4.0, checked) | 2 k |
| chord_from_notes | chord name from notes | up to 26 options | **own generator** (music theory, exact) | 1.5 k |
| poem_pair | spot the altered line | yes/no | public-domain poetry from Gutenberg collections; swap the last word of a line | 1.5 k |
| N: expense_policy | apply a policy to records | several yes/no | **own generator**: random policies × expense claims, computed gold | 3 k |
| N: shipping_rate | compute a tariff | 4–5 options | own generator: zone/weight/tariff tables | 3 k |
| N: python_pep_status | status of a spec document | 5 options | Python PEPs, **Ethereum EIPs (CC0)**, Rust RFCs (MIT/Apache), Kubernetes KEPs (Apache-2.0) | 2.5 k |
| N: rfc_status | standards-track status | 7 options | the RFC index, W3C / other standards bodies' public status lists (verify terms) | 2 k |
| N: nhtsa_recall_component | record → category among many | up to 26 options | NHTSA recalls, **openFDA recalls, CPSC recalls** (US gov, public domain) | 3 k |
| N: unknown live domains | decisions from fresh public records / rules | mixed | the 35 domains of section 3b (21 real-record, 14 computed) | 105 k |

## 3b. Part N: 35 training domains + 6 held out (revised 26 Oct)

The dev N types show four shapes (DEV-CARD): real record → one of many categories (26 options); real record → its
real-world status (5–7 options, the outcome is *not* stated in the record); rules + several cases → yes/no each (multi-question);
rules / table + case → computed value (4–5 options). The dev mix is 3 real-record : 2 computed, kept here (21 : 14).
Records go into the question text (no `state`), one question per prompt as served. 3,000 train items per domain (~105 k items) + 150 select + 150 test each; real-record sources with fewer records use all they have (no duplication).
Licences: US federal works are public domain; everything marked "verify" needs its terms read before use.

*Removed on 27 Oct 2026 (owner decision): #12, #15, #16, #18, #19 — their sources need API keys or a login, or refuse this machine.*

**Real records: status / outcome (5–7 options)**

| # | Domain | Record → label | Source / licence |
|---|---|---|---|
| 1 | Ethereum improvement proposals | title + abstract → status (Draft … Final, Stagnant, Withdrawn, Living) | ethereum/EIPs, CC0 |
| 2 | Rust RFCs | summary → merged / closed / postponed | rust-lang/rfcs, MIT/Apache + GitHub metadata |
| 3 | Kubernetes enhancements (KEPs) | summary → stage (alpha / beta / stable / deferred / withdrawn) | kubernetes/enhancements, Apache-2.0 |
| 4 | Apache Software Foundation projects | description → incubating / graduated / retired | ASF project metadata, Apache-2.0 |
| 5 | US Congress bills | title + summary → furthest status (introduced … became law, vetoed) | GovInfo / congress.gov bulk, US gov |
| 6 | Clinical trials | design summary → overall status (completed / terminated / withdrawn / …) | ClinicalTrials.gov, verify terms |
| 7 | FDA drug products | product record → marketing status (Rx / OTC / discontinued / tentative) | Drugs@FDA, US gov |

**Real records: severity / class (3–5 options)**

| # | Domain | Record → label | Source / licence |
|---|---|---|---|
| 8 | Software vulnerabilities | description → CVSS severity | NVD, US gov (CVE text: verify) |
| 9 | Package security advisories | advisory → severity | GitHub Advisory Database, CC BY 4.0 |
| 10 | Medical-device recalls | recall text → class I / II / III | openFDA device recalls, US gov |
| 11 | Aviation accidents | narrative → highest injury severity | NTSB, US gov |
| 12 | ~~Meat & poultry recalls~~ | ~~recall notice → health-risk class~~ | ~~USDA FSIS, US gov~~ |

**Real records: one of many categories (up to 26 options)**

| # | Domain | Record → label | Source / licence |
|---|---|---|---|
| 13 | Consumer-product recalls | description → hazard type | CPSC recalls API, US gov |
| 14 | Severe weather | event narrative → event type | NOAA Storm Events, US gov |
| 15 | ~~Workplace inspections~~ | ~~citation text → standard group / industry~~ | ~~OSHA enforcement data, US gov~~ |
| 16 | ~~Federal contract notices~~ | ~~notice → NAICS sector~~ | ~~SAM.gov, US gov~~ |
| 17 | EU public tenders | notice → CPV division (capped at 26) | TED, EU reuse policy, verify |
| 18 | ~~Patents~~ | ~~abstract → CPC section / class~~ | ~~USPTO bulk data, US gov~~ |
| 19 | ~~Company filings~~ | ~~business description → SIC division~~ | ~~SEC EDGAR, US gov (verify for filer text)~~ |
| 20 | Federal Register documents | summary → issuing agency | federalregister.gov API, US gov |
| 21 | NASA technical reports | abstract → subject category | NASA NTRS, mostly US gov, verify |

**Computed rules (generators, exact gold)**

| # | Domain | Shape |
|---|---|---|
| 22 | Expense policy ✓ built | rules + claims → yes/no each |
| 23 | Shipping rate ✓ built | tariff + parcel → price |
| 24 | Parental-leave eligibility | rules + employees → yes/no each |
| 25 | Return / refund policy | policy + orders → full / partial / none |
| 26 | Grant eligibility | criteria + applicants → yes/no each |
| 27 | Building-permit requirements | code rules + projects → permit type |
| 28 | Insurance coverage | clauses + claims → covered yes/no each |
| 29 | Tiered utility tariff | kWh bands + fixed fees → bill |
| 30 | Parking fees | time bands, caps, discounts → fee |
| 31 | Payroll overtime | hours, rates, overtime rules → pay |
| 32 | Late fees and interest | schedule + payments → amount owed |
| 33 | Progressive income tax | brackets, allowances → tax due |
| 34 | Checkout discount stacking | coupons, loyalty rules → final price |
| 35 | Room-booking rules | constraints + requests → allowed yes/no each |

**Held out (never trained on; transfer check only)**

The three dev-set sources (NHTSA recalls, Python PEPs, the RFC index) were held out here until 29 Oct; they may now be
trained on (section 0).

| Domain | Shape | Why |
|---|---|---|
| EPA enforcement cases → outcome | real-world outcome | new, unseen |
| Visa fee-waiver rules | rules → yes/no each | new, unseen |
| Public-transit fare zones | table → fare | new, unseen |

## 3c. Staged training (27 Oct)

Train in stages instead of one long run. Each stage continues the previous stage's best LoRA checkpoint, is scored on
the same fixed test split and must show a measurable change before the next stage starts. A stage is **submitted only
when it clears the champion locally**. The validator accepts at most 4 new generalist submissions per coldkey in 7 days
and 2 open at once (`MAX_NEW_PER_COLDKEY_WEEK`, `MAX_OPEN_PER_COLDKEY_TRACK`). A submission that loses still uses one.

**Main new source: `decisionmodels/sn92-generalist-train-v1`** (rev 2241ec2c5e98, CC BY 4.0, 109,547 items, 10 categories,
27 languages, published by the operator for this track). It is downloaded to `data/generalist/hf/sn92-generalist-train-v1/`.
`SOURCE.json` there holds the revision, the licence and the sha256 of every shard; all 11 match the LFS hashes. Rows are
converted to v5.1 on load (`data.py`, kind `s1`):

* `choice` options are re-keyed A.. in their order.
* `score` levels are re-keyed A.. in level order and never shuffled.
* `noul` becomes a yes/no question with `yes` first. The s1 renderer puts false first, so the letters cannot be kept as they are.

**Fixed held-out split.** 1 % of groups go to select and 2 % to test, by sha256 of the group. The group is the
publisher's `split_key`, else the counterfactual pair, else the root, so templates and counterfactual pairs are never
split. The split ignores every filter, so no stage ever trains on a held-out row. The stage order is a second hash over
the training rows; each stage takes a slice of it (`take`).

**Licence choice (yours).** About 72 k items were written with OpenAI or Anthropic models, whose terms restrict using
outputs to build competing models. To train only on the other ~37 k, set
`"exclude_author_family": ["openai", "anthropic"]` on every `s1` entry of every stage config, including select and test.

**Stages** (counts measured with the reax-1.1 tokenizer; time on one A100 80 GB at ~2.2–3.6 M training tokens/h, plus the
evaluations)

| Stage | Config | Training rows | Tokens | Time |
|---|---|---|---|---|
| 0 | none: the base's report (`reports/base.json`) | n/a | n/a | ~0.5 h |
| 1 | `stages/stage1.json`: first 5,000 core items | 4,999 | 3.1 M | ~1.5–2 h |
| 2 | `stages/stage2.json`: the remaining core items + 25 % replay of stage 1 | 25,827 + 1,249 | 16.7 M | ~5–8.5 h |
| 3 | `stages/stage3.json`: the 12 generated task types + 25 % replay of the core | 51,144 + 7,706 | 19.7 M | ~6–10 h |
| 4 | written when the section 3b domains exist: new domains + replay | n/a | n/a | n/a |
| 5 (optional) | the 77.8 k extra-tier items, only if stage 2 was still improving | ~76 k | ~62 M | ~17–28 h |

The shared evaluation splits are prepared once (`prepared/eval`):
* select: 3,875 questions, 1.4 M tokens. It holds the generated select files plus 818 HF items.
* test: 6,882 questions, 3.2 M tokens. It holds the generated test files, the 300 dev items (432 questions; scored, never
  trained on) and 3,411 HF items.
None of the 109,547 HF rows has a dev question's text.

**Running a stage**

```bash
tools/train_generalist/run_stage.sh stage1           # prepare, train from the base, score, compare, weight check
tools/train_generalist/run_stage.sh stage2 stage1    # continue stage1's best checkpoint
```

**Checking that a stage really updated the model** (`tools/train_generalist/stage_check.py`)

| Check | Pass |
|---|---|
| `compare`: test items whose result changed vs the previous stage | > 0 (else NOT UPDATED) |
| `compare`: paired gain vs the previous stage, all test items | > 0 and > 2 SE (else NO GAIN) |
| `compare`: no source or task type (≥ 40 items) more than 2 points and 2 SE below the previous stage | none flagged (else REGRESSION) |
| `weights`: the adapter's change from the base | not zero; moved since the previous stage |
| `weights --merged`: the merged export differs from the base | on every sampled tensor checked |

**When to submit.** Score the champion's public merged weights once into `reports/champion.json`
(`stage_check eval --base <champion dir>`). After that, `compare` prints a submit line. It reads CANDIDATE only when the
stage beats the champion on the paired test items by max(1.0, 2 SE), with no source behind and no regression.
Then export (`export.py`) and run `weights --merged`. A commitment is made only after you approve that specific entry.
When a stage is not a candidate, keep training: the next stage starts from it either way.

## 4. Keep from the current recipe

* `decisionmodels/sn92-specialists` train rows (CC BY 4.0): ~40 k, capped per category.
* **Anchors (self-distillation):** ~5 k MMLU auxiliary-train / AQuA-RAT style questions labelled with the base model's own
  answer distribution, so fine-tuning doesn't erase general ability.
* **Multilingual:** translate ~20 % of rows into the languages the SN92 set covers (de, fr, es, pt, it, nl, pl, tr, sv, ja).

Total ≈ 40 k (SN92) + ~70 k (new) + 5 k anchors ≈ **115 k rows**.

## 5. Splits and measurement

* For every generator and source: **train / select / test splits by generator seed or source record**, never by row.
* Selection set: ~150 items per task type (not the dev set). Test set: a second ~150 per task type, used once per release.
* Compare **paired** against a co-champion's public weights (e.g. reax-knockout/sn92-gen-a1@d57f18b9) and your base, with
  `tools/score_v5.py` (paired bootstrap SE). Ship only when the gain clears ~3–5 points on the test set **and** the dev
  set shows no much larger gain than the private test set (your own gap check).

## 6. Reference models

| Role | Model | Why |
|---|---|---|
| Base to fine-tune (declared `base_model`) | **decisionmodels/reax-1.1@142b19355af0** (Apache-2.0; ← reax-1 ← pplx-decider-v1.2 ← Qwen3.8-27B) | best mean S_eff of any base among entries (75.93, n=5); the operator's newest decision model |
| Alternative base, test first | baselabs/mammoth-1@61cec44c281c (MIT; ← Qwen/Qwen3.5-27B) | newest; in the operator's engine v2 lineup; no scored entry yet |
| Bar to beat | uid 250 reax-knockout/sn92-gen-a1@d57f18b9 (co-champion, S_eff 76.83 on v4) | strongest co-champion; public weights, so it can be run in the paired comparison |
| Anchor teacher + own gap check | the declared base itself | anchors use its answers; the validators' gap check and overlap rule compare against the declared base |

Step 0 before any training: score reax-1.1, mammoth-1 and uid 250 on the v5.1 dev set plus the private test set; pick the
base with the best v5.1 score (the champions were measured on v4, so their v5.1 standing is unknown).

## 7. Order of work

1. Generators with exact gold first (arithmetic, code output, logic, chords, policies, tariffs, fictional APIs): cheap,
   unlimited, licence-free, and they cover ~45 % of the score map.
2. Many-option retrieval and intent sets (OpenAlex, CLINC150, Banking77).
3. Language sets (NLI, stance, story, safety) and IDK facts (Wikidata).
4. Extra N-style domains.
5. LoRA run on the base (REAX 1.1 or mammoth-1) in the stages of section 3c, each stage checked before the next;
   submit only a stage that clears the champion locally.
