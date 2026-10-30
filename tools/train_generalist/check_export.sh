#!/usr/bin/env bash
# Check an exported submission as the validator serves it: the JointRunner serve check, scoring on the prepared eval
# items, and a paired comparison with the adapter scoring of the same checkpoint (the export must answer like it).
#   tools/train_generalist/check_export.sh submit/t2fix prepared/eval_t2fix reports_t2fix/t2fix.json [max items per split]
# Needs the GPU. Writes <reports dir>/<export name>-export.json; nothing is uploaded or committed.
set -euo pipefail
OUT=${1:?usage: check_export.sh <export dir> <eval dir> <adapter report> [max items per split]}
EVAL=${2:?usage: check_export.sh <export dir> <eval dir> <adapter report> [max items per split]}
ADAPTER_REPORT=${3:?usage: check_export.sh <export dir> <eval dir> <adapter report> [max items per split]}
MAX=${4:-}                                           # empty: every item (as the adapter was scored)
cd "$(dirname "$0")/../.."
[ -f /venv/main/bin/activate ] && . /venv/main/bin/activate
LABEL=$(basename "$OUT")-export
REPORT=$(dirname "$ADAPTER_REPORT")/$LABEL.json
t0=$(date +%s)

echo "== serve check: $OUT with the validator's JointRunner"
python - "$OUT" <<'EOF'
import sys
from tools.train_generalist import export as E
v = E.serve_check(sys.argv[1])
print("SERVE CHECK: " + ("OK" if not v else "PROBLEMS\n  " + "\n  ".join(v)))
sys.exit(1 if v else 0)
EOF

echo "== score $OUT on $EVAL${MAX:+ (first $MAX items per split)}"
python -m tools.train_generalist.stage_check eval --base "$OUT" --prepared "$EVAL" --label "$LABEL" --out "$REPORT" \
  ${MAX:+--max-items "$MAX"}

echo "== export minus the adapter scoring ($ADAPTER_REPORT), on the items both were scored on"
python - "$EVAL" "$REPORT" "$ADAPTER_REPORT" <<'EOF'
import gzip, json, os, sys
from tools.train_generalist import scoring as SC
ev, mine_p, theirs_p = sys.argv[1:]
mine_r, theirs_r = json.load(open(mine_p)), json.load(open(theirs_p))
for split in ("test", "select"):
    mine, theirs = mine_r["splits"][split]["responses"], theirs_r["splits"][split]["responses"]
    items = [it for it in map(json.loads, gzip.open(os.path.join(ev, f"{split}.items.jsonl.gz"), "rt"))
             if it["id"] in mine and it["id"] in theirs]
    d = SC.paired(items, mine, theirs)
    print(f"{split}: changed items {d['changed_items']} of {d['items']}")
    for k, e in [("local", d["local"]), ("dev_v51", d["dev_v51"])]:
        if e["gain"] is not None:
            print(f"  {k:8s} export {e['a']:6.2f}  adapter {e['b']:6.2f}  gain {e['gain']:+6.2f} (se {e['se']:.2f}, n {e['items']})")
EOF
echo "== done in $(( ($(date +%s) - t0) / 60 )) min; nothing uploaded or committed"
