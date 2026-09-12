# Project status

Updated September 11, 2026. Latest implementation checkpoint: `f8d41b1` on
`codex/preparation-foundation`. Draft PR#1 remains unmerged.
[Roadmap](ROADMAP.md), [accepted plan](PLAN.md), [history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native runtime, portal, seven lessons, README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher passes one physical layout |
| M2 in progress | ACT and planner integration exists; learned hand-off and full dinner success remain unproven |
| M3 incomplete | Frozen release suite, Intel/OpenVINO execution and final submission package remain |
| M4 incomplete | Reliability suites, real-candidate rollback trials and support gates remain |

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

The failed checkpoint now has a separate continuity-correction data boundary rather
than widening its historical approach-only dataset. Frozen protocol
[`experiments/handoff-continuity-collection-protocol-v1.json`](experiments/handoff-continuity-collection-protocol-v1.json),
seal `a8eaa8100b75c2a0bdc4275a4a47fa3b5bd324df17701f98ca92368febc555be`,
binds the verified unpromoted diagnosis, exact nominal-v2 assets and nine receiver
start cases at a 0.015-radian envelope. The contact-only collector retains prefix,
acquisition, correction and validation evidence, but marks only receiver convergence
through donor release as training eligible. Independent scoring requires ordered
donor/shared/receiver holds and continuous grip. The source views independently
recompute the physical score, select only the correction interval, and pad chunks
before the validation tail. A separate LeRobot-v3 export preserves all raw source
evidence, verifies decoded RGB/joint/action parity and enters training under the
distinct `corrective_receiver_continuity` region. The historical approach-only
profile remains accepted without changing its semantics. The continuity protocol,
scoring, views, export and profile dispatch groups pass36tests; broader corrective
and relocation checks pass49tests. No case has executed because active serial
training owns the shared model lease; creating this boundary is not corrective data,
retraining or hand-off success. The complete non-render repository gate after this
integration passes1,318tests with18documented optional skips,9render deselections
and two dependency deprecation warnings in597.50seconds.

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
four coordinator fixtures plus the existing cohort/lease group pass16tests. A bounded
active-owner wait can idle behind the current model lease and then resume the frozen
sequence; it does not inspect model state, bypass ownership, retry failures or catch
unrelated runtime errors.

`bar_place_and_return` cohort attempt `20260911T204632-867e6f75a36e` completed and
sealed all20,000native-MPS updates. Wrapper seal
`828147c082bb2bd0e682ffe641a7e805c1e2ee4729a2fe0c0114d57c2acbf9a0`;
child `20260911T204632-a60b589a1eea`, seal
`5ec8946b9174db540e5a03aebc20e068a19e5cb964b7c7975079b406bd6a5ebf`;
checkpoint `b3363d5980efa1a3d04f0f1aa7350823a73500d7a1ce0910d872f54db195aa07`.
This proves training completion only.

The waiting coordinator then allocated cup attempt
`20260911T222550-b516bc6370d5`, but its restricted process could not see Metal and
failed before update1 with `Requested MPS unavailable; no fallback`; it stopped
the sequence and exited1. The exact native interpreter reports ARM64, MPS built,
MPS available and one device outside that restriction. Adjudication run
`20260911T223530-cb658d888223`, seal
`ef3140bc7551c5a1ec9fc7fe1e22143b0f12c16ed2d19217b90e9c8ccd6ee5a4`,
preserves the failed wrapper/child identities, proves zero updates and no
checkpoint, records the live MPS probe, and authorizes exactly one replacement.
It makes no training or physical claim.

Replacement cup attempt `20260911T223642-23fabd26e102` completed and sealed all
20,000 native-MPS updates. Wrapper seal
`e6bf5ff7cb8acff542e3ee3d8886600788a446c32974b1c5c5d32631f973c185`;
child `20260911T223642-9b4a6482722b`, seal
`d4ea0df77fcee0f2754a42ea78462d1b876d632675a0f4f39f5b3450c03b155a`;
checkpoint `d0e2a96d7b29c841e707b5fa929469edc95ac9828fe62f3176891b8824adf328`.
This proves training completion only. The same native process allocated active
`plate_pick_place` wrapper `20260912T001417-968c928850a3`, child
`20260912T001417-2e614f4afc6e`, which completed and sealed all 20,000 updates.
Wrapper seal `c5a3c58acd086cef0e5a9be104b9b2c9a275a2781a087e0f495c3960e4651a0a`;
child seal `b624fa31d4ba163259d1a8fd7ac67186a7393ac52e81090e894d61960fbd500c`;
checkpoint `49a2cdd82d1a457b132049155a17d7222de5fc29400e2c42f20f43120389bd83`.
This is training completion only; plate manipulation remains untested. The
`drawer_open` wrapper `20260912T014959-e04ee487ae95` and child
`20260912T014959-e973f584306d` then completed and independently reverified all
20,000 native-MPS updates. Wrapper seal
`228b6fde6480af5a952e2555ea0e0a158edffe89f6c47a3c57e56885b2bb2651`; child
seal `b1dd438ad076cce0ace7a1a1a1936798bcbbe2ab25043781ae1f662e1337add0`;
checkpoint `4c111e572e74cee759f1838377601d7cea393ab938c716ff0d2199dd7942edc9`.
Drawer manipulation remains untested. The `spoon_retrieve_place` wrapper
`20260912T033121-93082ac2bf9a` and child `20260912T033121-70afbc38d04c` then
completed and independently reverified all 20,000 native-MPS updates. Wrapper
manifest SHA-256 `bf249c2c6da399945db5a6db89e158b123489441caafa97d5ec30935706d33d3`;
child manifest SHA-256 `f3c5ccdfb7d726a066a211125f62361944ad301b031a04c6a0e8743a51ebc885`;
checkpoint `043299789355afd30abe126fc20037bbaac6fefdcb174cc77088aec0f5d1674b`.
Spoon manipulation remains untested. The final `fork_retrieve_place` wrapper
`20260912T051013-349dc05877f1` and child `20260912T051013-a1e71cfdf885` then
completed and independently reverified all 20,000 native-MPS updates. Wrapper
manifest SHA-256 `1769fa9a4546bc6077bc239e6ffd5e5008de117216754f1b2c948733a756dda5`;
child manifest SHA-256 `465c90fda5a5208b618628193d1e29de6d734fb92b05f1e6a30fbf3cc7a6b5ea`;
checkpoint `9583437c92db08a4b4767a4b5cccac04a76388a3fe941f7b029891c6846eea6e`.
All six planned local individual-skill training runs are now complete. This is
training completion only: fork manipulation and every other learned skill remain
untested physically. The next executable step is exactly one frozen six-skill
physical protocol run under the released shared model lease. Log
`.artifacts/cohort-remaining-sequence-replacement.log`.

The continuity collector now runs below a bounded guardian and native spawned
worker. It reserves the shared model lease before allocating output, retains
consumed interrupted reservations, reaps a hung worker after cancellation, timeout
or parent loss, and verifies the child recording before exposing it. CPU lifecycle
fixtures cover clean success, physical failure, wrong child identity, lease
contention, a termination-resistant worker, parent death and evidence-source
confinement. No continuity case has run. The frozen protocol was regenerated before
its first case with seal
`a8eaa8100b75c2a0bdc4275a4a47fa3b5bd324df17701f98ca92368febc555be`.

A frozen visual-planner decision-suite boundary is now implemented. A write-once
protocol binds the exact Qwen model manifest/revision, sealed source runs and
observations, optional sensor bundles, instruction context, accepted outputs, case
order and interpreter sources before inference. Its runner verifies and copies all
inputs before one model load, evaluates every case, preserves malformed and wrong
answers, and separates process completion from case success. Five CPU-only fixtures
pass. The result now retains a full case table plus field-level mismatch counts,
malformed-case count, decision rate with 95% Wilson interval, and inference-latency
p50/p95. Every result denies live dispatch, keeps physical manipulation success null
and carries no evidence claims. The real dinner protocol is deliberately not frozen
or run until high-resolution inputs can be captured after the active serial ACT
training finishes. [Planner evaluation boundary](PLANNER.md#frozen-decision-suite).

The missing six-family robustness input boundary is also implemented and frozen.
The generator makes bounded, deterministic pre-load changes to object placement,
mass, sliding friction, horizontal shape, lighting and background, while recording
every changed XML attribute. Protocol
[`experiments/dinner-perturbation-protocol-v1.json`](experiments/dinner-perturbation-protocol-v1.json),
seal `3aba583eecc9ba96d6e703d61fcf58d236fdafcd907c45ba01b3bab36446cff7`,
reserves seed29001 for six one-factor diagnostics and seeds30001–30010 for ten
all-family combined tests. Twenty-six generator/protocol fixtures pass, including
actual SO-101 scene compilation. No perturbed policy evaluation has run, and
prepared scenes keep task success unknown. [Perturbation boundary](SCENE_VARIANTS.md).
The learned workflow now accepts one verified prepared scene as an optional input.
It checks the bundle before model preload, the worker independently rechecks and
declares it before MuJoCo starts, and the dinner evaluator binds its run/protocol,
family, seed, scene and layout hashes to the sealed worker files. Nominal execution
is unchanged. The scene-bundle, worker, orchestration and learned-audit group passes
121 CPU/physics fixtures; no trained perturbed workflow has executed.

A resumable perturbation-input suite now materializes the six one-factor and ten
combined scenes in frozen order, then seals an index of each child run, manifest,
scene and layout digest. It reuses a unique verified child after interruption,
returns an existing complete suite unchanged, and rejects ambiguous duplicates
instead of selecting the newest. Four suite fixtures pass. No model or evaluation
is invoked by preparation.

Actual prepared suite `20260911T235826-bd7f6e295f30`, seal
`e412f79eeb513c190e4955dd6cc06feb787a04c11fb3945a9e73dd48bbb4c2ab`,
contains all16ordered frozen inputs from `placement-29001` through
`combined-30010`. Independent reload verifies every child manifest, scene and
layout; a second preparation call returned the same suite without allocating a
duplicate. Its `evaluation_attempted=false` and `task_success=null` remain
unchanged. These inputs await a completed seven-checkpoint candidate.

The local release declaration is implemented but not instantiated. Once seven
completed checkpoints exist, it will freeze their workflow/execution profile,
Qwen revision and manifest, the verified16-scene suite, every package Python
source, canonical instruction, MPS devices, 1920-pixel planner camera and time
limits before release evaluation. Its schema cannot claim release or Intel success.
The one-case runner now acquires the shared top-level model lease before writing a
durable identity-addressed scene reservation, blocks automatic retry after a missing,
truncated or interrupted reservation, preserves the process and child evidence, and
independently scores a verified copy. It reports execution completion, clean process
transport and physical task success separately, plus terminal reasons, failure codes,
retry/intervention declarations, action/contact counts and timing. The aggregate
reporter reconstructs each exact request from the frozen protocol, verifies the
source-manifest-bound learned evaluation and all duplicated outcome fields, and
requires exactly one result for all sixteen cases in frozen order. Missing,
interrupted, orphaned or contradictory reservations stop aggregation. The report
retains failure/gate histograms, action/contact totals, timing p50/p95, the full
result table, observed rate and Wilson95 interval. It also reports the six diagnostic
scenes and ten combined frozen test seeds separately, including the observed 10-seed target.
Local prequalification requires16/16; final release success remains null and Intel
validation remains false. The hardened release and workflow-process group passes44
focused tests, including truncated-reservation, busy-shared-lease, exact request,
nested process/child/evaluation re-verification and source-bound scoring checks.
The aggregate cannot hide an orphaned reservation or later source change.
[Release freeze](WORKFLOW_RELEASE.md).

A host-local deployment registry now verifies and activates one complete workflow
manifest without loading models. Immutable generations bind the manifest file and
body seals, prior activation and rollback target; the current pointer is replaced
atomically. Deployed `workflow-run` resolves and reverifies this identity before
model loading, while the direct manifest path remains diagnostic. Rollback creates
a new generation only after the target's full dataset/checkpoint lineage reverifies.
Changed sources, corrupt pointers, missing history and orphaned pre-pointer records
fail closed. Twenty-nine deployment/manifest tests pass; actual rollback between
two physically evaluated candidates remains untested. [Operations](WORKFLOW_DEPLOYMENT.md).

The next seven-checkpoint manifest version now seals the per-skill execution
profile alongside checkpoint lineage: all seven ordered skill/capability IDs,
checkpoint digests, exact twice-nominal-v2 action budgets, prefix2 and no temporal
ensemble. Legacy manifests remain verifiable but cannot execute. The runtime rejects
missing, reordered or changed profiles before model loading; fresh executors inherit
the bound prefix and budget. The focused manifest/execution/executor checks pass75
tests. This is interface integrity, not learned workflow success.

Executor failures now retain a machine-readable physical classification. A
controlled no-grasp action-budget fixture produces `grasp_not_acquired`, recaptures
fresh sequence boundaries, and exhausts exactly attempts1/2/3. An injected early
physical-outcome failure produces `physical_outcome_failed`, stops at
`recovery_required`, and never replans. The focused runner/executor/supervisor group
passes92 CPU/physics fixtures. These tests validate recovery authority and taxonomy,
not learned grasp success.

Integrated workflow children now build `step-report.json` before sealing. The
typed report joins each canonical supervisor attempt to one planner dispatch,
the frozen capability/checkpoint, camera and revalidation timing, planner and ACT
inference samples, applied/rejected/partial actions, simulated duration, physical
readiness and structured failure code. Retry links, counts and timestamps fail
closed; downstream steps remain `not_attempted`. Focused report/execution checks
pass43tests; the broader non-render workflow group passes137tests. No trained
seven-step workflow has produced this evidence yet.
[Report contract](WORKFLOW_STEP_REPORT.md).

The independent dinner evaluator now has a source-bound learned-execution audit.
New workflow workers seal zero object-state edits, artificial attachments,
external object-force samples and teacher actions. Evaluation requires that exact
declaration in both worker and source records, then rechecks all seven ordered
steps, checkpoint/capability bindings, supervisor attempts, ACT inference samples,
action ownership/counts and terminal physical/readiness evidence. A workflow
cannot pass physical dinner evaluation unless this audit verifies. The focused
step/workflow/evaluator group passes65tests; the broader non-render control,
workflow, process and evaluation group passes168tests. This is audit capability;
no complete learned dinner run exists yet.

A generic teacher-prepared component evaluator is now implemented. It verifies the
nominal-v2 source and skill boundary, executes the sealed teacher prefix through
real collision/contact physics, and then permits checkpoint actions only. Component
success requires both the physical skill outcome and successor/final-parking
readiness. Its records always disclose teacher action count and cannot set full-task,
autonomous-workflow or release success. Eight focused CPU/physics tests pass,
including a real630-action MuJoCo prefix, source-forgery rejection, shared model-job
exclusion and refusal to pass physical-only results without readiness. No trained
checkpoint has been run through this evaluator yet because the active training job
owns the model slot. The direct diagnostic command remains in-process; the frozen
protocol path now uses the guarded process boundary described below.
[Evaluation contract and command](SKILL_PHYSICAL_EVALUATION.md).

The six-skill component suite is frozen before any remaining checkpoint completes:
[`experiments/six-skill-physical-evaluation-protocol-v1.json`](experiments/six-skill-physical-evaluation-protocol-v1.json),
seal `141e34751c7ae112eb15fb4214f0db65dac2e00d4002a7eb4b02cec03e8f0a25`.
It binds the training cohort and 115 package/runtime and authored-scene/SO-101 asset
files,
final-update20,000 selection,
MPS, execution prefix2, exact teacher preparation, fixed nominal-v2 scene,
twice-nominal action budgets and1,200-second wall limits. Its runner accepts only a
completed matching cohort wrapper/child, evaluates once, preserves failures and
refuses ambiguous duplicates. The focused protocol/evaluator/CLI group passes19
tests. No model or physical success is implied. This protocol replaced the earlier
unused seal before any cohort component evaluation ran.

`skill-physical-protocol-run-all` verifies all six exact completed cohort attempts
before starting the first physical evaluation, excludes only explicitly adjudicated
training failures, resumes existing clean results in frozen skill order, continues
after ordinary component failures, and stops when a process interruption requires
adjudication. It seals the suite only after all six cases exist and preserves the
teacher-prepared scope. Five CPU orchestration fixtures pass; no physical case has
run.

Operator jobs now persist as sealed immutable records with an atomic current
pointer. After a server restart, a previously active or stopping job becomes
`recovery_required` and is never relaunched automatically; verified terminal
results remain inspectable. Malformed, oversized, symlinked, orphaned or
outcome-mismatched records fail closed. The portal recognizes the recovery state.

A local submission packager now validates a clean exact Git revision, the frozen
release protocol and matching sealed release-suite evidence, a credential-free
HTTPS application URL, MP4 video, PDF slides and exact 16:9 cover before creating
any output. It copies and hashes the declared assets and evidence, preserves failed
or incomplete quality outcomes, and labels a completed bundle
`package_complete_not_submitted`. This is packaging capability only; the required
release evidence and final media do not exist yet.

The complete non-render repository gate after this checkpoint passes 1,352 tests,
with 18 documented optional skips, 9 render deselections, two dependency
deprecation warnings and 493 verified documentation links in 657.92 seconds. The
native Node 24 portal production build also passes.

The frozen runner now places each component evaluation below a separate non-daemon
guardian and spawned worker. Bounded cancellation, timeout and original-parent-loss
fixtures reaped the worker and released the shared model lease, including a worker
that ignored termination. Clean component failure remains a failed physical result;
process completion is tracked separately. The shared model lease is reserved before
an attempt is allocated and transferred continuously through the guardian to its
worker, so contention consumes no frozen attempt. A child can be returned only when
its verified process wrapper records clean worker and guardian exits, confirmed
reaps, no forced interruption and `process_complete=true`. A timed-out process is
retained and cannot be retried automatically under the frozen protocol. An
original-parent loss that leaves an unsealed process declaration also blocks
automatic retry pending explicit adjudication. The 65 protocol/process/guardian/
lease CPU fixtures pass together.

A CPU-only suite reporter now requires exactly one verified result and one clean,
child-bound process wrapper for every frozen skill. It rebinds each evaluation to
its cohort wrapper and training child before sealing a result table. Missing,
duplicate or interrupted outcomes stop without a partial report; failed components
remain failed. It never promotes teacher-prepared components to
independent dinner, autonomous-workflow or release success. Six aggregation fixtures
pass. Run it only after the six one-time component evaluations finish. The portal
recognizes cohort attempts, component evaluations, the component suite, guarded
workflow evidence, frozen local cases and their aggregate report by readable names;
`result.json` is directly inspectable. Native ARM64 Node24 type-check and production
build pass.

Before the suite ran, review found the outcome monitor's redundant default budget
still came from shorter v1 skill intervals. The executor now passes a guard one
action beyond its explicit budget, leaving the executor as the single stopping
authority and preventing premature v2 plate termination. The unused protocol was
regenerated before any outcome with all then-current transitive evaluator/control/scoring
sources pinned. Later guardian, step-report, local-release and deployment hardening
produced the current 115-source-and-asset seal before any component evaluation.
The combined executor/outcome/protocol/evaluator group passes61
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
still needed. Physical placement, mass, friction and shape generation is now
implemented by the separately frozen six-family release protocol described above;
no learned outcome on those scenes has been measured.
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

- Current stable non-render repository gate passes 1,326 tests with 18 documented
  optional skips, 9 render deselections and 2 dependency deprecation warnings in
  594.56 seconds. Ruff lint/format, 491 documentation links and README synchronization
  pass in the same run. It includes the deployment generation/pointer tamper checks
  and the refreshed 112-source physical protocol. Rendering was not rerun while
  native-MPS drawer training owns the model/render slot.
- Current repository-wide non-render regression passes:1,267tests,18optional
  skips and9render deselections in596.37seconds. It includes the frozen planner,
  scene generation, workflow release runner/aggregate and portal checks.
  Documentation481links and README synchronization pass. Log
  `.artifacts/checks-workflow-release.log`. It predates the aggregate reload
  hardening, whose focused runner/aggregate group passes9tests.
- Current repository-wide CPU regression `42144` exits0:1,181passed,18optional
  skips,9render deselections and2dependency deprecation warnings in555.75seconds.
  Documentation checks cover465links and README synchronization. Log
  `.artifacts/checks-physical-protocol.log`. The physical protocol was additionally
  reverified after its final source bundle seal. Native `/opt/homebrew/bin/node`
  portal type-check/build passes; an accidental `/usr/local/bin/node` x86 selection
  failed before build and was discarded without creating or extending a Rosetta
  environment.
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
reference and Lesson4 now include the corrective checkpoint's measured receiver-grip
failure and the distinction between low recorded-input error and closed-loop contact.
No additional mastery has
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
unsupported. The portal was not restarted. The serial native-MPS training process
is active on `plate_pick_place`; no competing model/render job may start.

Training and the default workflow use the same `.model-job.lock`. A competing
start is rejected before run allocation, the lease becomes available after the
owner exits, and nested cohort evidence borrows the continuously held top-level
lease. The cup preflight exposed an additional operational rule: an MPS coordinator
must itself run with Metal access. The failed zero-update record and its explicit
one-replacement adjudication are retained. Sixteen coordinator/adjudication CPU
fixtures pass. Full regression for the current adjudication changes remains required.
