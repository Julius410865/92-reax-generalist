# Generalist track: model update plan (27 Oct 2026)

Based on the live standings `https://reax.co/data/miners/eval-live.json` (generated 2026-10-27 17:27Z), the public
Hugging Face metadata of the entries, and this repo's code (`spec/v5.py`, `spec/evaluator.py`, `spec/machine.py`).
It supersedes the assumptions in PLAN.md where they differ (marked **changed**).

## 1. Findings

### 1.1 The real bar is uid 116, not uid 250
The generalist title is held by three co-champions. A challenger's gain is measured against the **best co-champion
on the same draw** (`evaluator.py:3018`). On all three v5.1 draws so far, that was uid 116:

| v5.1 draw (27 Oct) | uid 116 Andrew93110/sn92-gen-v1 | uid 199 putty77/sn92-generalist-a | uid 250 reax-knockout/sn92-gen-a1 |
|---|---:|---:|---:|
| 08:38 | **40.75** | 37.77 | 37.86 |
| 10:41 | **38.12** | 36.02 | 34.82 |
| 13:27 | **43.18** | 42.51 | 40.91 |
| mean | **40.68** | 38.77 | 37.86 |

All three co-champions are fine-tunes of `perplexity-ai/pplx-decider-v1.2`, the same lineage as `decisionmodels/reax-1.1`.
PLAN.md's "the bar = uid 250" is **changed**: uid 250 is the weakest of the three on v5.1.

The same model moves about 5 points between draws (uid 116: 38.1 to 43.2). Raw S_eff values from different draws
cannot be compared; only paired gains on the same draw count.

### 1.2 Challengers that may already be better than the champions
"Gain" is the score minus uid 116's score on the same 900-item draw (checked against the published gains). SE ≈ gain / z.

| Entry | Base | Draw 1 gain (z) | Draw 2 | Status at 17:27Z |
|---|---|---|---|---|
| uid 60 isomsom/sn92-gen-m87b@7f04058f | mammoth-1@61cec44 | **+3.96** (1.6) | running | close call, extra draw running now |
| hotkey 5D5goWB7 xflud/sn92-decider-1@db2e622a | mammoth-1@61cec44 | +2.90 (1.1) | running | close call, extra draw running now |
| uid 40 reax-coyote/reax-gen-coyote@2f64c8bd | not readable (repo not public now) | +4.23 (1.8) | +1.54 | not better (pooled too low); v2 queued |
| uid 76 edinlong83/sn92-generalist-h5@764dad66 | mammoth-1@03007ab | +2.89 (1.2) | +0.10 | not better |
| uid 144 CharlieBT/gx28-decider@0914f52c | ? | +1.57 (0.7) | – | not better |
| uid 54 voicort/sn92-generalist-v5-1@0a59cd61 | decisionmodels/reax-1 | +0.71 (0.4) | – | not better |
| uid 102 edward56/sn92-gen-v5m | ? | −2.49 | – | not better |
| uid 218 doubtsjohn/sn92-gen-r4 | ? | −2.90 | – | not better |

What the table shows:
* **The base decides most of the result.** Three of the four best v5.1 first draws are fine-tunes of `baselabs/mammoth-1`
  (Qwen3.5-27B, MIT). It ranks #1 on Jev Decision Index 0.4, the structure eval v5.1 is built on (`docs/EVAL-V5.md`).
  The only reax-1-lineage challenger gained +0.71.
* **First draws overstate the gain.** Both close calls that already had their second draw fell back:
  +4.23 to +1.54, and +2.89 to +0.10. The true lead of the best current entries over uid 116 is probably
  2–3 points, not 4.
* **Noise level:** the paired SE is about 2.4–2.6 points per 900-item draw.
* **No entry has crowned on v5.1 yet.** m87b and xflud are being re-drawn right now. If m87b passes, it waits for a
  confirmation at least 12 h after its first draw (13:27Z). It could crown at the Thu 29 Oct 14:30Z slot and become the bar.

### 1.3 What it takes to crown (rules v3 + v4, `machine.py`)
* First draw: z ≥ 2.0 and gain ≥ 1.0 passes directly. With SE ≈ 2.5, that means a gain of about **5 points**.
* Close call (1.0 ≤ z < 2.0): one more draw; pooled z ≥ 2.0 needs a mean gain of about 3.6.
* Crowning: pooled z ≥ 2.75 over all draws, including at least one confirmation 12 h or more later. With 3 draws that
  means a mean gain of about **4 points**; with 4 draws, about 3.5.
* A tie inside the noise goes to the earlier commitment.

In short, a new entry needs a **true** lead of about 4–5 points over the bar. PLAN.md's local gate of "+3 points / z 2.5"
is too low (**changed**, see 2.4).

### 1.4 Scoring detail that changes what to optimise
v5.1 gives credit only for the **top-1 answer** (`v5.question_credit`): 1 if the argmax is the gold option, 1/k for
exact ties. An item counts only if all of its questions are right.
* Scaling the readout uniformly or retuning the temperature (as uid 116 did ×3, m87b ×2.7 and reax-1.1 ×1.6) **does not
  change the score**, because the argmax stays the same. Don't spend time on it.
* What does change the score is anything that moves the argmax: the weights, and per-option biases. The main case is
  the IDK option on omniscience items, scored `(100 + correct% − incorrect%) / 2` with IDK = 0. A wrong answer costs
  points; an IDK costs nothing.

### 1.5 Recipes of the leading entries (from their model cards)
* All of them: LoRA rank 16–32 on attention, linear-attention and MLP projections, merged into bf16; the validator's
  joint readout; trained in joint (bidirectional) mode, as the validator serves it.
* m87b (the best first draw):
  * 1,500 steps × 32 rows (about 48k rows), lr 2.5e-5 with a cosine schedule.
  * Data in the eval v5.1 item format: about 50 procedural rule-engine generators with exact solvers (fees, tariffs,
    eligibility, refunds, games), public-record classification (federal registers, CVEs, recalls, EU tenders, Wikipedia
    process pages and more).
  * "I don't know" targets for facts dated after 1 Aug 2026.
  * Replay of sn92-specialists and procedural-typed-decisions rows.
* h5: similar generators plus Aegis safety rows, official-category classification and IDK rows.
* uid 116: sn92-specialists plus MMLU self-distillation anchors plus area rows (math/dates, tool use).

## 2. Update plan

### 2.1 Before anything else (now, then again before each decision)
1. Re-pull `eval-live.json` after the running draw. Record whether m87b or xflud passed, and their pooled gain.
2. Bar = the strongest of: uid 116; any entry pending confirmation; any newly crowned champion.
3. **Changed:** step 6 of the training brief compares against uid 116, `Andrew93110/sn92-gen-v1@4d2a519d78…`
   (look up the full 40-hex revision on Hugging Face), not uid 250. If m87b passes, also compare against it.

### 2.2 Phase B: base bake-off (go / no-go 1, about 1 day)
Score each candidate on `prepared/eval` (select + test) and the v5.1 dev set, all on the same machine and code:
* `decisionmodels/reax-1.1@142b193` (the current plan's base)
* `baselabs/mammoth-1@61cec44` repackaged into the joint-readout layout, as h5's MODIFICATIONS.md step 1 does:
  * `architectures: ["Qwen3_5Model"]`, tensor names `model.X` → `X`, drop `lm_head`;
  * `readout.safetensors` = LM-head rows of the 255 answer codes;
  * `decision_config.json` / `joint_config.json` as in REAX 1.1.
* uid 116 (the bar), plus m87b if it loads.

Decision:
* If repackaged mammoth-1 (untrained) already matches or beats uid 116 locally, switch the base to mammoth-1.
* Otherwise, keep reax-1.1.

Caveats:
* The trainer has only been tested with reax-1.1. Supporting mammoth-1 is a code change (a converter plus loading).
  It needs your approval and a diff before I make it.
* The validator fetches the declared base itself. `mammoth-1` is public and MIT; with the 26 Oct revision `61cec44` it
  is the same base m87b and xflud declare.
* Our weight change must not be nearly identical to theirs (cosine > 0.98 ⇒ "derived"). An independent LoRA run is
  not affected.
* Keep-alive is not available for any entry above 10 B parameters in this release (empty `KEEPALIVE_BASE_FLOOR`),
  whichever base we choose.

### 2.3 Phase C: training (staged, as in DATASET-PLAN 3c, on the chosen base)
* Stage gates as in the training brief (IMPROVED verdict, weight check, falling loss).
* The plan's data mix already matches what worked for the leaders. Priorities by points per effort:
  1. **N part (40 % of S, plain mean over task types):** rule-application generators with exact solvers, and
     record-to-official-category classification. This is where m87b and h5 put their effort.
  2. **Omniscience / IDK:** answerable old facts next to "I don't know" for post-1-Aug-2026 facts. Wrong answers cost
     points there.
  3. **Multi-question items:** an item needs every question right, so include joint multi-question rows.
* Skip readout temperature or scaling work (see 1.4).
* Select checkpoints by the v5.1 score on the select split, never by loss.

### 2.4 Phase D: local gate before a submission (**changed**)
Submit a stage only if, on the test split, against the bar from 2.1:
* paired gain ≥ **+5 points** and z ≥ 2.5 (was +3);
* no area or N type is worse than the base by more than its SE;
* dev-set gain is not much larger than test gain.

Reason: the observed shrinkage of first-draw gains, together with crowning needing pooled z 2.75 at SE ≈ 2.5 per draw.
A +3 local gain would most likely end as "not better" and use up one of the 4 weekly submissions.

### 2.5 Phase E: timing
* Slots: Thu 29 Oct, Mon 2 Nov, Thu 5 Nov, 14:30Z.
* The first draw currently comes 1–3 h after commitment (8 evaluations per hour, 13 queued). The confirmation needs
  12 h after that.
* Commit as soon as an entry clears the gate, because ties go to the earlier commitment.
* Realistic first slot: Mon 2 Nov if Phase B and stage 1 finish by Sat 31 Oct; otherwise Thu 5 Nov.

## 3. Open decisions for you
1. Base switch to mammoth-1, if Phase B supports it (code change to the trainer; needs your approval).
2. The licence filter for OpenAI- and Anthropic-authored rows (still pending from the training brief).
3. Raising the local gate from +3 to +5 points.

## 4. Limits of this analysis
* SEs are derived from gain / z with z rounded to one decimal (about ±10 %).
* The feed lists xflud under uid 114 in `entries` and uid 162 in `recent_events` (same hotkey 5D5goWB7).
* `reax-coyote/reax-gen-coyote` could not be read from Hugging Face (not public), so its base is unknown.
* Five entries are in evaluation right now, so this picture can change within hours. Re-check per 2.1.
