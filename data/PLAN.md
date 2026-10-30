# Generalist track: execution plan (from 26 Oct 2026)

Target: take rank 1 on the SN92 generalist track under eval v5.1 with a fine-tuned 27 B decision model.
Data plan: `DATASET-PLAN.md` (same folder).

## Facts this plan rests on

* Score = 0.6 T + 0.4 N (eval v5.1, panel-scaled). Live items are private, fresh, from other sources than the dev set.
* To win: paired gain over the champion of max(1.0, 2 SE) on a ~900-item draw (effective 2-5 points so far), then at
  least half that again on a disjoint draw >= 12 h later; crowned at the next Mon / Thu 14:30 UTC slot; owner approval.
* Co-champions (v4 scores): uid 250 reax-knockout/sn92-gen-a1 76.83, uid 116 75.23, uid 199 74.99. No challenger has
  confirmed since the opening. Nobody has a v5.1 score yet.
* Limits: one commitment per hotkey; per coldkey at most 2 open submissions on the track and 4 new per 7 days; the HF repo
  must be public within 24 h of the commitment; >10 B entries get keep-alive only if their base is in the owner's table.
* Live standings: https://reax.co/data/miners/eval-live.json (every ~2 min).

## Phase 0 - Set-up (day 1)

1. Hardware: one 96 GB (RTX PRO 6000) or 80 GB (H100) GPU, Docker-capable VM, >= 500 GB fast disk. Two GPUs halve the
   training time and allow train + evaluate in parallel.
2. `pip install -e '.[spec]'` in reax-subnet; download the SN92 dataset and the v5.1 dev set.
3. Confirm the local scorer reproduces the validator path: run `reax-spec-eval` and `tools/score_v5.py` on one known
   entry and check its numbers are plausible against the live S_eff.
4. Hotkey: uid 128 (rabi-h1) is offline with zero weight and past immunity, so it can be deregistered at any time.
   Either bring its miner back up first, or register a fresh hotkey for the entry (one registration burn).

## Phase 1 - Base selection (day 1-2), go / no-go 1

1. Score without training, paired, on the v5.1 dev set plus a first private validation suite (DATASET-PLAN section 5):
   * decisionmodels/reax-1.1@142b19355af0 (candidate base)
   * baselabs/mammoth-1@61cec44c281c (candidate base)
   * uid 250 reax-knockout/sn92-gen-a1@d57f18b9 (the bar)
2. Pick the base with the best v5.1 score. If a raw base already matches or beats uid 250 on v5.1, the champions are weak on
   v5.1 and a quick, light fine-tune is worth submitting early (see Phase 4 fast lane).

## Phase 2 - Data (days 2-5)

Build in the order of DATASET-PLAN section 7: exact-gold generators -> retrieval / intent sets -> language / safety / IDK ->
extra N domains. Every set gets train / select / test splits by seed or source record. Validation sources stay disjoint from
training sources. Target ~115 k training rows.

## Phase 3 - Training (days 4-8)

1. LoRA through the base's own readout (decider-style bases ship `readout.safetensors`, `joint_config.json`,
   `decision_config.json`; train against that readout, as the leaders did), bf16 base, gradient checkpointing.
   Start: rank 32, lr 5e-5 -> 2e-5, cosine, one epoch, label smoothing 0.05, anchors in every batch.
2. Two or three runs that differ in data mix only (e.g. N-heavy vs balanced, with vs without translations).
3. Select checkpoints on the select split by the **v5.1 score**, not by loss.
4. Merge LoRA in fp32, store bf16; keep tokenizer / config / readout files of the base unchanged unless a change is
   deliberate (e.g. readout temperature); write `reax-specialist.json` (schema, category generalist, hotkey, base_model
   with revision, licence) and LICENSE.

## Phase 4 - Pre-submission gate (1 day per candidate), go / no-go 2

Submit only if all hold on the **test** split (used once per candidate):
* paired gain over uid 250 >= 3 points and z >= 2.5, and over the base clearly positive in every area;
* no area or N type worse than the base by more than its SE;
* dev-set gain not much larger than private-test gain (own gap check);
* files pass the static rules (safetensors only, allowed architecture, no auto_map, size <= 36 B / 68 GiB).

Fast lane: if Phase 1 showed the champions weak on v5.1, a first light fine-tune that clears the gate can go in early to
catch the Thu 29 Oct or Mon 2 Nov slot.

## Phase 5 - Submit and follow (1-2 days per attempt)

1. Push the model repo (private is fine), commit `reax-spec/1:generalist:<repo>@<40-hex>` with `reax-commit set`, make the
   repo public within 24 h.
2. Watch eval-live.json: first draw (gain, margin, z), close call / extra draw, confirmation >= 12 h later, slot.
3. Expected path: first draw within hours (queue-dependent), confirmation +12 h, crown at the next Mon / Thu 14:30.
4. Fail -> read the per-area result of the draw if shown, return to Phase 3 with a changed mix. At most 4 new submissions
   per coldkey per 7 days: don't burn them on near-identical candidates.

## Timeline

| Day (2026) | Milestone |
|---|---|
| Mon 26 Oct - Tue 27 | Phase 0-1: set-up, base selection on v5.1 |
| Wed 28 - Fri 30 | Phase 2 data, first training run |
| Sat 31 - Mon 2 Nov | runs 2-3, selection, gate; fast-lane submission possible for Mon 2 Nov |
| Tue 3 - Thu 5 Nov | main submission, first draw + confirmation, **target slot Thu 5 Nov 14:30** |
| after | iterate weekly within the 4-per-week limit |

## Budget (rough)

* GPU: ~80-150 GPU-hours on one 80-96 GB card (base scoring ~10 h, 3 training runs ~15-25 h each, evaluations ~20 h);
  at $1.4-2.5 / h about $120-370.
* Registration: one burn if a new hotkey is needed.
* People: one engineer comfortable with LoRA on 27 B models and data pipelines; the generators are the bulk of the work.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| v5.1 draws noisy, margin 2-5 points | gate at +3 points / z 2.5 on a large private test set; don't submit marginal gains |
| champions improve or new entrants win first | Phase 1 tells early whether v5.1 reshuffles the field; fast lane |
| gap check / overlap rule | disjoint training vs validation sources; never train on dev items; record sources |
| catastrophic forgetting of general ability | anchors in every batch; per-area checks vs the base |
| servability (validator serves the pinned revision in its own vLLM with a fixed prompt) | keep the base's architecture and files; test with the validator's own tools before committing |
| uid 128 deregistered | restore its miner or use a fresh hotkey before committing |
