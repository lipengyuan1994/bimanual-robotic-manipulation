# Six-skill corrective teacher collection

This collector consumes one case from the sealed
[six-skill corrective protocol](experiments/six-skill-corrective-collection-protocol-v1.json).
It runs only a privileged scripted teacher in the real MuJoCo `DinnerEnvironment`.
It does not load a learned policy, manipulate object state directly, attach objects,
or create a training dataset.

Each source records three synchronized parts through `DemonstrationRecorder`:

1. the contact-checked teacher prefix that reaches the component’s starting state;
2. one bounded measured-joint probe and exact measured-state recovery command; and
3. the frozen source-plan replay interval.

All recorded actions are initially `training_eligible: false`. Acquisition has no
candidate replay label. A later independent source validator must verify the physical
trace and choose any replay labels before retraining. A completed collection is teacher
evidence only; it is not learned skill success.

A case identity is `family-seed`. The five approach/contact seeds rotate in their frozen
order across cup, plate, fork, cup, plate; other families each use their sole skill.
A reservation is created before physics starts. Failed and interrupted reservations stay
consumed, and rerunning the same exact request returns its verified manifest.

```bash
.venv/bin/bimanual skill-corrective-protocol-check \
  docs/experiments/six-skill-corrective-collection-protocol-v1.json
.venv/bin/bimanual skill-corrective-run \
  docs/experiments/six-skill-corrective-collection-protocol-v1.json \
  bar_contact_avoidance-51000
```

Run each of the twenty cases at most once, preserve every outcome, and do not begin
local retraining until a separate validation/export boundary exists.

The validator creates an immutable view that selects only verified replay actions:

```bash
.venv/bin/bimanual skill-corrective-views-create /private/tmp/bar-view.json \
  six-skill-corrective-9d2fae6f6ad5f8027a2a4991
.venv/bin/bimanual skill-corrective-views-check /private/tmp/bar-view.json
```

Use the native training environment for the offline export and decoded-data check:

```bash
HF_HUB_OFFLINE=1 HF_HOME=.artifacts/hf-offline \
  .artifacts/training-venv/bin/bimanual skill-corrective-export \
  --views docs/experiments/six-skill-corrective-views-v1.json \
  --destination .artifacts/datasets/six-skill-corrective-bar-v2 \
  --repo-id local/six-skill-corrective-bar-v2
HF_HUB_OFFLINE=1 HF_HOME=.artifacts/hf-offline \
  .artifacts/training-venv/bin/bimanual skill-corrective-export-check \
  .artifacts/datasets/six-skill-corrective-bar-v2
```

## Per-skill corrective training boundary

The complete corrective archive may retain several skills so that raw evidence is
preserved once. It is not a multi-task policy label. Before ACT training, the
training runtime reloads the sealed corrective view and selects only source
intervals whose `skill_id` equals the selected nominal skill view. It reindexes
only that subset for sampling, keeps its original source indices in the sampling
record, and rejects an empty or substituted selection. For example, a cup
checkpoint cannot silently train on a drawer or utensil replay merely because all
three are stored in the same immutable archive.

This is a data-lineage guard. It does not make the scripted teacher data a learned
success claim; the resulting checkpoint still requires frozen physical evaluation.
