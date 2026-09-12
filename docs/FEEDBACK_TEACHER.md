# Feedback approach demonstrations

This training-only collector moves the open left gripper through orientation,
approach and descent subgoals in the authored dinner scene. It stops before
closing the gripper. A completed run means approach subgoals were reached;
it does not mean a grasp, hand-off, learned skill or dinner workflow succeeded.

## Why this exists

The horizon50 ACT checkpoint produced finite, bounded forecasts on all630 recorded
inputs, but failed both physical comparisons. Full-trace analysis found no
bilateral finger contact. At the stalled states, the last20 first-action commands
projected backward along the nearest teacher approach direction. Those comparisons
are diagnostic; a nearby teacher frame is not automatically a safe corrective label.
See [status](STATUS.md) and [experiment history](STATUS_HISTORY.md).

The collector computes each bounded command from measured joints toward the
current joint subgoal, checking the proposed path for forbidden collisions. It
advances using measured position and velocity rather than a scheduled frame index.
The subgoals come from verified teacher assets. This is privileged training control,
not a deployed policy and not a substitute for learned execution.

## Run locally

Use the verified native environment from [setup](SETUP.md):

```sh
.venv/bin/bimanual feedback-approach
.venv/bin/bimanual feedback-approach --record-demonstration
```

Recording captures three fresh cameras before each action, records only confirmed
transitions, and retains a terminal observation. Evidence binds controller,
configuration, scene and code provenance. Failure evidence must remain available;
an interrupted or partial action cannot become a successful training transition.

## Observed prototype results

- `20260911T182014-d5975b976748`: three subgoals reached in76actions;
  3,800physics samples, zero forbidden-contact rows; no rendering.
- `20260911T182142-82bacc879387`:76actions,77observations,231camera images;
  episode and image integrity checks pass. Final overhead image inspected.

These runs used preserved prototype drivers. They do not by themselves validate
subsequent packaged collector changes. Record packaged-command verification
separately in the status record.

## Packaged command validation

CPU run `20260911T182702-c865ecbe7bbd` and recorded run
`20260911T182712-57ecfd9a0eba` both complete three subgoals in76actions.
The recorded run has77observations across three cameras and a verified evidence
seal. Eighteen focused collector/CLI tests pass, including cancellation, collision
rejection, recording boundaries after partial physics, and cleanup failures.
Full regression status is tracked in [status](STATUS.md).

## Corrective data boundaries

Starting-joint variation is available with:

```sh
.venv/bin/bimanual feedback-approach --variation-seed 7 --acquisition-offset-rad 0.06 --record-demonstration
```

This reaches a perturbed orientation pose through bounded real actions, then
runs the three original corrective subgoals. The seeded offset affects only the
first four left-arm joints and cannot exceed0.08rad. Every action is preserved;
`training_eligible=false` labels acquisition, and `correction_start_action` marks
the first eligible action. The episode reports one intervention when acquisition
occurs, so ordinary successful-episode intake cannot silently train on it.
This is initial robot-state variation, not independent scene randomization or a
validated remedy for learned approach drift.

Recorded seed7 run `20260911T182943-df32bfbe811b` completed79actions:
42 acquisition and37 correction, with80observations. Its evidence seal verifies.
The separate corrective-view validator accepts only the37 corrective transitions
and rechecks all source/image hashes, action alignment, intervention count and
seed. It rejects recordings missing the explicit correction boundary. Commands:

```sh
.venv/bin/bimanual corrective-views-create --run-id 20260911T182943-df32bfbe811b --destination .artifacts/my-corrective-views.json
.venv/bin/bimanual corrective-views-check .artifacts/my-corrective-views.json
```

Repeat `--run-id` to include additional verified sources. Outputs are created
exclusively and never overwrite an existing manifest. Chunk windows remain inside
one correction interval and mark repeated terminal action targets as padding.
A separate local LeRobot export preserves these bindings and complete original
records. In the verified training environment, with `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` set before Python starts:

```sh
.artifacts/training-venv/bin/bimanual corrective-export --views .artifacts/feedback-corrective-views-four.json --destination .artifacts/datasets/my-corrections --repo-id local/my-corrections
.artifacts/training-venv/bin/bimanual corrective-export-check .artifacts/datasets/my-corrections
```

Actual export `.artifacts/datasets/feedback-corrections-v1` contains188rows from
four sources (nominal seed0 and perturbed seeds7,8,9). Export and independent reload
parity checks pass for RGB, joints, actions, instructions, timestamps and indices.
The export manifest digest is
`98480e5e21dd0699786191e775b224245d0749c10d1b93734438fe6a0ae39633`.
This is training data, not a trained manipulation result. The optional combined
training/checkpoint path remains under validation.

Further corrective variations remain work in progress. Reach disturbed states through
real bounded robot actions from normal reset; never teleport objects. Preserve
acquisition actions and interventions, but do not silently label a deliberate
wrong-way disturbance as the desired policy action. A future training-view contract
must identify eligible correction transitions and their original observations,
with immutable source lineage and explicit exclusion of acquisition actions.

Do not insert these approach-only episodes into the fixed full-handoff view or
claim that multiple recordings of one layout are independent physical scenes.
The nominal seven-skill view contract remains unchanged. Extend dataset intake
explicitly before training on corrective segments. If repeated sensor states still
require different actions across subgoals or safety dwell, resolve that ambiguity
with consistent supervision or a versioned causal observation history shared by
training and inference; never expose privileged teacher phase or elapsed plan time.
