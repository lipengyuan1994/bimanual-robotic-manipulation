# Project status

Updated September 11, 2026. Latest pushed checkpoint: `29465a8` on
`codex/preparation-foundation`. Draft PR#1 remains unmerged.
[Roadmap](ROADMAP.md), [accepted plan](PLAN.md), [history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native runtime, portal, seven lessons, README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher passes one physical layout |
| M2 in progress | ACT and planner integration exists; learned hand-off and full dinner success remain unproven |
| M3 incomplete | Frozen release suite, Intel/OpenVINO execution and submission package remain |
| M4 incomplete | Reliability suites, native-hang crash recovery, rollback and support gates remain |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Spend stays zero. Existing-code eligibility is unconfirmed. Physical robot deployment
and pouring remain outside this release. Never relabel teacher success or runtime
checks as learned task success, generalization or Intel compliance.

## Active job and next executable step

Corrective training run `20260911T184624-653277cfce84` completed20,000updates
on native MPS in5,908.77seconds, with fallback disabled and offline caches. Its
seal is `246f19c17b7f1795b4e10c0bb9799c6c5fbeae1add264ea876bd68080c5ac6ac`.
Checkpoint, processors, sampler, temporal loss, learning-rate schedule and external
registry binding reverify. Log `.artifacts/handoff-corrective-v1-training.log`.
This proves training completion only; learned manipulation success remains unknown.

Frozen recorded-input evaluation `20260911T202723-0973816bd4b8` completed over
all630handoff frames:630valid, zero invalid/out-of-bounds, first-action mean
absolute error0.0011597rad and maximum0.0859281rad. Physical success remains null.
Seal `edae68351d72ccb9d6841647da719044f58bd24ad9a2a43f5e15485415649a89`.
Log `.artifacts/handoff-corrective-v1-recorded-eval.log`.

Frozen physical prefix2 wrapper `20260911T202840-4d435b9b3475` failed after567
actions: hand-off support/grip continuity was lost after donor hold. The verified
child used actual MPS and no teacher actions. Wrapper seal
`305e269b772d6c8cd6a6fa4b2cbab49dfe74e77ff2304162230b6e38ef3526d8`;
child seal `5a8661ce035b9a12947e5a79aacda8c55923609926e085a28cc9f69aded27869`.
Log `.artifacts/handoff-corrective-v1-physical-prefix2.log`.

Frozen physical prefix5 wrapper `20260911T203307-69308d4aecf0` also failed on
support/grip continuity after donor hold, after676actions. Its verified child used
actual MPS and no teacher actions. Wrapper seal
`18acbd0c85aae61eed7c6180657a9f3452c8b070c966d1602967923d858431c0`;
child seal `9af6175cf4a59be585a0f520ab8bc9cbb562a328cf67a71ec12baf5485c1659e`.
Log `.artifacts/handoff-corrective-v1-physical-prefix5.log`. The corrective model
reached donor hold instead of the earlier prefix2 pre-grasp stall, but did not
complete a hand-off. It is not promoted.

The remaining-six-skill protocol is frozen at
[`experiments/six-skill-training-protocol-v1.json`](experiments/six-skill-training-protocol-v1.json),
seal `777c6d54a3248de896849b0fccfcf61610fe799a0bf79c0ae74aed9c4f8a0d2a`.
It binds nominal v2 data/views, exact20,000-update MPS configurations, final-only
checkpoint selection, the prepared hand-off protocol and all three frozen
evaluation records. Both physical failures remain prerequisites as failures, not
success claims. The [resumable one-skill-at-a-time executor](TRAINING_COHORT.md)
passes seven CPU recovery fixtures; combined cohort/model-lease checks pass34tests.
Targeted training/process checks pass107tests with13optional skips.
An ordered `training-cohort-run-all` coordinator now resumes/reverifies completed
attempts, starts exactly one remaining skill at a time through the existing runner,
stops at the first sealed failure, and reports physical quality as unknown. Its
three coordinator fixtures plus the existing cohort/lease group pass18tests.

`bar_place_and_return` cohort attempt `20260911T204632-867e6f75a36e` is active;
child training run `20260911T204632-a60b589a1eea` is configured for20,000native-MPS
updates under shared model-job ownership. Session56052; log
`.artifacts/cohort-bar-place-training.log`. Poll this handle and do not launch any
other model, inference or render job. Training progress and loss are not physical
skill success.

A generic teacher-prepared component evaluator is now implemented. It verifies the
nominal-v2 source and skill boundary, executes the sealed teacher prefix through
real collision/contact physics, and then permits checkpoint actions only. Component
success requires both the physical skill outcome and successor/final-parking
readiness. Its records always disclose teacher action count and cannot set full-task,
autonomous-workflow or release success. Eight focused CPU/physics tests pass,
including a real630-action MuJoCo prefix, source-forgery rejection, shared model-job
exclusion and refusal to pass physical-only results without readiness. No trained
checkpoint has been run through this evaluator yet because the active training job
owns the model slot. The first command path remains in-process; guardian-based
native-hang cleanup is still needed before it is a release runner.
[Evaluation contract and command](SKILL_PHYSICAL_EVALUATION.md).

The six-skill component suite is frozen before any remaining checkpoint completes:
[`experiments/six-skill-physical-evaluation-protocol-v1.json`](experiments/six-skill-physical-evaluation-protocol-v1.json),
seal `f822cbdda7c9936f5ffab18d37edfa89a3c02e4a9bc37b5b0ab7c7b4d9e35b2c`.
It binds the training cohort and nineteen evaluator/runner/control/scoring/policy sources,
final-update20,000 selection,
MPS, execution prefix2, exact teacher preparation, fixed nominal-v2 scene,
twice-nominal action budgets and1,200-second wall limits. Its runner accepts only a
completed matching cohort wrapper/child, evaluates once, preserves failures and
refuses ambiguous duplicates. The focused protocol/evaluator/CLI group passes18
tests. No model or physical success is implied.

Before the suite ran, review found the outcome monitor's redundant default budget
still came from shorter v1 skill intervals. The executor now passes a guard one
action beyond its explicit budget, leaving the executor as the single stopping
authority and preventing premature v2 plate termination. The unused protocol was
regenerated before any outcome with all nineteen transitive evaluator/control/scoring
sources pinned. The combined executor/outcome/protocol/evaluator group passes61
tests; the corrected protocol re-verifies.

CPU-only analysis run `20260911T210617-481ff0b6e8eb`, seal
`6466ef3ce767e469ef58052d4832742a9b60c2f83c5ef8ca966014fc628ceb81`,
reverified both frozen physical wrappers, child logs, shared checkpoint and teacher
plan, then reproduced their contact-stage failures. Prefix2 lost continuity at
action567/physics sample18 after donor hold; its terminal right-gripper target was
`0.0707rad`, `+0.1707rad` from the nearest nominal `-0.1rad` target. Prefix5 first
completed the shared hold, then lost continuity at action676/sample30 with a
`0.1323rad` receiver target, `+0.2323rad` from nominal. This localizes the next
corrective data to receiver-close/shared-hold through donor release, with the
receiver held closed and varied measured approach starts. Per user direction,
collect/retrain that region only after all six planned local skill trainings.
[Reproduction and interpretation](HANDOFF_FAILURE_ANALYSIS.md).

Full regression85553 exited0:1,058passed,18optional skips,9render deselections,
472.02seconds. Log `.artifacts/checks-corrective-integration.log`. The subsequent
CLI-only `train --corrective-dataset` addition passed all8CLI tests separately.
Native training-environment corrective tests passed5/5, including actual Torch
chunk boundaries. Formatting, current docs and README synchronization pass.

The three-update MPS integration smoke `20260911T183755-ab866d7b2e46` completed
and its seal verifies: `8c8c021dadd71421a6f779b2a29e723a2300ec50dfa57e3759ce0c9ec2bd6eb5`.
It sampled the818-row union, reloaded checkpoint/processors, and passed external
registry reconstruction. Session35460 exited0. Log
`.artifacts/smoke-corrective-training.log`. This proves runtime compatibility only.

Active experiment protocol
`20260911T183957-c501cb44460b`, driver `.artifacts/train-handoff-corrective-v1.py`.
It adds188corrective rows to all630nominal hand-off rows, preserving the horizon10
baseline's20,000updates, batch4, seed0, architecture, loss, learning-rate schedule
and nominal image statistics. Numeric normalization uses the selected union.
Final checkpoint only; frozen recorded-input and physical prefix2/prefix5 checks
retain all failures and unchanged guards. This tests approach drift, not a claim
that donor-release ambiguity or full dinner execution is solved.

## Corrective demonstration evidence

The training-only feedback teacher reaches open-gripper approach subgoals using
measured joints and bounded collision-checked commands. Real acquisition actions
create starting-joint variation; they remain in the recording but are excluded
from corrective labels and declared as interventions. No object teleportation,
attachments, or privileged deployed-policy inputs were added.

Four-source view `.artifacts/feedback-corrective-views-four.json` verifies:

| Source run | Seed | Eligible actions |
|---|---:|---:|
| `20260911T183319-0c211f8f51c2` | 0 | 76 |
| `20260911T182943-df32bfbe811b` | 7 | 37 |
| `20260911T183327-c61378694d99` | 8 | 38 |
| `20260911T183334-0a0f2eecf2e1` | 9 | 37 |

All four recorded approaches completed in the same physical layout. LeRobot
export `.artifacts/datasets/feedback-corrections-v1` and independent reload verify
all188RGB/joint/action/timestamp/index mappings; manifest digest
`98480e5e21dd0699786191e775b224245d0749c10d1b93734438fe6a0ae39633`.
Export35213 and verification59964 exited0. Native media imports emitted duplicate
AVFoundation-class warnings without export failure; installed libraries were not
modified. [Collector, boundaries and commands](FEEDBACK_TEACHER.md).

Separate review found no actionable composition/normalization/registry defect.
Explicit corrective-dataset relocation is under validation: registry and policy
can accept a copied dataset only after full source/hash/statistics checks, while
preserving original sealed sampling identity. Six relocation tests pass. Actual read-only registry check15849 exited0 against
a local copy (no model inference); log `.artifacts/corrective-relocation-check.log`.
Workflow v2 pins relative corrective paths and export hashes, passing resolved
locations through policy preload. Six targeted compatibility tests pass; the prior
combined workflow suite passed21tests. Parent combined regression83708 exited0:50tests passed in71.53seconds.
Required fullcheck11603 exited0:1,073passed,18optional skips,9render deselections,
487.52seconds; log
`.artifacts/checks-corrective-relocation.log`. V1 body seals are preserved.
The completed corrective training experiment was not changed. Source confinement
rejects output nested in corrective datasets before allocating files in both
execution paths; all9confinement tests pass. Guardian integration passes the full
regression reported below.
The ordinary dataset intake still rejects intervened episodes.

Horizon50 training completed20,000updates, but both physical comparisons failed:
prefix2 exhausted900actions; prefix5 expired after634actions. Full traces show no
bilateral grasp and approach drift. Do not promote that checkpoint. The horizon10
baseline reached shared contact in one comparison but never completed transfer.
All earlier runs, diagnostics, hashes and profiling are preserved in
[the experiment history](STATUS_HISTORY.md). No learned hand-off success yet.

## Model and physical evidence

- Teacher `20260911T114540-8b3b1ff0238d`:5,049actions,5,050observations,
  15,150RGB images,252,450physics samples; both physical scorers pass with zero
  forbidden contacts. LeRobot export and seven boundary checks pass. One scene only.
- First full-handoff ACT `20260911T122319-b2ee550f005b`:20,000updates completed.
  Recorded evaluation `20260911T131631-11ba2033068e`:630valid bounded forecasts;
  first-action mean error0.00335rad, maximum0.18855rad. Not held-out validation.
- Physical prefix1 `20260911T131735-2cd345d50623`:failed after900actions.
  Prefix5 `20260911T133038-335ba4618a39`:failed on forecast expiry.
  Prefix2 `20260911T133149-1555757a5255`:failed after900actions, pre-grasp stall.
  No limits were relaxed and all attempted runs remain preserved.
- Reproducible phase-error analysis `20260911T134740-40a7dd56482b` verifies
  source seals and target alignment. [Training](SKILL_TRAINING.md).
- Qwen `20260911T121102-7f242fa1b264`:four bounded visibility/recipient cases pass;
  earlier failures remain. No broad planner success or prompt promotion.
  [Planner](PLANNER_LIVE_INTEGRATION.md).

## Visual variants and application

`dinner-teacher --recipe v2 --visual-seed N` generates only lighting and
floor/workbench colors, records separate scene/layout hashes and preserves targets.
Seed7 run `20260911T141555-ae5762976ce8` passes both full physical scorers over
5,049actions with zero forbidden contacts. Rendering/recording were disabled.
Camera variation and variant demonstrations remain unvalidated. Existing nominal
skill views explicitly reject variants; a separate validated view/data path is
still needed. Physical placement/mass/friction/shape variation remains unfinished.
[Scene](DINNER_SCENE.md).

The separate [visual-training allocation](experiments/visual-training-protocol-v1.json)
is frozen before visual-data training: training seeds7–10, validation1001–1002,
test2001–2010. Seal `8c3755c717cbb1a213e3523353df4d2d8ba1e155af756be8685e2657a6f9ec7c`.
Known development seeds0/7 cannot enter held-out sets. Protocol validation passes
24CPU tests and binds the current v2 assets and visual generator. This is an
internal visual-only experiment on one physical layout, not the final production
or organizer evaluation suite. No visual recordings have entered training;
verified export/view/composition integration remains the next data step after
the frozen hand-off evaluation sequence frees the model/render slot.
[Protocol and source-verification guide](VISUAL_TRAINING.md). The source verifier
and CLI pass41targeted checks, including rejection by real physics scorers of a
synthetic integrity fixture. No real visual recording has passed this gate yet.

The opt-in operator supports one worker, start/stop, verified history, progress
and three-camera previews. History pages omit large training-update arrays while
retaining the complete trace. Guardian-based native-hang cleanup now passes
component tests and an integrated original-parent-loss/restart test.
Parent-record reconstruction remains unresolved. The original portal service was not restarted.
[Execution](WORKFLOW_EXECUTION.md).

## Verification and delivery

- Latest full regression:1,093passed,18optional skips,9render deselections in504.38s,
  `.artifacts/checks-guardian-integration.log`. Additional parent-loss and24visual
  protocol tests pass separately; combined process/operator suite57/57passes.
  Native corrective tensor tests5/5pass. Lint and formatting pass.
- Documentation447links and README synchronization pass in that check. Earlier
  12-file learning-site checks pass.
  Native frontend build and prior isolated browser fixtures pass; no current
  live learned-workflow camera validation is claimed.
- Fresh base wheel installation `20260911T140058-01b5bd0ef785` passed offline
  against hashed lockfile requirements:ARM64,68compiled extensions, CPU arithmetic
  and MuJoCo stepping. It predates visual variants and excludes ML extras/rendering.
  [Repeatable installation](SETUP.md).
- Checkpoint548327d is pushed; its remote CI is not yet verified. Checkpointc124e4a's portal job passes and its Python/render job is
  still running. Prior checkpoint2399b2f's GitHub Actions
  runs34635313597 and34635303088 now have successful portal and Python/render jobs.
  These checks cover pushed2399b2f, not the subsequent working-tree changes.
  No merge is authorized here.

## External dependencies and learning

Intel access was rejected without explanation. Per user direction, defer all Intel
setup/access work until local training for the planned skills is complete, not
merely the first checkpoint. No paid resources are authorized. Actual Intel runs
remain mandatory for Intel compliance. [Access](INTEL_ACCESS.md).

Organizer assets/seeds, prior-code eligibility and hosting details remain provisional.
User reports completion of lessons1–2. Lessons3–7 are available; the training-evidence
reference now includes actual failed physical attempts. No additional mastery has
been recorded. [Learning](LEARNING.md), [questions](ORGANIZER_QUESTIONS.md).


## Pending operational hardening

The standalone guardian is now wired into workflow execution. Its eight real-process
component tests include original-parent death during a GIL-held native call with
SIGTERM ignored. The integrated process suite passes26tests, including guardian
crash cleanup, malformed terminal records, lease release after publication failure,
and protection against multiprocessing automatic PID reaping. The worker lease
passes five tests. These are CPU fixtures, not learned manipulation evidence.
The additional integrated parent-loss test passes in2.26seconds: it kills the
actual workflow owner during a GIL-held native call, verifies TERM/KILL and worker
reap, then completes a replacement fixture on the same evidence store. The old
parent remains unsealed. Session21074 exited0; no model was loaded.
Combined process/guardian/lease/operator verification22842 exited0:57passed
in30.09seconds, log `.artifacts/checks-guardian-process-final.log`.

The operator shutdown budget now includes guardian escalation, group exit and
worker-lease release. Required full regression52845 exited0:1,093passed,18optional skips,9render
deselections,2warnings in504.38seconds; log
`.artifacts/checks-guardian-integration.log`. It predates the additional parent-loss
test and24visual-protocol tests, which passed separately. Scope is POSIX/Python3.12, one worker with threads;
independently launched subprocess trees and parent-record reconstruction remain
unsupported. The portal was not restarted. Frozen physical prefix2 evaluation
session30402 is the only active model/render job.

Uncommitted shared model-job ownership now makes training and the default workflow
use the same `.model-job.lock`. Two focused tests pass: a competing training start
is rejected before run allocation, the lease becomes available after the owner
exits, and nested cohort evidence borrows the continuously held top-level lease.
All84 existing training tests pass with13 optional-dependency skips;47 earlier
cohort/process tests pass. Full regression for this working tree is still required.
