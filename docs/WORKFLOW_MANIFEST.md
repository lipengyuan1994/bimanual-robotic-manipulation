# Pinned checkpoints for the complete dinner workflow

A development workflow manifest names all seven skill checkpoints, in order:
hand-off, bar placement/return, cup, plate, drawer, spoon and fork. It pins their
training seals and checkpoint digests to the same verified dataset and skill-view
manifest. There is no automatic selection of a latest checkpoint. A complete
manifest is an integrity/compatibility record, not evidence that the skills work.
There is currently **no physically validated seven-checkpoint cohort**.

Create a new version after explicitly choosing all seven runs:

```sh
.venv/bin/bimanual workflow-create \
  --dataset .artifacts/datasets/dinner-nominal-v1 \
  --skill-views .artifacts/dinner-skill-views-v1.json \
  --destination .artifacts/workflows/candidate-v1.json \
  --training-run HANDOFF_RUN --training-run BAR_RUN \
  --training-run CUP_RUN --training-run PLATE_RUN \
  --training-run DRAWER_RUN --training-run SPOON_RUN --training-run FORK_RUN

.venv/bin/bimanual workflow-check .artifacts/workflows/candidate-v1.json
```

The uppercase run paths above are placeholders, not existing trained skills.
Creation refuses to overwrite a manifest. Paths are relative to its directory,
so a complete artifact tree can move to another host. Verification still checks
every referenced artifact; moving the JSON alone does not move its dependencies.
Neither command imports a model checkpoint into an inference backend or runs the
robot. A changed manifest body, dataset file, skill view, checkpoint, or training
seal is rejected. Missing, repeated or reordered skills cannot form a cohort.

The manifest keeps **file digests and canonical body seals distinct**. The
export file digest binds exact JSON bytes. Successor references carry the
export's verified body seal and measured terminal observations. Comparing these
two hashes directly would reject valid data; their names and tests distinguish
them. All successor references bind the same parent episode. The final fork
reference checks final parking and does not invent an eighth skill.

## Preloading and execution

`load_workflow_manifest(path)` returns a frozen verified record with checkpoint
bindings and successor references. `preload_workflow(record, device="cpu")`
reverifies it before loading policies, compares each loaded binding, and checks
the cohort again afterward. Supported local devices are CPU and MPS. This is
local inference only; OpenVINO and actual Intel validation remain separate work.

`LoadedWorkflow.executor_factories(worker)` supplies a new single-attempt
executor per capability, using models already loaded into memory. One loaded
cohort belongs to one worker; sharing mutable ACT policy state across workers is
rejected. Construct each executor before starting visual planning, because
reference verification reads files and may take longer than a camera's freshness
window. The workflow runner then starts it with the exact authorized observation.

Tests use sealed synthetic dataset/checkpoint fixtures to cover all seven
bindings, final parking, pinned digest failures, missing skills, manifest tampering,
load ordering and model-sharing restrictions. These tests do not execute real
learned manipulation. The original nominal dataset also has a known bar-successor
readiness gap; packaging it cannot resolve that gap or certify reliable chaining.
