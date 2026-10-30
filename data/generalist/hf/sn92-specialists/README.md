---
license: cc-by-4.0
language:
- en
- de
- fr
- es
- pt
- it
- nl
- pl
- tr
- sv
- ja
- ko
- zh
- hi
- id
- vi
- ar
pretty_name: SN92 specialist decision data (train + dev)
size_categories:
- 10K<n<100K
task_categories:
- text-classification
tags:
- decision-making
- synthetic
- bittensor
- sn92
viewer: false
---

# SN92 specialists: train + dev data for 20 business use cases

Synthetic, realistic **decision tasks** for 20 business use cases, published by REAX (Bittensor subnet 92) so that miners can
train and test **Jev-compatible specialist models**: small open-weight models that answer typed decision questions
(choice, noul = yes/no probability, score = ordinal level). This repository holds the public **train** and **dev** splits.
**The sealed split is private** and is used for scoring; it is not in this repository.

* **Licence:** CC-BY-4.0 (see `LICENSE`). Please credit "REAX / decisionmodels, SN92 specialists dataset".
* **Size:** 47,997 train rows and 7,956 dev rows in 20 categories.
* **Active tracks:** the first two specialist tracks, **demand_forecasting** and **risk_assessment**, run **16 Oct 2026, 12:00 UTC
  to 30 Oct 2026, 12:00 UTC**. The other 18 categories are included now so you can prepare for later tracks.
  Rules: [SPECIALIST-TRACKS.md](https://github.com/reaxlabs/reax-subnet/blob/main/docs/SPECIALIST-TRACKS.md).

## Layout

```
<category>/train.jsonl     # training rows
<category>/dev.jsonl       # public dev rows (use for local previews, not for the final ranking)
<category>/dev/dev.jsonl   # identical copy of dev.jsonl, so that reax-spec-eval 1.2.0rc3 and older finds it
demand_forecasting/train-factory-20261017.jsonl   # additional training rows, 18 Oct 2026 (see below)
risk_assessment/train-factory-20261017.jsonl      # additional training rows, 18 Oct 2026 (see below)
errata/errata-lang-20261018.jsonl                 # ids of older rows whose text language does not match `lang`
LICENSE
README.md
```

## Download and local dev score

```
huggingface-cli download decisionmodels/sn92-specialists --repo-type dataset --local-dir sn92-specialists
reax-spec-eval ./my-model --dev ./sn92-specialists --category demand_forecasting --hotkey <your hotkey>
```

`reax-spec-eval` (package `reax-subnet`, extra `spec`) runs the validator's rule checks, prompt, container and scorer on the dev
rows of your category. A dev score is a preview, not a ranking: validators score on fresh sealed items.
`--dry-run` only runs the rule checks and the tensor hash and needs no GPU. The `<category>/dev/dev.jsonl` copies exist only
so that older `reax-spec-eval` versions (up to 1.2.0rc3) accept the dataset root; newer versions read `<category>/dev.jsonl`.
Both files are identical, so do not count the dev rows twice in your own tooling.

## Row schema (JSON lines)

| Field | Meaning |
|---|---|
| `id` | unique row id |
| `category`, `family`, `domain` | use case, task family inside it, business domain of the case |
| `split` | `train` or `dev` |
| `difficulty` | `easy`, `medium` or `hard` (as designed by the generator) |
| `lang` | language of the case text (mostly `en`) |
| `state` | the messy input: ticket, contract excerpt, transaction log, telemetry, record set ... (a JSON object, or text for programmatically generated rows) |
| `question` | `{type, instructions, criteria}`; `type` is `choice`, `noul` or `score` and `criteria` describes the options or levels |
| `labels` | the answer options in order |
| `expected` | the gold answer |
| `target_probs` | soft target distribution over `labels` (useful for calibration training) |
| `rationale` | short reason for the gold answer |
| `state_sha256` | hash of the state (for your own deduplication) |
| `provenance` | generator, writer and labeler models (LLM rows) or generator and seed (programmatic rows) |
| `license` | `CC-BY-4.0` |

## Splits and counts

Rows after filtering. In brackets: programmatic-gold rows (included in the total).

| Category | Train | Dev | Task families (dev) |
|---|---:|---:|---:|
| `advertising` | 2,059 (1,000) | 373 (60) | 10 |
| `code_linting` | 1,978 (1,000) | 349 (60) | 10 |
| `customer_support` | 2,053 (1,000) | 338 (60) | 10 |
| `demand_forecasting` (active 16-30 Oct) | 4,046 (3,000) | 508 (180) | 12 |
| `ecommerce` | 2,059 (1,000) | 382 (60) | 10 |
| `feature_extraction` | 3,052 (2,000) | 449 (120) | 11 |
| `financial_crime` | 3,050 (2,000) | 455 (120) | 11 |
| `gaming` | 2,052 (1,000) | 368 (60) | 10 |
| `insurance_claims` | 2,048 (1,000) | 388 (60) | 10 |
| `knowledge_graphs` | 3,055 (2,000) | 435 (120) | 11 |
| `lead_generation` | 2,053 (1,000) | 381 (60) | 10 |
| `legal_compliance` | 2,053 (1,000) | 378 (60) | 10 |
| `llm_guardrails` | 2,051 (1,000) | 378 (60) | 10 |
| `model_routing` | 2,059 (1,000) | 370 (60) | 10 |
| `moderation` | 2,052 (1,000) | 362 (60) | 10 |
| `other` | 3,048 (2,000) | 428 (120) | 11 |
| `recruiting` | 2,062 (1,000) | 389 (60) | 10 |
| `risk_assessment` (active 16-30 Oct) | 3,037 (2,000) | 443 (120) | 11 |
| `scientific_discovery` | 2,053 (1,000) | 386 (60) | 10 |
| `search_retrieval` | 2,053 (1,000) | 385 (60) | 10 |
| **Total** | **47,997 (27,000)** | **7,956 (1,620)** | |

## How the labels were made

Two kinds of rows, marked in `provenance.generator`:

1. **LLM-written rows** (`sn92-gen`; 20,997 train, 6,336 dev). An open-weight *writer* model drafts an item for a task
   family with a pre-assigned target answer; any rule, table or base rate the answer needs is placed inside the state.
   Two other open-weight models (three for sealed data) then answer **blind**. A row is kept only if all of them agree with
   the target and none flags it as ambiguous or as revealing its answer. Rule checks follow (schema, length, leak phrases,
   neutral option texts, exact and near-duplicate removal).
2. **Programmatic-gold rows** (`sn92-procgen`; 27,000 train, 1,620 dev). Code builds each case, computes the exact answer
   and renders noisy text (shuffled logs, time zones, holidays, exceptions, distractors). A second, independent implementation
   parses the text back and agreed on every row. These are the harder items: a 4B model scores far lower on them than on
   LLM-written rows.

**Models used for text and labels** (all open-weight, run on Chutes; licences checked on 14 Oct 2026): DeepSeek-V3.2 and
DeepSeek-V4-Flash-0731 (MIT), GLM-5.1 and GLM-5.2 (MIT), Qwen3.5-397B-A17B and Qwen3.8-27B (Apache-2.0), Kimi K3 (Kimi K3 License,
modified MIT). **No output from Claude, OpenAI or TypeSafe/Jev models is used as a label or as training text**; every LLM row records its
writer and labelers in `provenance`.

**Separation from the sealed split.** Within each split near-duplicates (8-gram containment) were removed, dev rows overlapping
train were dropped, and sealed rows overlapping train or dev were dropped. Before publishing, every row was also checked against all
sealed ids, text hashes and 8-gram overlap; nothing matched. Programmatic rows share templates and task families with the private
sealed split by design (different seeds and names), and the sealed split also contains other items, so a model that has only
memorised these rows will not score well on it.

## Known limitations

* **Synthetic.** This is not real customer data. Models trained only on it may learn the generators' style.
* **Gold quality.** In a blind check by independent reviewers (not used as labels), the gold answer was confirmed on about 94-100 % of
  sampled LLM-written items, and about 3-5 % of those have a wrong or arguable gold; about 10 % are ambiguous at rubric boundaries.
  Programmatic rows are exact once the rule wording is right (a blind sweep over all 27 families found one wording bug, fixed before release).
* **Difficulty.** LLM-agreement rows are easier than real-world cases; the programmatic rows separate models much better.
* **Fabricated sensitive-looking strings.** Cases about fraud, guardrails and moderation contain invented names, e-mail addresses and
  SSN-format numbers. They are fabricated test content, not real personal data. Rows containing key-like strings (API keys, private-key
  headers, tokens) were removed before publishing so that secret scanners do not trip on them.
* **Language.** Mostly English, with some German, French, Spanish, Portuguese and others where they fit the use case.

## Wording

Use "Jev-compatible". Models trained on this data are not "Jev" models. Nothing here is investment advice or a statement about
any token.

## Citation

> REAX / decisionmodels, *SN92 specialists: train and dev data for 20 business use cases*, 2026. CC-BY-4.0.

## Additional training rows (18 Oct 2026)

`demand_forecasting/train-factory-20261017.jsonl` (1,869 rows) and `risk_assessment/train-factory-20261017.jsonl` (2,052 rows)
add new training rows with the same schema. The existing files are unchanged.

* **Writers and labelers:** open-weight models only (Gemma 4 31B, GLM-5.1, DeepSeek V3.2 / V4 Flash, Qwen 3.5 / 3.8). Every
  row records its writer, its blind labelers and their licences in `provenance`. No output of Claude, OpenAI or TypeSafe/Jev
  models is part of any row.
* **Languages:** about 35 % of rows are non-English, spread over 16 languages, with locale-native names, currencies and dates.
* **Checks every row passed:** the labelers agree with the target; no writer notes; exact and near-duplicate removal (8-gram)
  against all public and private data; a language check (the text must be in the tagged language); an independent open-weight
  judge (unique answer, no missing fact, answer not given away); a second judge for worked results or notes in the state
  that give the answer away. An independent blind review of a sample then removed task families and one writer model with
  high defect rates.
* **Known limitations:** `difficulty` is the writer's tag and is often too high (about a third of sampled rows were easier
  than tagged). A blind review of the remaining rows still found about 13 % with a disputable or under-specified label, which
  is lower than in the earlier data under the same review.

## Errata

* **18 Oct 2026 (all categories):** `errata/errata-lang-20261018.jsonl` lists 1,209 of 56,040 published train/dev rows
  whose text is not in the language given by `lang` (mostly English text under a non-English tag). The rows are unchanged;
  filter them out if you train per language. Labels are not affected.

* **16 Oct 2026 (demand_forecasting, risk_assessment):** some LLM-written rows kept the writer's working note in `rationale`
  (for example "I will change the base rate to 1.5"), but the change was never applied to `state`, so the gold label did not
  fit the published state. We removed 35 such rows (train: 12 + 12, dev: 5 + 6) and corrected 2 dev labels
  (risk_assessment dev `4c0612505881` yes -> no, `6491b86cb2f0` tier_4_low -> tier_3_standard). Thanks to the miner who
  reported it. Scoring uses the private sealed items only and was not affected; the same defect was removed from the sealed
  items before the next scored draws.
