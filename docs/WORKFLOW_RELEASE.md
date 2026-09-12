# Freeze a local workflow release candidate

The local release declaration prevents checkpoint, model, scene or runtime
selection after evaluation results are known. It can be created only after all
seven skill checkpoints are complete and explicitly assembled into a verified
[workflow manifest](WORKFLOW_MANIFEST.md).

`workflow-release-create` binds:

- the exact seven-checkpoint workflow manifest and execution profile;
- the local Qwen model manifest and immutable upstream revision;
- the verified sixteen-input [perturbation suite](SCENE_VARIANTS.md);
- the complete ordered scene case table and child digests;
- every Python runtime source file used by the package;
- the canonical instruction, MPS policy/planner devices, 1920-pixel overhead
  planner camera, generation budget and workflow/step timeouts.

The protocol is local ARM64 prequalification. Its schema fixes
`intel_validated=false` and `release_success=null`; creating or verifying it cannot
claim task quality or Intel compliance.

`workflow-release-run PROTOCOL CASE_ID` reserves one declared case before starting
the isolated workflow process. The shared model-job lease is acquired before the
identity-addressed reservation is created, so a busy training or inference worker
does not consume the one allowed attempt. The reservation and request are flushed
before execution. A missing, truncated or unsealed reservation requires explicit
adjudication; the runner will never retry it or select a replacement scene. A clean
process child is copied into a separate evidence store and scored by the independent
dinner evaluator. The sealed case wrapper keeps execution completion, process
integrity and physical task success as separate fields. It also retains terminal
reasons, failure codes and gates, retry and intervention declarations, rejected and
partial actions, forbidden-contact counts, and planner/policy/execution/simulation
timing. It can claim only that one local scene passed.

After all sixteen reserved cases have sealed, `workflow-release-suite PROTOCOL`
reconstructs the canonical request from the protocol, then re-verifies every wrapper,
nested process, execution copy and exact source-manifest-bound evaluation. Missing,
interrupted, orphaned or contradictory reservations stop aggregation. The report
retains the complete ordered result table, failure and scoring-gate histograms,
retry/intervention/action/contact totals, timing p50/p95, observed success rate and
Wilson 95% interval. It reports the six one-factor diagnostics and ten combined
frozen test seeds separately, including the observed 10-seed target result.
`local_prequalification_passed` is true only at 16/16; `release_success` stays null
and `intel_validated` stays false.

After the serial training cohort and component checks finish, create it with:

```sh
.artifacts/workflow-venv/bin/bimanual workflow-release-create \
  --workflow-manifest .artifacts/workflows/candidate-v1.json \
  --planner-model .artifacts/models/qwen3-vl-4b-instruct \
  --scene-suite-run .artifacts/runs/20260911T235826-bd7f6e295f30 \
  --perturbation-protocol docs/experiments/dinner-perturbation-protocol-v1.json \
  --instruction "Set the dinner table with the plate, cup, spoon and fork, including the hand-off" \
  --destination .artifacts/releases/local-candidate-v1.json
.artifacts/workflow-venv/bin/bimanual workflow-release-check \
  .artifacts/releases/local-candidate-v1.json
.artifacts/workflow-venv/bin/bimanual workflow-release-run \
  .artifacts/releases/local-candidate-v1.json placement-29001
.artifacts/workflow-venv/bin/bimanual workflow-release-suite \
  .artifacts/releases/local-candidate-v1.json
```

The destination is exclusive-create. Any later source, checkpoint, Qwen manifest,
scene-suite child or configuration change invalidates the protocol and requires a
new version rather than silently changing the tested candidate.
