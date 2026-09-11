# Project status

Updated September 11, 2026. Latest pushed checkpoint: `cb1c9e3` on
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

Corrective training session61470 is active, run `20260911T184624-653277cfce84`:
20,000updates on native MPS, with
fallback disabled and offline caches. Log `.artifacts/handoff-corrective-v1-training.log`.
Poll this existing handle; do not start another model/render job or restart from
an observation timeout. The training protocol is frozen below. No physical success
is implied by progress or loss.

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
Corrective dataset relocation is currently rejected; portability remains unfinished.
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

The opt-in operator supports one worker, start/stop, verified history, progress
and three-camera previews. History pages omit large training-update arrays while
retaining the complete trace. Cooperative parent loss now cancels the worker and
preserves its sealed result; hung native calls and parent-record reconstruction
remain unresolved. The original portal service was not restarted.
[Execution](WORKFLOW_EXECUTION.md).

## Verification and delivery

- Latest full regression:1,058passed,18optional skips,9render deselections in472.02s,
  `.artifacts/checks-corrective-integration.log`. Subsequent CLI-only option tests8/8
  pass; native corrective tensor tests5/5pass. Lint and formatting pass.
- Documentation447links and README synchronization pass in that check. Earlier
  12-file learning-site checks pass.
  Native frontend build and prior isolated browser fixtures pass; no current
  live learned-workflow camera validation is claimed.
- Fresh base wheel installation `20260911T140058-01b5bd0ef785` passed offline
  against hashed lockfile requirements:ARM64,68compiled extensions, CPU arithmetic
  and MuJoCo stepping. It predates visual variants and excludes ML extras/rendering.
  [Repeatable installation](SETUP.md).
- Latest known CI for prior checkpointcadebbe:run34608198429 was in progress.
  Inspect current-commit CI before asserting it passes. No merge is authorized here.

## External dependencies and learning

Intel access was rejected without explanation. Per user direction, defer all Intel
setup/access work until local training for the planned skills is complete, not
merely the first checkpoint. No paid resources are authorized. Actual Intel runs
remain mandatory for Intel compliance. [Access](INTEL_ACCESS.md).

Organizer assets/seeds, prior-code eligibility and hosting details remain provisional.
User reports completion of lessons1–2. Lessons3–7 are available; the training-evidence
reference now includes actual failed physical attempts. No additional mastery has
been recorded. [Learning](LEARNING.md), [questions](ORGANIZER_QUESTIONS.md).
