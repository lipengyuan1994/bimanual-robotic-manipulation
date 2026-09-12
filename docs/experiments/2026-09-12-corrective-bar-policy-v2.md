# Corrective bar-policy v2 training and physical evaluation

## Scope

This record covers the corrective `bar_place_and_return` ACT training attempt and
its one frozen, teacher-prepared physical evaluation. It is local native ARM64/MPS
evidence only. It does not establish a learned component pass, a complete dinner
workflow, generalization, release qualification, or Intel compliance.

## Inputs and training result

- **Cohort:** [`six-skill-corrective-training-protocol-v2.json`](six-skill-corrective-training-protocol-v2.json),
  seal `08f59ef6a7a5f4524d0b0958ee19318270c304e238ef65a4a5ad1ce2c83257e1`.
- **Inputs:** nominal dinner-v2 dataset plus the sealed six-skill corrective archive,
  whose archive manifest is `588e701aa3cd8e7e6101d6c227b9a98ecd915643f5851152bc7efd6d27a00668`.
- **Wrapper:** `20260912T125007-553bada5f697`, completed, seal
  `87610e554db7ebe8c1fabd57dd712282b66fdad67b9095cc98de744f559c97a8`.
- **Training child:** `20260912T125007-0c5aaacaefba`, completed 20,000 updates on
  `mps` with CPU fallback disabled, seal
  `3db021d565409041e40fb32f10c78223f184c24d3bd4b1960854b9093c82e969`.
- **Checkpoint:** `728012239ea6b6aed78697ac410f5419e20a540bdf5a0d76324ba88b9696582c`.

The strengthened cohort checker independently reverified the native ARM64 runtime,
the nominal dataset, selected skill views, and the corrective archive binding after
training. This verifies training provenance and completion, not physical quality.

## Physical evaluation

The first frozen evaluator declaration,
[`six-skill-corrective-physical-evaluation-protocol-v1.json`](six-skill-corrective-physical-evaluation-protocol-v1.json),
was not executed: it exposed a strict comparison bug because the evaluator resolved
only the nominal dataset path while the training wrapper had sealed both dataset
paths as absolute. It created no physical worker or result run.

The path-normalization repair is covered by native CPU lifecycle tests. The successor
[`six-skill-corrective-physical-evaluation-protocol-v2.json`](six-skill-corrective-physical-evaluation-protocol-v2.json),
seal `101a9f9e5ffc9c8c6a306bd8019018f728ad92a3e4a11edcbd178f530c48aa58`,
then ran its one allowed teacher-prepared bar evaluation.

- **Process wrapper:** `20260912T143358-3ea6bb7d8be8`, failed and fully reaped,
  seal `85c0dcf4fdeff6121a8fe23497f1cee1fb5f2ed81bcdfb39268f2fd26b023217`.
- **Evaluation child:** `20260912T143359-6110d95794f2`, failed, seal
  `cff0a83bb7e7c85062eb23af0e7b868d5ea67f751d48cbb7364ad6a8adcfdeb3`.
- **Actual policy device:** `mps:0`.
- **Teacher prefix:** 630 actions; all post-prefix controls came from the checkpoint.
- **Learned controls applied:** 213, independently counted from
  `worker/actions.jsonl` before the partial failed control.
- **Failure:** the contact guard stopped the run at simulation time 42.170 s when
  overlap reached 0.002515121 m, beyond the 0.0025 m limit. `bad_contacts` was
  empty; the prior error text omitted the overlap value.

The child’s original summary reported zero autonomous controls because the exception
was raised during a partial physics step before the executor returned a result. The
immutable action log is the authoritative evidence for the 213 completed controls.
The runtime now preserves that partial count and includes overlap and overtravel in
future contact-guard errors. Those diagnostics do not change this frozen result.

## Read-only trace diagnosis

Successor diagnosis `20260912T145146-e257ac568053`, seal
`c659981a4a6bc91dab9e099d7f13be581b95ae2efc98f662b4d88374a5bc1537`, reverified
the sealed child and streamed its worker traces without loading a model or changing
the result. It found 213 confirmed action-log controls plus one rejected partial
control, 10,670 post-prefix physics rows, 10,649 target-contact samples, maximum
target displacement of 0.134962956 m, no forbidden-contact events, and maximum
overlap of 0.002515121 m. The correction direction is to inspect the learned
trajectory that exceeds the overlap guard; the contact guard remains mandatory.

## Outcome and next step

This candidate is **not promoted**. Its physical success, component pass,
independent task success, autonomous workflow success, and release qualification are
all false or unproven. The next step is to define a separately frozen corrective-data
protocol only if a trajectory review supplies a bounded, measurable correction
objective. There is no automatic evaluation retry or retraining authorization in
this record.
