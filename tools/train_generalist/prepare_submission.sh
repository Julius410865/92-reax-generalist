#!/usr/bin/env bash
# Build the submission directory of a trained stage, check it as the validator does and score it through JointRunner.
#   tools/train_generalist/prepare_submission.sh train_50k <hotkey ss58>
# A stage trained on another base (e.g. a merge): set the variables below, e.g. for train_42k on /models/merge-w05
#   BASE=/models/merge-w05 EVAL=prepared/eval_42k REPORTS=reports_42k ADAPTER_REPORT=reports_42k/train_42k-ckpt350.json \
#   LINEAGE=submit/licence/NOTICE-lineage-merge.txt COMPARE="reports_all/core2.json reports_all/core2+train_50k-w0.5.json" \
#   SKETCHES=reports_42k/sketch/sketch_core2.npz SKETCH_SEED=reports_42k/sketch/sketch_seed.bin \
#   DATA_MANIFESTS="dataset/n_records/manifest.json dataset/n_records_extra/manifest.json dataset/openai_anthropic/manifest.json dataset/train_42k/sources.json" \
#   tools/train_generalist/prepare_submission.sh train_42k <hotkey ss58>
# EXPORT_ONLY=1: the merge and the CPU checks only (no GPU: no serve check, no scoring, no comparison).
# Nothing is uploaded or committed: the script ends by printing those commands for you to run.
set -euo pipefail
STAGE=${1:?usage: prepare_submission.sh <stage> <hotkey ss58>}
HOTKEY=${2:?usage: prepare_submission.sh <stage> <hotkey ss58>}
cd "$(dirname "$0")/../.."
[ -f /venv/main/bin/activate ] && . /venv/main/bin/activate
BASE=${BASE:-/models/mammoth-1}                      # the weights the adapter was trained on (merged into)
BASE_ID=${BASE_ID:-baselabs/mammoth-1@61cec44c281c693992e3d6ebeb44dd3402dfa186}   # the declared base
DECLARED_BASE=${DECLARED_BASE:-/models/mammoth-1}    # local copy of the declared base (weight copy check)
LIC=submit/licence
LINEAGE=${LINEAGE:-$LIC/NOTICE-lineage.txt}
OUT=submit/$STAGE
EVAL=${EVAL:-prepared/eval_all}
REPORTS=${REPORTS:-reports_all}
DATA_MANIFESTS=${DATA_MANIFESTS:-dataset/n_records/manifest.json dataset/openai_anthropic/manifest.json}
ADAPTER_REPORT=${ADAPTER_REPORT:-$REPORTS/$STAGE.json}   # adapter scoring of the same checkpoint (the export must match it)
COMPARE=${COMPARE:-$REPORTS/core2.json}              # other reports, compared on the test items both were scored on
SKETCHES=${SKETCHES:-}                               # saved delta sketches of earlier submissions (copy check) ...
SKETCH_SEED=${SKETCH_SEED:-}                         # ... and the seed they were sampled with
PY="python -m tools.train_generalist"
ADAPTER=${ADAPTER:-$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['path'])" "runs/$STAGE/best.json")}
t0=$(date +%s)

free_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }
FLOOR=${DISK_FLOOR_GB:-40}                           # free disk to keep after the export (0: only the export must fit)
NEED=$(( $(du -s -BG "$BASE" | cut -f1 | tr -dc 0-9) + FLOOR ))
echo "== disk: $(free_gb) GB free, need $NEED GB (the export + the $FLOOR GB floor)"
[ "$(free_gb)" -ge "$NEED" ] || { echo "not enough free disk: stopping"; exit 2; }
[ -e "$OUT" ] && { echo "$OUT exists: move it away first"; exit 3; }

echo "== export $ADAPTER -> $OUT (hotkey $HOTKEY, base $BASE_ID)"
MANIFEST_ARGS=()
for m in $DATA_MANIFESTS; do MANIFEST_ARGS+=(--data-manifest "$m"); done
$PY.export --base "$BASE" --adapter "$ADAPTER" --out "$OUT" --hotkey "$HOTKEY" --base-id "$BASE_ID" \
  --licence mit --licence-file "$LIC/LICENSE" "${MANIFEST_ARGS[@]}" $([ "${EXPORT_ONLY:-0}" = "1" ] || echo --serve-check)
cp "$LIC/LICENSE-APACHE-2.0" "$OUT/"
[ -f "$BASE/THIRD_PARTY_NOTICES.md" ] && cp "$BASE/THIRD_PARTY_NOTICES.md" "$OUT/"
# a base with its own LICENSE (a merge of other entries) is shipped with that file: add our copyright line to it
OWN=$(grep -m1 '^Copyright' "$LIC/LICENSE")
grep -qF "$OWN" "$OUT/LICENSE" || python - "$OUT/LICENSE" "$OWN" <<'EOF'
import sys
path, line = sys.argv[1:]
text = open(path, encoding="utf-8").read().split("\n")
last = max(i for i, l in enumerate(text) if l.startswith("Copyright"))
open(path, "w", encoding="utf-8").write("\n".join(text[:last + 1] + [line] + text[last + 1:]))
EOF
grep -n '^Copyright' "$OUT/LICENSE"
{ echo; cat "$LINEAGE"; } >> "$OUT/NOTICE"

echo "== final directory: validator rules and merge check"
python - "$OUT" "$HOTKEY" "$BASE" "$ADAPTER" <<'EOF'
import sys
from tools.train_generalist import export as E
out, hotkey, base, adapter = sys.argv[1:]
v = E.validator_check(out, hotkey) + E.check_merged(out, base, adapter)
print("VALIDATOR RULES + MERGE: " + ("OK" if not v else "PROBLEMS\n  " + "\n  ".join(v)))
sys.exit(1 if v else 0)
EOF

if [ -n "$SKETCHES" ]; then
echo "== weight copy check vs earlier submissions (validator's delta sketch; derived = cosine > 0.98 and relative L2 < 0.05)"
python - "$OUT" "$DECLARED_BASE" "$SKETCH_SEED" $SKETCHES <<'EOF'
import sys
from reax_subnet.spec import tensors as T
out, base, seed_path, *sketches = sys.argv[1:]
sk = T.delta_sketch_ex(out, base, seed=open(seed_path, "rb").read())
print(f"  review flags: {list(sk.review) or 'none'}{T.coverage_note(T.sketch_coverage(sk.deltas, out, base))}")
derived = 0
for p in sketches:
    s = T.compare_sketches(T.load_sketch(p), sk.deltas)
    print(f"  vs {p}: cosine {s.cosine:.4f}, relative L2 {s.relative_l2:.4f}, alpha {s.alpha:.4f} -> "
          + ("DERIVED" if s.derived() else "not derived"))
    derived += s.derived()
sys.exit(1 if derived else 0)
EOF
fi

if [ "${EXPORT_ONLY:-0}" != "1" ]; then
echo "== score $OUT with the validator's JointRunner"
$PY.stage_check eval --base "$OUT" --prepared "$EVAL" --label "$STAGE-export" --out "$REPORTS/$STAGE-export.json"

echo "== paired test-split comparison"
python - "$REPORTS" "$STAGE" "$EVAL" "$ADAPTER_REPORT" $COMPARE <<'EOF'
import gzip, json, os, sys
from tools.train_generalist import scoring as SC
reports, stage, ev, adapter_report, *others = sys.argv[1:]
items = [json.loads(l) for l in gzip.open(os.path.join(ev, "test.items.jsonl.gz"), "rt")]
mine = json.load(open(os.path.join(reports, f"{stage}-export.json")))["splits"]["test"]["responses"]
for p in [adapter_report] + others:
    if not os.path.exists(p):
        continue
    r = json.load(open(p))
    label = "adapter scoring of the same checkpoint" if p == adapter_report else r["label"]
    theirs = r["splits"]["test"]["responses"]
    shared = [it for it in items if it["id"] in theirs]     # a report of another eval dir: the items both were scored on
    d = SC.paired(shared, mine, theirs)
    print(f"export minus {label}: changed items {d['changed_items']} of {d['items']}")
    for k, e in [("local", d["local"]), ("dev_v51", d["dev_v51"])] + sorted(d["sources"].items()):
        if e["gain"] is not None:
            print(f"  {k:18s} export {e['a']:6.2f}  other {e['b']:6.2f}  gain {e['gain']:+6.2f} (se {e['se']:.2f}, n {e['items']})")
EOF
fi

echo "== ready: $OUT ($(du -sh "$OUT" | cut -f1)), $(free_gb) GB free, $(( ($(date +%s) - t0) / 60 )) min"
echo "Nothing was uploaded or committed. When you decide to submit, run these yourself:"
echo "  hf upload-large-folder <hf user>/<repo name> $OUT --repo-type model --private"
echo "  python -c \"from huggingface_hub import HfApi; print(HfApi().model_info('<hf user>/<repo name>').sha)\""
echo "  reax-commit --wallet-name <wallet> --wallet-hotkey <hotkey name> set \"reax-spec/1:generalist:<hf user>/<repo name>@<40-hex sha>\" --dry-run"
echo "  reax-commit --wallet-name <wallet> --wallet-hotkey <hotkey name> set \"reax-spec/1:generalist:<hf user>/<repo name>@<40-hex sha>\""
echo "  reax-commit --wallet-name <wallet> --wallet-hotkey <hotkey name> show"
echo "The repo may stay private at commit time; it must be public before the publish deadline."
