# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Latest pushed checkpoint: `f5c3f02`. Working changes add configurable action-prefix
execution and its regression test. Draft PR#1 remains unmerged.
[Roadmap](ROADMAP.md), [accepted plan](PLAN.md), [historical evidence](STATUS_HISTORY.md).

## Readiness

| Milestone | Current evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site and README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher dinner workflow passes one authored scene |
| M2 in progress | Full hand-off ACT training completed; first physical rollout failed; planner, bounded recovery, worker isolation and operator UI implemented; no full learned dinner success |
| M3 incomplete | Frozen release suite, actual Intel/OpenVINO execution and submission package remain |
| M4 pending | Held-out reliability, parent-crash recovery, rollback, installation and support gates remain |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Spend is zero. Prior-code eligibility is unconfirmed. Physical deployment is outside
scope. Do not relabel runtime checks, fixture tests or teacher success as learned
quality, release reliability or Intel compliance.

## Active jobs and next executable actions

Current model job: **11662**, batch4 training `20260911T134059-0cebfd5a5ae1`.
At the latest check,1,718/20,000 updates were recorded. No second GPU job may
run concurrently. Regression83196 is terminal:971 passed,18 skipped,9 render deselected
(490.25s), `.artifacts/checks-history-summary.log`. The later phase-analysis
module has11 separately passing tests.

- ACT training `20260911T122319-b2ee550f005b` completed 20,000 updates on
  native MPS. Checkpoint and processor reloads pass.
- Recorded-input evaluation `20260911T131631-11ba2033068e` completed all
  630 training observations with valid bounded forecasts. This is not physical success.
- Physical baseline `20260911T131735-2cd345d50623` is verified **failed**:
  900 actions without physical completion/readiness. Preserve this result.
- Comparison protocol `20260911T133027-fbedf19e2391` freezes the same checkpoint,
  seed0 scene and 900-action budget with five actions per forecast instead of one.
  Per-action validation, cancellation and physical acceptance limits are unchanged.
  Five-action comparison `20260911T133038-335ba4618a39` failed with an
  expired forecast; session23540 is terminal. The two-second freshness limit
  remains unchanged. New protocol `20260911T133146-f568c723db05` declares a
  two-action comparison with the same checkpoint and limits. It finished as
  run `20260911T133149-1555757a5255`: failed after900 actions without physical
  completion/readiness. Session24984 is terminal; sealed evidence verifies.
  Log `.artifacts/handoff-physical-prefix2.log`. Batch4 training is now active; see its run below.
- Prefix integration regression: 100 tests passed; lint passes. Production default
  remains one action per forecast. Longer-prefix physical quality is unproven.

Next: inspect and verify the comparison's sealed result; diagnose any failure
before choosing further training. Then continue the other six skills, integrated
learned dinner workflow and held-out evaluation. Intel setup remains deferred until
local training for the planned skills is complete. Full latest regression before
this prefix change: 969 passed,18 skipped,9 render deselected.

## Physical teacher and data

Corrected recording `20260911T114540-8b3b1ff0238d` from clean106f5ed:
5,049 actions,5,050 observations,15,150 RGB images,252,450 physical samples.
Both stage and independent physical scores pass, with zero forbidden contacts.
Source seal `37ec8a70353517d668f4bc18cf8252c2067e2fe4db6b7d1060e1c43d782808ff`.
First v2 recording113458 remains failed for plate phase sample-count mismatch;
the correction changed20 phase labels only, verified by115118. V1 remains immutable.

Dataset `.artifacts/datasets/dinner-nominal-v2` passes complete LeRobot image/state/
action readback. Views `.artifacts/dinner-skill-views-v2.json` define all seven skills.
Recorded boundary audit `20260911T121108-abc948e25b7d` passes every physical outcome
and terminal readiness boundary without weakening thresholds. This is one seed0
teacher episode, not held-out data or learned success. [Data](DATASETS.md),
[scene](DINNER_SCENE.md), [skill training](SKILL_TRAINING.md).

## Model quality and unresolved evidence

The older approach ACT run053104 completed20k updates but retained a5/6 offline
gate result; no physical promotion. The completed full hand-off training run is a separate
experiment and does not erase that failure. [Training](TRAINING.md).

Qwen's receiver-first prompt run `20260911T121102-7f242fa1b264` passes four frozen
present/absent × left/right cases. Earlier visibility/direction failures remain
preserved. No production prompt promotion or broad planner/generalization success
is established. All Qwen jobs are terminal. [Planner](PLANNER_LIVE_INTEGRATION.md).

## Operator application and verification

Default portal is read-only. `serve --operator-config` enables server-owned models/
limits, one active worker, instruction entry, job-specific stop, and run history.
Foreign browser origins are rejected. Stop remains stopping until the worker is
reaped and its result verified; process completion never means physical success.
Full seven-model cohort is not yet validated. [Setup](WORKFLOW_EXECUTION.md).

Progress/camera integration publishes bounded, display-only worker
snapshots and exact existing three-camera PNGs. Hashes/dimensions/source and capture
identity are checked; invalid previews are unavailable. No browser request renders
or captures observations. Last updates may remain visible during planning/after
stop. Preview data never feeds the action validator, model inputs or task scorer.

- Operator regression33890:936 passed,18 skipped,9 render deselected (501.83s).
- Later pagination/controller/API/CLI delta:32 focused tests pass; native UI builds.
- Progress/execution/process/API:78 pass, plus2 spawned-delivery/terminal tests.
- Reader FIFO/filesystem failure checks:8 pass.
- Camera/control/progress/execution:72 pass; synthetic captures, no GPU rendering.
- Real browser fixture verifies active → stopping → cancelled and all three saved
  teacher images. Screenshot `output/playwright/operator/camera-panel.png`.
  Temporary fixture servers and browser sessions are closed; portal8768 untouched.
- Lint, formatting and403 documentation links pass. Actual learned-run camera
  display and render checks remain pending. No new clean-install physics claim.

Run history pages verify20 records at a time and retain corrupt/failed entries.
One large run can still be slow. Full CLI/unpaged API listing remains available.
The final camera regression passed964 tests; source remained unchanged during it. Preserve all failed runs.

## External dependencies and learning

Intel BM-PTL request was rejected with no explanation. Per user direction, defer
all Intel setup/access work until local training completes, then handle separately.
No paid resources or hardware purchases are authorized. Actual Intel execution
remains a release requirement. [Intel access](INTEL_ACCESS.md).

Organizer assets/seeds, prior-code eligibility and hosting details remain provisional;
no organizer message or submission has been sent. User completed lessons1–2;
lessons3–7 are available, with mastery tracked separately from exposure.
[Learning record](LEARNING.md), [organizer questions](ORGANIZER_QUESTIONS.md).

## Current regression and physical comparison

Full regression session62625 passed:970 tests,18 skipped,9 render deselected
in486.48s; log `.artifacts/checks-chunk-prefix.log`. Documentation423links and
README synchronization also pass.
The two-action comparison session24984 is terminal failed after900 actions.
Preserve all three physical attempts (one-, five-, and two-action prefixes).
Next investigate training around the pre-closure transition before a new model run.

Interim joint comparison `20260911T133455-61d8550ff348` preserves observations100/178/240/287.
Nearest teacher frames158/173/173/172 suggest approach progress followed by a
pre-closure stall. Joint similarity does not prove grasping or causality.

## Next training comparison

Protocol `20260911T134006-5dad71a35331` freezes a batch-size comparison:
ACT batch4 instead of1, same nominal handoff data, architecture, loss, seed,
20,000 updates and learning-rate schedule. Final checkpoint only; evaluate all630
recorded inputs, then preserve both prefix1 and prefix2 physical diagnostics with
900-action budgets and unchanged guards. This is development, not held-out evaluation.
Training launched as session **11662**, log `.artifacts/handoff-batch4-training.log`.
Poll the handle and verify actual MPS/device/result evidence; do not run another
GPU/model/render job concurrently. No performance or physical-quality claim yet.
Recorded-input inspection showed gripper errors concentrated near closure onset:
frame180 target0.7971rad, prediction0.6085rad, versus much smaller later errors.
Batch size is an experiment, not a proven causal fix. More scene diversity and all
remaining skills are still required. Intel work remains deferred.

Batch4 training run: `20260911T134059-0cebfd5a5ae1`; session11662 confirmed
live with113 updates recorded. Frozen evaluation protocol
`20260911T134150-ebacc86a1733` contains exact recorded-input, prefix1 and prefix2
drivers. Verify their bytes against that sealed protocol before execution.
The final20k checkpoint alone is selected, and both physical outcomes must be kept.

Portal history improvement: paginated API responses omit the potentially20,000-row
`metrics.steps` array and explicitly report the omitted field and recorded count.
All other metrics, failures and integrity status remain visible. Full unpaged API
and sealed local manifests retain the original data. This reduces response size;
full selected-run hashing still occurs and remains a possible latency cost.

History summary follow-up:7 API tests pass, including a20,000-update record that
keeps the paginated response below5KB while preserving the complete sealed and
unpaged data. The UI displays the recorded update count and links `steps.jsonl`
when available; native ARM64 TypeScript/Vite build passes. Full regression is
running as session83196, log `.artifacts/checks-history-summary.log`. Training
session11662 remains active; do not start a second GPU workload.

Verified phase-error report `20260911T134557-8d1df3e13b25` binds the recorded evaluation and
teacher seals and copies phase labels. All630frames are included. Left-close
gripper mean absolute error is0.05030rad; startup settle has the highest
all-joint phase mean (0.03160rad). These labels support diagnosis only and
never enter operating policy inputs. Earlier unbound report134536 is retained.

Reusable phase analysis: `scripts/analyze_phase_errors.py` verifies both source
seals, compares evaluation targets to teacher actions, and recomputes errors from
raw forecasts. Real-data run `20260911T134740-40a7dd56482b` completed.11 focused
tests cover coverage, invalid forecasts and nonzero skill intervals; lint and
formatting pass. This module was added after regression83196 started, so its
coverage is reported separately from that suite.

History/analysis checkpoint: full regression971passed; phase-analysis11passed;
native frontend build,423documentation links and README synchronization pass.
Training11662 remains active. Parent OS-crash recovery remains an M4 gap.

Cooperative parent-loss handling: workflow children now check the spawning
parent's process handle alongside explicit cancellation.22 CPU process tests
pass, including a real parent termination fixture. Log
`.artifacts/parent-cancellation-tests.log`. This revokes execution at cooperative
checkpoints only; hung native calls and parent-record reconstruction remain M4
gaps. No physical/model test or complete OS-crash recovery is claimed.

Parent-loss integration now exercises the actual `_child` entry point: terminate
its owner, observe cooperative cancellation, verify the sealed cancelled result,
and confirm worker return after the result pipe closes.22 tests pass in11.34s
(`.artifacts/parent-loss-integration-tests.log`). Broken result pipes no longer
raise a second reporting exception. No full native-hang crash recovery claim.

Learning reference `reference/training-evidence.html` now uses the completed
630-input evaluation and all three physical prefix attempts, with a short
self-check and explicit unknown batch4 outcome. Static site build/check passes
all12required files;423documentation links pass. No new learner mastery recorded.
Full parent-loss regression is active as76274, log `.artifacts/checks-parent-loss.log`;
training11662 remains active (latest observed update3191).

Offline wheel check `20260911T135931-14890e721519` passed:89packaged files, new modules
match source bytes, extracted-wheel imports verify both dinner asset plans
(4819/5049actions). Wheel hash `ce87232cff1e8e615cca2d060e35ba241a4cd4afa64902fbf33bb105b46240c0`.
Existing environment dependencies were used: this is not a fresh installation
or physical/render validation.

Fresh base installation `20260911T140058-01b5bd0ef785` passed offline with hashed lockfile
requirements and the wheel. Installed-package import path verified;doctor passes
ARM64 runtime,68compiled extensions,MuJoCo stepping and CPU arithmetic. No ML
extras, rendering, learned policy or Intel validation is included.

Final parent-loss regression76274 is terminal:984passed,18optional skips,9render
deselections in494.07s.423documentation links and README synchronization pass.
Training11662 remains active (latest observed4654/20,000). All three evaluation
drivers still match frozen protocol134150. No new physical success claim.
