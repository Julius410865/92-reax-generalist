# t2: the complete training data

Train only on the `MIX-*` files. They hold everything the next run needs: t2's own rows plus the slices taken from t/,
gen/ and hf/. No other folder is read.

| File | What it is | Rows |
|---|---|---|
| `MIX-train.jsonl` | training rows, all 20 T types and 18 N types, balanced to the v5.1 score weights | 60,190 (66,709 questions) |
| `MIX-hf_s1.jsonl` | 30% of the operator's hf core tier (s1 format) | 10,550 |
| `MIX-select.jsonl` | held-out set for choosing the checkpoint | 5,750 |
| `MIX-test.jsonl` | held-out set for the final measurement | 5,750 |
| `MIX-check.jsonl` | t/ and gen/ held-out rows, a second check (never trained on) | 5,700 |
| `MIX-stage.json` | trainer config that reads only these files | |
| `MIX-MANIFEST.json` | targets, counts per type and source folder, licences, sha256 of every input and output | |

The other `<task>.{train,select,test}.jsonl` files are the per-type builder outputs that the mix is made from. Don't
glob `*.train.jsonl` into a run as well, or rows will be trained twice.

Rebuild and check: `python -I tools/records/build_t2_mix.py --check --tokenizer <tokenizer.json>`. The design is in
`../T2-MIX-DESIGN.md`.
