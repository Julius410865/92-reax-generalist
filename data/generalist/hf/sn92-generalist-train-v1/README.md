---
license: cc-by-4.0
pretty_name: SN92 generalist decision data (train v1)
task_categories:
- multiple-choice
- text-classification
language:
- en
- es
- de
- fr
- ja
- pt
- zh
- it
- ko
- ru
- pl
- ar
- tr
- vi
- id
- nl
- hi
- cs
- sv
- sw
- tl
- bn
size_categories:
- 100K<n<1M
---

# SN92 generalist decision data — train v1

109,547 synthetic training items for **decision models**: a model reads a structured state and a question and picks one
option. Items use the REAX decision format (`state` + `question` with type `choice`, `noul` (no/yes) or `score`
(ordered levels), `expected` = the key of the correct option). They cover 10 categories and 27 languages and were built
for the Bittensor subnet 92 (REAX) generalist track and for decision-model research.

No claim is made about any leaderboard, benchmark score or rank.

## Composition

| category | items |
|---|---:|
| support_ops_logistics | 26,463 |
| rules_policy_law | 18,271 |
| finance_commerce_insurance | 15,066 |
| tools_agent_routing | 12,079 |
| knowledge_reasoning | 9,987 |
| forecasting_risk_science | 8,853 |
| coding_data_it | 7,929 |
| math_quant | 4,707 |
| language_taste | 3,324 |
| safety_security_harm | 2,868 |

Types: choice 50,467 · noul 35,517 · score 23,563. `mix_tier = core` (31,746 items) follows a balanced target mixture
over the 10 categories; `mix_tier = extra` (77,801) is further valid material from over-supplied categories — sample
it with category weights if you need a balanced mix.

Languages (question and options verified with fastText lid.176 + script checks): English 68,539 (62.6 %); 37.4 % in 25
other languages (es 4,008 · de 3,992 · fr 3,590 · ja 3,489 · pt 3,345 · zh 3,104 · it 2,922 · ko 2,424 · ru 2,061 ·
pl, vi, ar, tr, id, nl, cs, hi, sv ~1,050-1,300 each · sw 643 · tl 493 · bn 354; < 10 items each for uk, yo, mr, te,
which are likely detector noise). 3,561 items are controlled translations of other items (same gold); the rest is
native. 882 items carry `lang_verified = false` (declared language kept).

## Fields

`id, category, family, bench_shape, qtype, lang, state, question{type, instructions, criteria}, expected, gold_basis,
generator, verifiers, ancestry{root, template_id, source_row, cf_pair, cf_role, translation_of, author_family},
licence, lane, mix_tier, quality, rationale` (some fields are absent for some lanes). Render a prompt from `state`,
`question.instructions` and the lettered `question.criteria`; `expected` is a criteria key (for `noul`: `false`/`true`).
Counterfactual groups (`ancestry.cf_pair`, 22,395 items) are minimal edits of one state that flip or keep the gold; keep a group
together when you split the data.

## How it was made

* **World first where possible.** 80,631 items have `gold_basis = programmatic`: code samples a structured world
  (policies, ledgers, calendars, tickets, tool catalogues, tables), computes the answer, and the text is rendered from
  templates or written around fixed facts. Other gold bases: LLM labelers with blind cross-family agreement (15,066),
  construction / author-computed / executed (≈ 10,200), source-verified (2,394), adjudicated hard items (1,286).
* **Verification.** Model-written items were blind-solved by model families other than the author's and dropped on
  disagreement; programmatic items were cross-checked by at least one other-family solver.
* **Filters.** Option-content shortcut audit (answer position, longest/shortest/medoid option, lexical overlap, numeric
  rank) — families still flagged were removed; a state-free probe (small open model) removed items answerable without
  the state for model-written families; language truth gate; skeleton cap (≤ 8 counterfactual groups per decision
  skeleton per family); exact / near-duplicate removal.
* **Contamination screening, not a guarantee.** All items were screened against public benchmark corpora used by
  decision-model leaderboards (HF Decision Index public suites, AA Decision Index public components, JevBench public
  items and related public sets; exact hash, 13-gram, MinHash, MiniLM cosine with an e5 re-rank) and, by a separate
  custodian, against a sealed held-out benchmark (only aggregate results were returned): no lexical match was found;
  7,415 items whose MiniLM embedding came within our pre-declared threshold (cos >= 0.73) of a sealed item were removed
  even though the custodian read them as same-domain neighbours, not copies. Benchmark corpora were used for
  screening and aggregate shape statistics only; no benchmark item was given to a generator. Items derived from intent
  benchmark source datasets (CLINC150, BANKING77, MASSIVE) were removed from this release. Gated sets we could not
  access (e.g. WildGuardTest) were not screened.

## Synthetic data and model provenance

Item text comes from code and from language models. Author family per item (`ancestry.author_family`):

| source | items |
|---|---:|
| OpenAI models (procedural generator and templates written by GPT-6 Astra 40,026; GPT-6 Luna 9,578; GPT-6.1 Sol 426) | 50,030 |
| Anthropic Claude (Claude Code sessions; mostly code-composed worlds with Claude-written text fragments) | 21,859 |
| code / programmatic generators | 20,272 (code 10,310 + earlier procedural generator 9,430 + programmatic 532) |
| open-weight models (Qwen3.5/3.8, DeepSeek V3.2/V4, GLM-5.1/5.2, Gemma 4, Kimi K2.6/K3) | 16,100 |
| adjudicated hard items (mixed families) | 1,286 |

The per-item `generator` field names the model. Some items were generated with models whose providers' terms restrict
using their outputs to develop competing models (OpenAI, Anthropic; Moonshot's Kimi licence has an attribution
condition for very large products). Users are responsible for complying with the terms that apply to their use.

## Quality audit

A blind audit of a stratified 300-item sample (30 per category) by a reviewer that did not see the keys agreed with the
gold label on **296 / 300** items (98.7 %). 28 of the 300 sampled items (9.3 %) were flagged with a real defect, mostly
ambiguity (a rubric that can be read two ways, meta-reasoning text in the state); those sampled items were removed, the
rest of the set has a similar residual rate. Known limitations: strong template reuse in some families; the set is
medium-length heavy (few long documents); about 4 % of sampled items are answerable from general knowledge alone;
difficulty varies widely by family (language and safety items are easy for strong models; finance, support, rules and
math are harder).

## Personal data and safety

All persons, companies, accounts and identifiers are synthetic, except company names in real public SEC filings from
CUAD (354 contract items). Items were scanned for credential-like strings (API keys, private keys, tokens, card numbers
with CVV) and such items were removed. Invented person-style e-mail addresses on real-looking domains remain in about
2 % of items; they are fictional. If you find real personal data, please open a discussion and we will remove the item.
Some items contain harmful or offensive text (abuse, fraud and phishing examples, unsafe advice) because the task is to
classify, route or refuse it; the set contains no working exploit code, no weapon or drug synthesis instructions and no
real targets.

## Intended use

Training and evaluating decision models in a single-choice format. Not intended as a source of factual knowledge
(some worlds use fictional or pinned facts) or for medical, legal or financial advice.

## Licence and attribution

The compilation is released under **CC-BY-4.0**; each item carries its own `licence` (CC-BY-4.0 107,379, CC0-1.0
2,168). See `LICENCES.md` for source attributions (CUAD, Wikidata, UCI Bike Sharing) and model notes. Items derived from
the listed sources were adapted (re-worded and re-formatted to the REAX schema).

Files: `train-00000…00011.jsonl.gz` (JSON lines, gzip), `MANIFEST.json` (counts and per-shard sha256).
