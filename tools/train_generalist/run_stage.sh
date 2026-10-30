#!/usr/bin/env bash
# One stage end to end: base report (once), prepare, train, score, compare, weight check.
#   tools/train_generalist/run_stage.sh stage1
#   tools/train_generalist/run_stage.sh stage2 stage1
# Run from the repository root, inside tmux, e.g.  ... 2>&1 | tee logs/stage1.log
# Extra trainer flags: TRAIN_ARGS="--eval-every 25" tools/train_generalist/run_stage.sh stage1
# Everything up to (not including) training: PREPARE_ONLY=1 tools/train_generalist/run_stage.sh stage1
# No base / champion scoring (and so no verdict): SKIP_BASE=1
# Another evaluation set: EVAL=prepared/eval_all REPORTS=reports_all CHAMPION=/models/uid116-sn92-gen-v1 run_stage.sh all
set -euo pipefail
STAGE=${1:?usage: run_stage.sh <stage> [<previous stage>]}
PREV=${2:-}
cd "$(dirname "$0")/../.."
[ -f /venv/main/bin/activate ] && . /venv/main/bin/activate
CFG=data/generalist/stages/$STAGE.json
[ -f "$CFG" ] || CFG=data/stages/$STAGE.json
[ -f "$CFG" ] || { echo "no config for $STAGE"; exit 2; }
BASE=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['base'])" "$CFG")
PY="python -m tools.train_generalist"
# the config's run block sets eval / reports / skip_base; an environment variable of the same name still wins
RUNCFG() { python -c "import json,sys; v=(json.load(open(sys.argv[1])).get('run') or {}).get(sys.argv[2]); print('' if v is None else (int(v) if isinstance(v, bool) else v))" "$CFG" "$1"; }
EVAL=${EVAL:-$(RUNCFG eval)}
EVAL=${EVAL:-prepared/eval}
REPORTS=${REPORTS:-$(RUNCFG reports)}
REPORTS=${REPORTS:-reports}
SKIP_BASE=${SKIP_BASE:-$(RUNCFG skip_base)}
SKIP_BASE=${SKIP_BASE:-0}
t0=$(date +%s)
mkdir -p "$REPORTS" runs prepared logs
echo "== $STAGE ($CFG), base $BASE, previous ${PREV:-none}, $(date -u +%FT%TZ)"

if [ ! -f "$EVAL/test.items.jsonl.gz" ]; then
  echo "== prepare eval splits (once)"
  $PY.data --config "$CFG" --out "$EVAL" --splits select,test
fi
# the eval splits must come from this config's select / test definitions: another stage's eval dir would pick the best
# checkpoint and score the stage on the wrong items (FORCE_EVAL=1 overrides, e.g. to score on an earlier stage's splits)
WRONG=$(python - "$CFG" "$EVAL" <<'EOF'
import json, os, sys
from tools.train_generalist import data as D
cfg, ev = json.load(open(sys.argv[1])), sys.argv[2]
for split in ("select", "test"):
    p = os.path.join(ev, f"{split}.meta.json")
    got = json.load(open(p)).get("digest") if os.path.exists(p) else None
    if got != D.config_digest(cfg, split):
        print(f"{split}: {ev} was prepared from other {split} definitions ({got}) than {sys.argv[1]} ({D.config_digest(cfg, split)})")
EOF
)
if [ -n "$WRONG" ] && [ "${FORCE_EVAL:-0}" != "1" ]; then
  echo "$WRONG"; echo "set EVAL (or the config's run.eval) to this stage's eval dir, or FORCE_EVAL=1"; exit 5
fi
echo "== settings: eval $EVAL, reports $REPORTS, skip_base $SKIP_BASE, extra trainer flags '${TRAIN_ARGS:-}'"
if [ "${SKIP_BASE:-0}" != "1" ] && [ ! -f "$REPORTS/base.json" ]; then
  echo "== base report (once)"
  $PY.stage_check eval --base "$BASE" --prepared "$EVAL" --label base --out "$REPORTS/base.json"
fi
if [ "${SKIP_BASE:-0}" != "1" ] && [ -n "${CHAMPION:-}" ] && [ ! -f "$REPORTS/champion.json" ]; then
  echo "== champion report (once): $CHAMPION"
  $PY.stage_check eval --base "$CHAMPION" --prepared "$EVAL" --label champion --out "$REPORTS/champion.json"
fi

if [ -e "runs/$STAGE" ]; then
  echo "runs/$STAGE exists (an earlier run): move it away first, a new run must not append to its log"; exit 3
fi
if [ -n "$PREV" ]; then
  # the next stage only builds on a stage that passed (its compare verdict); to start a later stage from the base, omit <previous stage>
  PV=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['verdict'])" "$REPORTS/$PREV.compare.json" 2>/dev/null || echo "no compare report")
  if [ "$PV" != "IMPROVED" ] && [ "${FORCE_CONTINUE:-0}" != "1" ]; then
    echo "$PREV did not pass (verdict: $PV): not continuing from it (FORCE_CONTINUE=1 overrides)"; exit 4
  fi
fi

echo "== prepare $STAGE"
$PY.data --config "$CFG" --out "prepared/$STAGE" --splits train

KL=$(python -c "import json,sys; print(float((json.load(open(sys.argv[1])).get('train') or {}).get('kl_to_base', 0)))" "$CFG")
KLF=$(python -c "import json,sys; print(float((json.load(open(sys.argv[1])).get('train') or {}).get('kl_fraction', 1)))" "$CFG")
if python -c "import sys; sys.exit(0 if float(sys.argv[1]) > 0 else 1)" "$KL"; then
  WHY=$(python -c "from tools.train_generalist import teacher as T; import sys; print(T.check(sys.argv[1], sys.argv[2], float(sys.argv[3])) or '')" "$BASE" "prepared/$STAGE" "$KLF")
  if [ -n "$WHY" ]; then
    echo "== base answers for KL-to-base ($KL, on a fraction $KLF of the rows): $WHY"
    $PY.teacher --base "$BASE" --prepared "prepared/$STAGE" --fraction "$KLF"
  else
    echo "== base answers for KL-to-base ($KL): up to date"
  fi
fi

INIT=()
PREV_BEST=""
if [ -n "$PREV" ]; then
  PREV_BEST=$(python -c "import json; print(json.load(open('runs/$PREV/best.json'))['path'])")
  INIT=(--init-adapter "$PREV_BEST")
  echo "== continue from $PREV_BEST"
fi

if [ "${PREPARE_ONLY:-0}" = "1" ]; then
  echo "== PREPARE_ONLY: $STAGE is ready; training not started"
  echo "   train with: tools/train_generalist/run_stage.sh $STAGE ${PREV}"
  exit 0
fi

echo "== train $STAGE"
$PY.train --config "$CFG" --prepared "prepared/$STAGE" --eval "$EVAL" --out "runs/$STAGE" "${INIT[@]}" ${TRAIN_ARGS:-}
BEST=$(python -c "import json; print(json.load(open('runs/$STAGE/best.json'))['path'])")
python -c "import json; b=json.load(open('runs/$STAGE/best.json')); print('best checkpoint:', b['path'], 'step', b['step'], 'select', b.get('select'))"

echo "== score $STAGE"
$PY.stage_check eval --base "$BASE" --adapter "$BEST" --prepared "$EVAL" --label "$STAGE" --out "$REPORTS/$STAGE.json"

if [ "${SKIP_BASE:-0}" = "1" ] && [ ! -f "$REPORTS/${PREV:-base}.json" ]; then
  echo "== compare skipped (SKIP_BASE=1: no $REPORTS/${PREV:-base}.json to compare with)"
else
echo "== compare"
EARLIER=$(REPORTS="$REPORTS" python - "$STAGE" "$PREV" <<'EOF'
import os, sys
stage, prev = sys.argv[1], sys.argv[2]
done = sorted(f[:-5] for f in os.listdir(os.environ.get("REPORTS", "reports")) if f.startswith("stage") and f.endswith(".json") and ".compare" not in f)
print(",".join(s for s in done if s not in (stage, prev)))
EOF
)
$PY.stage_check compare --stage "$STAGE" --prev "${PREV:-base}" --earlier "$EARLIER" --config "$CFG" --reports "$REPORTS" --prepared "$EVAL"
fi

echo "== weight check"
if [ -n "$PREV_BEST" ]; then
  $PY.stage_check weights --adapter "$BEST" --prev-adapter "$PREV_BEST" || true
else
  $PY.stage_check weights --adapter "$BEST" || true
fi
echo "== loss (first / last steps of runs/$STAGE/log.jsonl)"
python - "$STAGE" <<'EOF'
import json, sys
s = [json.loads(l) for l in open(f"runs/{sys.argv[1]}/log.jsonl") if '"loss"' in l]
if s:
    for key in ("loss", "ce", "kl"):
        v = [r[key] for r in s if r.get(key) is not None]
        if len(v) >= 2:
            k = min(10, len(v) // 2)          # disjoint windows, also for short runs
            a, b = sum(v[:k]) / k, sum(v[-k:]) / k
            print(f"{key}: steps {len(v)}: first-{k} mean {a:.4f}, last-{k} mean {b:.4f} ({'down' if b < a else 'NOT down'})")
    print(f"median tok/s {sorted(r['tok_s'] for r in s)[len(s)//2]:.0f}")
EOF
echo "== $STAGE done in $(( ($(date +%s) - t0) / 60 )) min"
