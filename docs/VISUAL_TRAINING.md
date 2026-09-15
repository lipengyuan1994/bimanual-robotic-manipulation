# Visual-variation training evidence

Visual variation changes lighting and floor/workbench color while retaining the
same physical dinner layout. It measures appearance robustness only; one visual
seed is not an independent physical scene.

The frozen protocol is
[`experiments/visual-training-protocol-v1.json`](experiments/visual-training-protocol-v1.json):
seeds7–10 are training inputs,1001–1002 are validation inputs, and2001–2010 are
reserved tests. Seeds0 and7 have already been used during development, so neither
can be held out. The protocol seals the current recipe-v2 scene, teacher plan,
asset manifest and visual generator. It declares `validated_recordings: false`
until real recorded sources pass the source verifier.

Verify the allocation and source bindings:

```sh
.venv/bin/bimanual visual-protocol-check \
  docs/experiments/visual-training-protocol-v1.json
```

After recording one allocated training seed, verify the sealed run before export:

```sh
.venv/bin/bimanual visual-source-check .artifacts/runs/RUN_ID \
  --protocol docs/experiments/visual-training-protocol-v1.json
```

The source check recomputes both physical scores, verifies all5,049 applied
teacher actions and5,050 observation/phase records, checks three-camera PNG
artifacts, regenerates the visual-only scene, and confirms the physical layout
and plan did not change. A successful source check still does not establish
LeRobot decoded row parity, learned-policy quality, physical-layout diversity,
or held-out generalization. Those gates belong to export, training and evaluation.

Current tests use synthetic recorded structures with explicitly mocked passing
scores to exercise integrity paths. A separate negative test sends that synthetic
trace through the real scorers and requires rejection. No synthetic fixture may
be cited as manipulation success.

## Held-out recording intake

The allocation file is **scaffolding**, not evidence that any validation or test
recording exists. Its permanent `validated_recordings: false` field prevents a
static JSON declaration from becoming a quality or generalization claim. A named,
sealed teacher source must separately pass the source-bound verifier before it can
be used as a held-out recording input:

```sh
.venv/bin/bimanual visual-held-out-source-check .artifacts/runs/RUN_ID \
  --protocol docs/experiments/visual-training-protocol-v1.json --split validation
```

Use `--split test` only for one of the frozen test seeds. The verifier requires the
source's declared seed, controller split and episode lineage to match the same
frozen allocation, regenerates the visual scene, and recomputes the teacher's
physical scores. It rejects a training seed, cross-split seed, or altered lineage.
It emits `verified_source_only`, `training_export_authorized: false`, and
`learned_evaluation_success: null`; it does not export data, run a policy, or claim
held-out generalization. Held-out recordings must be passed to a later independent
learned-policy evaluation record, never `lerobot-export` as a training source.
