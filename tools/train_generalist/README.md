# tools/train_generalist: staged LoRA training for the SN92 generalist track

Trains a LoRA on a joint-readout decision model (`Qwen3_5Model` backbone + `readout.safetensors`, e.g.
`decisionmodels/reax-1.1`) through the validator's own serving path, scores every stage on a fixed held-out test split, and
exports a merged submission directory that passes the validator's submission rules. Nothing here uploads or commits.

Plan: `data/DATASET-PLAN.md` section 3c. Stage configs: `data/stages/stage*.json` (`run_stage.sh` also looks in
`data/generalist/stages/`).

## Set-up

```bash
. /venv/main/bin/activate
pip install -e '.[model,spec,test]' peft 'flash-linear-attention==0.5.2' 'einops==0.8.2'
hf download decisionmodels/reax-1.1 --revision 142b19355af00251f08db3d287307dd8b711c133 --local-dir /models/reax-1.1
REAX_TOKENIZER=/models/reax-1.1/tokenizer.json python -m pytest -q tests/test_train_generalist.py
```

Tested with torch 2.14.1+cu130, transformers 5.18.0, peft 0.21.2 on an RTX PRO 6000 Blackwell (96 GB).
Dataset: `decisionmodels/sn92-generalist-train-v1` at revision `2241ec2c5e98…` in `data/generalist/hf/sn92-generalist-train-v1/`;
`SOURCE.json` there holds the sha256 of every shard (all equal to the Hub's LFS hashes when fetched).

## Commands

```bash
python -m tools.train_generalist.data --config data/stages/stage1.json --out prepared/eval --splits select,test   # once
PREPARE_ONLY=1 tools/train_generalist/run_stage.sh stage1   # everything up to (not including) training
tools/train_generalist/run_stage.sh stage1            # base report (once), prepare, base answers (KL), train, score, compare, weight check
tools/train_generalist/run_stage.sh stage2 stage1     # continue stage1's best checkpoint: only if stage1's verdict is IMPROVED
tools/train_generalist/run_stage.sh stage2            # a later stage from the base (e.g. after a TRANSFER LOSS)
TRAIN_ARGS="--keep-all" tools/train_generalist/run_stage.sh stage1   # keep every checkpoint (default: best + latest)
python -m tools.train_generalist.stage_check eval --base <champion dir> --prepared prepared/eval --label champion \
    --out reports/champion.json                       # once; afterwards compare prints a submit line
python -m tools.train_generalist.export --base /models/reax-1.1 --adapter runs/<stage>/ckpt-N --out submit/<stage> \
    --hotkey <ss58> --base-id decisionmodels/reax-1.1@142b19355af00251f08db3d287307dd8b711c133
python -m tools.train_generalist.stage_check weights --adapter runs/<stage>/ckpt-N --merged submit/<stage> --base /models/reax-1.1
```

## Other bases (`convert.py`)

A causal Qwen3.5 checkpoint (`Qwen3_5ForConditionalGeneration`, e.g. `baselabs/mammoth-1`) is repackaged into the joint
layout without changing any weight value: tensor names `model.X` -> `X`, `lm_head` dropped, `readout.safetensors` = the
`lm_head` rows of the 255 answer codes (A..Z, then the two-letter codes that are single tokens: the same list and ids as
reax-1.1), `decision_config.json` / `joint_config.json` added, `architectures: ["Qwen3_5Model"]`. The result must pass
`spec/joint.detect`. `--delete-src` removes each source shard once converted (disk).

```bash
hf download baselabs/mammoth-1 --revision 61cec44c281c693992e3d6ebeb44dd3402dfa186 --local-dir /models/mammoth-1-hf
python -m tools.train_generalist.convert --src /models/mammoth-1-hf --out /models/mammoth-1 --delete-src \
    --base-id baselabs/mammoth-1@61cec44c281c693992e3d6ebeb44dd3402dfa186
```

Token ids belong to one tokenizer: reax-1.1 and mammoth-1 share the vocabulary but not the pre-tokenizer (mammoth-1 also
groups combining marks). The prepared eval split therefore stores items, and every model's rows are rendered with its own
tokenizer when it is scored; prepared training rows record their tokenizer (`train.meta.json`) and `train.py` refuses
rows made with another base's tokenizer.

## Same path as the validator

| Step | Validator code | Here |
|---|---|---|
| one prompt per question, shared state repeated, IDK as an extra last option | `spec/v5wire.flatten` | called |
| at most 26 options per question (gold + 25 sampled distractors) | `spec/v5wire.cap_item` | called (eval: seed 0; train: per row) |
| prompt text | `spec/prompt.render` | called |
| chat template `qwen.jinja`, thinking off, Rust tokenizer only | `spec/joint.JointRunner.load` / `decide` | same calls (`common.load_tokenizer`, `render_ids`) |
| bidirectional full attention, linear-attention layers unchanged | `spec/joint.enable_full_attention` | called |
| readout: last prompt position x `readout.safetensors`, softmax at T = 2 | `JointRunner.decide` | `common.decide` (test: equal to `JointRunner.decide`); `stage_check eval` on a model directory runs `JointRunner` itself |
| item right only if every question is right, ties 1/k, chance-corrected type scores | `spec/v5.item_table`, `type_scores`, `aggregate_areas` | called |
| submission rules (files, sizes, architecture, joint readout, manifest) | `spec/fetch.inspect_dir` | `export` runs it on its output |

## Data

* `s1` rows are converted to eval-v5.1 items: `choice` options re-keyed A.. in their order, `score` levels re-keyed A.. in
  level order (never shuffled), `noul` -> yes/no with `yes` first (as v5.1 renders yes/no).
* Held-out split: sha256 of the row's group (`ancestry.split_key`, else `cf_pair`, else `root`) against `s1_holdout`,
  before any filter, so a filter never moves a row between train and held-out.
* At most 20 scored rows per held-out group (`data.EVAL_GROUP_CAP`): `split_key` groups are whole templates, the largest
  hold over 1,000 rows, and one of them would otherwise be 59 % of the select split. The rest of such a group stays unused.
* `take` slices a second hash order of the filtered training rows; `weight` < 1 keeps that fraction of the slice (replay).
* `augment`: options of `choice` questions are shuffled (gold position balance); yes/no and score levels keep their order.
* Training never reads `data/generalist/heldout/` (refused in code). The dev set (`eval-v5/devset-v1`) may be trained on
  since 29 Oct; a stage that trains on it no longer has `dev` as a clean check.
* `exclude_author_family` applies to every entry it is set on; set it the same way in every stage and in `select` / `test`
  before `prepared/eval` is built. A changed test split is detected (`compare` refuses reports scored on another one).

## Training

LoRA (default rank 32, alpha 64, dropout 0.05) on `q/k/v/o_proj`, `in_proj_qkv`, `in_proj_z`, `out_proj`,
`gate/up/down_proj` of the language model (217.6 M parameters on reax-1.1); vision tower and readout frozen. One question
per sequence, no padding or packing, gradients accumulated to `--batch-tokens` (16,384) per optimizer step, AdamW, linear
warm-up (5 %) and cosine decay from `--lr` 5e-5 to `--lr-min` 2e-5, label smoothing 0.05, gradient clipping 1.0, gradient
checkpointing. A continued stage loads the previous best adapter with a fresh optimizer and schedule.
Every `--eval-every` steps the adapter is saved (`ckpt-<step>`) and scored on the select split; `best.json` holds the best
by `local`. `log.jsonl`: one line per step (loss, lr, tokens, tok/s, peak memory) and per eval.

## Scores (`scoring.py`)

* Each source of the test split is scored on its own: `hf` (held-out HF rows) = item-weighted mean of its 10 category
  type scores;
  `dev` (the 300 public v5.1 items; a clean check only when the stage does not train on them) = v5.1 aggregation, S = 0.6 T + 0.4 N, **unscaled** (no panel
  statistics locally, so the number is not on the live S_v5.1 scale, but differences between models are comparable).
* `local` = mean over sources: the headline of every comparison.
* SE: paired bootstrap (1,000 draws) resampling whole held-out groups inside each task type.

## KL to the base (`teacher.py`)

With `train.kl_to_base` > 0 in the stage config (0.5 in stages 1-3) the loss is cross-entropy + `kl_to_base` x
KL(p_base || p_model), towards the **declared base's** own answer distribution on each training row (also in continued
stages: never towards the previous stage). `teacher.py` computes those answers once per prepared stage (inference only;
`run_stage.sh` runs it when missing or stale) and `train.py` refuses to train without a matching file. `log.jsonl` logs
`ce` and `kl` per step.

## Verdicts (`stage_check compare`, test split, vs the previous stage)

The stage config's `checks` name the `learn` sources (what the stage trains towards: `hf` in stages 1-2, `gen` in stage 3)
and the `transfer` sources (v5.1-format items it must not lose: `dev`, and `gen` while it is not trained on). `transfer`
(the score) pools every v5.1-format item of the split.

| Verdict | When |
|---|---|
| NOT UPDATED | no test item changed its result |
| TRANSFER LOSS | a transfer source's paired gain is below 0 |
| REGRESSION | a task type with >= 40 items, or a non-transfer source, is more than 2 points and 2 SE below the previous stage |
| NO GAIN | a learn source's gain is <= 0 or <= 2 SE |
| IMPROVED | otherwise |

`run_stage.sh <stage> <previous>` refuses to continue from a previous stage whose verdict is not IMPROVED
(`FORCE_CONTINUE=1` overrides); a later stage can always start from the base instead.

Submit line (needs `reports/champion.json`): CANDIDATE only if the verdict is IMPROVED, the `transfer` gain over the
champion is at least max(`--min-gain` (1.0), 2 SE), and no s1 source is behind the champion by more than 2 SE.
The local bar is not the live bar: live crowning needs pooled z >= 2.75 over at least two 900-item draws.
