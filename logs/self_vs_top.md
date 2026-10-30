# Submitted model vs top miner (SN92 generalist)

Measured on 2026-10-28 on this machine. Both models are scored by the validator's own `JointRunner` on the same
held-out splits (`prepared/eval_all`). Differences are paired: same items, bootstrap standard error over clusters.

## Models

| | **Submitted (ours)** | **Top miner** |
|---|---|---|
| Repo | `MstJeon410/sn92-gen-mam1@b90a6297d8f663eb35d56f063c556a2f1277d38f` | `danyloooah/sn92-generalist-m1-core2@c78c0a4aa874d1fa87d3d2b2efe84cc19bf52c24` |
| What it is | mammoth-1 + one LoRA (r32), `train_50k` checkpoint 521 | weight merge of 4 mammoth-1 fine-tunes (m87b 0.7, xflud 0.7, v3a 0.25, unreleased seed-1 0.25) |
| Declared base | `baselabs/mammoth-1@61cec44c` | `baselabs/mammoth-1@03007ab3` (same weights) |
| Parameters / size | 26,086,635,760 / 48.61 GiB, bf16 | 26,086,635,760 / 48.61 GiB, bf16 |
| Training data | 50,000 rows: 31,715 n_records + 18,285 openai_anthropic | v3a: 43,242 rows, 58 task types (incl. PEPs, RFC index, NHTSA); m87b: 48,000 rows from ~85 sources; xflud: not stated |

## Summary

| Measure | Ours | Top | Ours − top |
|---|---|---|---|
| Test score (3,417 items) | **77.55** | 72.95 | **+4.60 ± 1.23** |
| **Dev score `dev_v51` (300 items, closest to the validator)** | 74.55 | **80.60** | **−6.04 ± 2.50** |
| Test item accuracy | **0.811** | 0.753 | +0.058 |
| Validation score (2,466 items) | **79.46** | 69.93 | +9.53 |
| Validation item accuracy | **0.786** | 0.701 | +0.085 |
| Test items whose result differs | | | 530 of 3,417 |

## Test split by source

| Source | Items | Ours | Top | Ours − top | Favours |
|---|---|---|---|---|---|
| dev | 300 | 74.55 | **80.60** | −6.04 ± 2.50 | top (it trained on 3 dev sources) |
| hf | 718 | 88.05 | **90.14** | −2.09 ± 1.41 | top (overlapping public datasets) |
| n_records | 1,695 | **64.14** | 50.26 | +13.88 ± 2.17 | us (our training sources) |
| openai_anthropic | 704 | **83.47** | 70.80 | +12.68 ± 3.31 | us (our training sources) |

## Dev set by task type (where the validator gap comes from)

| Task type | Items | Ours | Top | Ours − top |
|---|---|---|---|---|
| arith_word_10 | 6 | 40.0 | 100.0 | −60.0 |
| shipping_rate | 22 | 50.0 | 93.8 | −43.8 |
| chord_from_notes | 8 | 57.1 | 85.7 | −28.6 |
| arxiv_category | 12 | 60.0 | 80.0 | −20.0 |
| expense_policy | 21 | 90.2 | 100.0 | −9.8 |
| wildguard | 8 | 35.2 | 42.2 | −7.0 |
| arith_word_4 | 6 | 75.0 | 75.0 | 0 |
| chess_best_move | 3 | 50.0 | 50.0 | 0 |
| logic_multistep | 12 | 87.3 | 87.3 | 0 |
| nhtsa_recall_component | 34 | 82.8 | 82.8 | 0 |
| nli | 20 | 84.6 | 84.6 | 0 |
| best_of_32, causal_yesno, intent_utterance, next_api, omniscience, poem_pair, stance, story_continuation, tool_call_decision, tool_retrieval, when2call | 5–12 each | 100.0 | 100.0 | 0 |
| rfc_status | 22 | **47.2** | 44.4 | +2.8 |
| python_pep_status | 21 | **25.0** | 18.8 | +6.2 |
| code_output | 9 | **100.0** | 66.7 | +33.3 |

Dev groups are small (3–34 items), so single groups are noisy.

## Records (n_records, test)

| Domain | Items | Ours | Top | Ours − top |
|---|---|---|---|---|
| ghsa_severity | 150 | 40.3 | 9.7 | +30.6 |
| fda_device_recall_class | 150 | 69.1 | 39.2 | +29.9 |
| nvd_cvss_severity | 150 | 57.6 | 28.1 | +29.5 |
| fda_drug_marketing_status | 150 | 55.9 | 28.8 | +27.0 |
| asf_podling_outcome | 29 | 91.7 | 66.7 | +25.0 |
| congress_bill_status | 150 | 51.9 | 39.3 | +12.6 |
| eip_status | 81 | 57.7 | 48.1 | +9.6 |
| ntsb_injury_severity | 150 | 65.6 | 59.4 | +6.1 |
| fedreg_agency | 150 | 86.4 | 81.4 | +5.0 |
| noaa_storm_event_type | 150 | 80.0 | 75.2 | +4.8 |
| ted_cpv_division | 150 | 78.4 | 76.3 | +2.2 |
| rust_rfc_outcome | 85 | 39.4 | 37.5 | +1.9 |
| ntrs_subject_category | 150 | 59.9 | 63.8 | −3.9 |

## openai_anthropic (test)

| Category | Items | Ours | Top | Ours − top |
|---|---|---|---|---|
| forecasting_risk_science | 4 | 100.0 | 50.0 | +50.0 |
| coding_data_it | 37 | 100.0 | 68.8 | +31.2 |
| support_ops_logistics | 111 | 74.0 | 49.3 | +24.7 |
| finance_commerce_insurance | 114 | 66.7 | 45.7 | +21.0 |
| rules_policy_law | 90 | 86.0 | 70.3 | +15.7 |
| math_quant | 75 | 56.6 | 50.0 | +6.6 |
| tools_agent_routing | 113 | 97.6 | 91.6 | +6.0 |
| language_taste | 54 | 100.0 | 100.0 | 0 |
| safety_security_harm | 32 | 100.0 | 100.0 | 0 |
| knowledge_reasoning | 74 | 97.9 | 100.0 | −2.1 |

## hf (test)

| Category | Items | Ours | Top | Ours − top |
|---|---|---|---|---|
| support_ops_logistics | 118 | 94.1 | 91.7 | +2.4 |
| coding_data_it | 88 | 84.8 | 83.3 | +1.5 |
| rules_policy_law | 138 | 94.3 | 94.3 | 0 |
| safety_security_harm | 28 | 100.0 | 100.0 | 0 |
| language_taste | 10 | 100.0 | 100.0 | 0 |
| forecasting_risk_science | 122 | 85.2 | 88.9 | −3.7 |
| finance_commerce_insurance | 105 | 81.3 | 87.1 | −5.7 |
| knowledge_reasoning | 73 | 86.3 | 92.2 | −5.9 |
| tools_agent_routing | 30 | 76.8 | 86.1 | −9.3 |
| math_quant | 6 | 50.0 | 75.0 | −25.0 |

## Copy rule (answers)

Mean Jensen–Shannon divergence of our answers vs the top miner's on the test split: **0.0514 bits**; same option order on
**23.2 %** of questions with 3+ options. The rule marks a model as derived below 0.005 bits, or below 0.05 bits with the
same order on ≥ 99 %, so ours is not derived.

## Merges of the two (core2 + w × our change)

| Model | Validation | Test | **Dev** | n_records | openai_anthropic | vs top: test / dev |
|---|---|---|---|---|---|---|
| Top (w = 0) | 69.93 | 72.95 | **80.60** | 50.26 | 70.80 | – |
| **Merge w 0.5** | 76.30 | 76.22 | **79.90** | 57.71 | 77.55 | +3.28 ± 0.91 / −0.69 ± 1.49 |
| Merge w 0.75 | 77.38 | 77.02 | 78.79 | 60.62 | 79.68 | +4.07 ± 0.98 / −1.81 ± 1.66 |
| Merge w 1.0 | 78.64 | 77.91 | 77.56 | 64.54 | 79.96 | +4.96 ± 1.08 / −3.04 ± 2.02 |
| Ours | 79.46 | 77.55 | 74.55 | 64.14 | 83.47 | +4.60 ± 1.23 / −6.04 ± 2.50 |

Merge w 0.5 (`/models/merge-w05`) ties the top miner on dev and is +3.3 on test; it is the base of the `train_42k` run.

## Reading this

* Our overall lead comes from sources we trained on (n_records, openai_anthropic); it does not show we would beat the top
  miner on the validator.
* On the dev set the top miner leads by 6 points, from generator-style skills we had no data for (arithmetic, shipping
  tariffs, chords, arxiv topics, expense policies, wildguard). Data for these has since been built (`dataset/data/generalist/gen/`).
* Reports: `reports_all/train_50k-export.json`, `reports_all/core2.json`, `reports_all/core2+train_50k-w{0.5,0.75,1}.json`.
