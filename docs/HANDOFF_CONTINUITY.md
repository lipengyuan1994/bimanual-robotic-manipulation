# Hand-off continuity corrective data

The first corrective hand-off checkpoint reached donor hold but failed two frozen
physical evaluations when the receiver lost its grip during donor release. The
[failure analysis](HANDOFF_FAILURE_ANALYSIS.md) therefore identifies a narrow missing
data region: receiver close, shared hold and donor release from varied measured
receiver starts. The old approach-only corrective dataset remains immutable and is
not relabeled as continuity training.

The frozen
[`handoff-continuity-collection-protocol-v1.json`](experiments/handoff-continuity-collection-protocol-v1.json)
binds the unpromoted diagnosis, nominal-v2 scene/plan/layout, correction code,
phase boundaries, a 0.015-radian envelope and nine cases. The allocation contains
one baseline plus positive and negative offsets for the receiver shoulder pan,
shoulder lift, elbow flex and wrist flex. These are measured starts in one authored
layout; they are not nine independent scenes or generalization evidence.

Each case starts from a normal reset and:

1. replays teacher actions `[0, 310)` to establish a two-second donor-only hold;
2. moves the open receiver to its frozen measured-start offset while the donor and
   both grippers remain fixed;
3. records training-eligible convergence to teacher frame 369 and teacher actions
   `[370, 530)`, covering receiver descent/close, shared hold and donor release;
4. records `[530, 630)` as validation-only donor retreat and receiver-only hold.

All actions, three cameras and 1 kHz contacts are retained. Prefix, acquisition and
validation actions remain in raw evidence but are excluded from corrective training.
The collector does not set object poses, attach the bar or apply external forces.
Independent scoring requires ordered donor/shared/receiver holds, continuous airborne
grip, zero forbidden contacts, no partial actions and bounded overlap. A failed or
interrupted case consumes its reservation and cannot be replaced automatically.

The protocol verifies locally now. Physical collection waits until the active serial
training sequence releases the shared simulation/model lease:

```sh
.venv/bin/bimanual handoff-continuity-protocol-check \
  docs/experiments/handoff-continuity-collection-protocol-v1.json
.venv/bin/bimanual handoff-continuity-run \
  docs/experiments/handoff-continuity-collection-protocol-v1.json receiver-baseline
```

Run every declared case in protocol order and retain every outcome. A separate views,
LeRobot export and training intake are implemented. They accept only completed sources
whose physical score reproduces from the sealed 1 kHz trace, keep action chunks inside
the eligible correction interval, and label the training region
`corrective_receiver_continuity`. The earlier `corrective_approach` profile remains
supported and distinct. After all nine physical cases pass, create and export the new
version with:

```sh
.venv/bin/bimanual handoff-continuity-views-create \
  --run-id FIRST_CASE_RUN --run-id SECOND_CASE_RUN \
  --destination .artifacts/handoff-continuity-views-v1.json
.artifacts/training-venv/bin/bimanual handoff-continuity-export \
  --views .artifacts/handoff-continuity-views-v1.json \
  --destination .artifacts/datasets/handoff-continuity-v1 \
  --repo-id local/handoff-continuity-v1
HF_HUB_OFFLINE=1 .artifacts/training-venv/bin/bimanual \
  handoff-continuity-export-check .artifacts/datasets/handoff-continuity-v1
```

List all nine run IDs in frozen protocol order; the two shown above only illustrate
the repeated option. No current checkpoint is promoted by creating this protocol or
implementing the collector/export boundary.
