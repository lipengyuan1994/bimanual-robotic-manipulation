# Activate and roll back a local workflow

A deployment record selects one fully verified seven-checkpoint workflow manifest
for local operation. Activation rechecks the dataset, skill views, all checkpoints,
corrective data, successor references and execution profile. It does not load a
model or claim that the workflow succeeds physically.

After creating and checking a candidate, activate it:

```sh
.venv/bin/bimanual workflow-activate \
  .artifacts/workflows/candidate-v1.json

.venv/bin/bimanual workflow-deployment-status
```

The default registry is `.artifacts/workflow-deployment`. Use
`--deployment-root PATH` on activation, status, rollback and deployed execution
when operating a separate installation. The registry writes an immutable JSON
generation before atomically changing `current.json`. Each generation records the
exact manifest path, file digest, canonical body seal, prior activation and whether
the action was an activation or rollback. Quality fields stay explicitly unknown
or false.

Run the selected manifest only after status reverifies it:

```sh
.artifacts/workflow-venv/bin/bimanual workflow-run \
  --deployment-root .artifacts/workflow-deployment \
  --planner-model .artifacts/models/qwen3-vl-4b-instruct \
  --instruction "Set the dinner table with the plate, cup, spoon and fork, including the hand-off" \
  --policy-device cpu --planner-device cpu
```

Supplying a positional manifest remains a direct diagnostic path. `workflow-run`
requires exactly one positional manifest or deployment root; it rejects both and
neither. Both paths still use the same guarded process, shared model-job lease and
independent evaluation boundary.

To return to the immediately prior verified activation:

```sh
.venv/bin/bimanual workflow-rollback
```

An operator can name an older recorded generation with `--target-id`. Rollback
reverifies that generation's full manifest lineage, then creates a new immutable
activation; it never edits or copies checkpoints. A changed or missing manifest,
invalid pointer, unknown identity, or interrupted record fails closed.

If a crash leaves an immutable generation without `current.json`, the registry
requires manual adjudication. Preserve the directory. Confirm whether the pointer
was never published, inspect the generation and source manifests, then create a
new registry or documented repair rather than deleting a lock or guessing which
model ran. This protects audit history at the cost of automatic recovery from the
small record-to-pointer crash window.

Focused tests cover idempotent activation, rollback history, source mutation,
corrupt/missing pointers, orphaned generations, identity confinement and CLI input
selection. They use verification fixtures and load no model; real rollback
qualification still requires two complete local candidates and operational trials.
