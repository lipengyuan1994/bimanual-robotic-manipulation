# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Use `git rev-parse HEAD` for the exact checkpoint; previous pushed checkpoint is
`4434407`. Current work connects saved workflow traces to independent scoring.
[Roadmap](ROADMAP.md), [original plan](PLAN.md), [history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site, README/CI synchronization |
| M1 locally complete | One authored continuous teacher dinner scene passes contact, placement, drawer and hand-off checks |
| M2 in progress | Learned training, visual planner, skill monitors, pinned cohorts, runner and bounded recovery exist. No learned grasp or full learned dinner success |
| M3 incomplete | No frozen release suite, Intel/OpenVINO execution or final submission package |
| M4 pending | Production reliability, held-out perturbations, interruption/rollback and operational gates incomplete |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Spend remains zero. Prior-code eligibility remains unconfirmed. Physical robot
deployment is outside this release. Runtime, fixture and integrity checks do not
establish model quality or Intel compliance.

## Active training: do not restart

**Handle 61437 is live**, run `20260911T053104-2b24b508ff79`, from clean `1f7c0a0`.
Log: `.artifacts/approach-first-action-loss.log`. Actual optimizer progress was
observed beyond update 11,000; the fixed budget is 20,000 updates on native MPS,
fallback disabled. No quality result or completed checkpoint is claimed yet.

Protocol `20260911T052340-2416748543bb` changes only temporal L1 weighting: first
action 50%, remaining nine share 50%, with valid-target normalization. Dataset,
initialization, sampler, terminal learning-rate schedule and all six offline gates
remain unchanged. Only the final checkpoint may be evaluated.

Previous terminal-decay training `20260911T035236-64462d013810` completed 20,000
updates in 3,672.98s. Offline/gate runs `20260911T045418-d8a9a5277bc8` and
`20260911T045441-86b5ad13622d` passed five of six checks: first pan remains
-0.002800 rad versus teacher +0.000564 rad. No promotion or physical rollout followed.
CPU diagnosis `20260911T050712-1aacb1d9c003` motivates the new weighting but does
not establish its effectiveness. [Training](TRAINING.md), [policy evidence](POLICY_ROLLOUT.md).

No other model inference, rendering or benchmark job may share this GPU while
61437 is running. Poll the existing handle after timeouts; do not launch duplicates.

## Workflow execution and recovery

- [Pinned cohorts](WORKFLOW_MANIFEST.md) bind all seven selected policies to their
  dataset, view and successor references. No validated seven-model cohort exists.
- [Workflow runner](WORKFLOW_RUNNER.md) chains authorized steps in one simulation.
  Eligible incomplete action-budget attempts may request fresh visual assessment
  and retry at most twice. Collision, partial-action and stopped-worker failures
  remain ineligible. No reset, teacher fallback or artificial grasp is inserted.
- [Local execution command](WORKFLOW_EXECUTION.md) is implemented. It verifies
  sources and loads ACT/Qwen before creating the worker, records final supervisor
  history and preserves failed outcomes. Its timeout is cooperative; process-level
  forced termination and the live operator UI remain incomplete.
- Saved workflow traces now retain their verified scene layout for independent
  scoring. The scorer requires exact sealed paths and scene/layout digest binding;
  missing intervention evidence remains a failed condition. No object locations
  enter planner or policy inputs. The original portal remains read-only.
  Executor completion is separate from independent dinner-task success.

A new locked `.artifacts/workflow-venv` contains both training and reasoning extras.
Run `20260911T053930-398fa0529139` verifies native ARM64, all 372 compiled libraries
and ACT/Qwen class imports. No weights or inference were run in that environment.
The active `.artifacts/training-venv` was not modified.

## Visual reasoning

Actual HD Qwen run `20260911T045505-ef9d1f373348` uses overhead1920/wrist480 images,
native MPS and exact fresh recapture. Load/inference: 16.62/85.60s while CPU tests
also ran. It reports the visible cyan bar missing and requests clarification;
zero attempts/actions follow. Recognition remains unresolved. Next: a preregistered
appearance-description comparison with missing-object controls after GPU training
finishes. [Planner evidence](PLANNER_LIVE_INTEGRATION.md).

## Physical foundation and plate repair

Teacher `20260911T013229-b7184e9ba66a` completes 4,819 controls and 240,950 samples
at 1kHz, with zero forbidden contacts and final placement hold. Recording
`20260911T022644-a24a56ff004c` exports to `.artifacts/datasets/dinner-nominal-v1`;
views are `.artifacts/dinner-skill-views-v1.json`. Preserve both unchanged.
[Scene](DINNER_SCENE.md), [datasets](DATASETS.md).

The original bar boundary has six stationary observations; ten are required.
Adding holds perturbs the subsequent plate release. Destination/parking searches
and boundary repartitioning have not produced a validated replacement.

Measured prefix diagnostics retain original destinations and all live guards:

- North5 mm: `20260911T053109-6c16dbcb8104`, 2,761 controls/138,050 samples,
  zero forbidden contacts. Fixed jaw supports the tilted plate throughout all
  3,000 endpoint-hold samples; release fails.
- +5-degree tilt: `20260911T053710-429c53f79518`, same complete coverage and no
  forbidden contacts. Final jaw load 0.365 N, tilt 17.3 degrees, height +19.2 mm;
  sustained release fails. Analysis `20260911T053909-574e0b62c3ed` preserves details.

The earlier static-heuristic failure `20260911T052918-cdeba1a0c381` remains retained.
No failed diagnostic is relabeled as a repaired workflow. Read-only design
`20260911T054402-12a65c47f446` rejects plate-before-cup ordering: the cup source
blocks the path earlier. Design `20260911T054615-6660a468f379` proposes outward
and downward withdrawal after measuring load transfer between two fixed-jaw
patches. Coupled west10/down3 mm diagnostic `20260911T055847-e6acdec0f110`
then completes 2,781 controls/139,050 samples without forbidden contacts, but again
fails release: 0.369 N final jaw load, 15.0-degree tilt, height +16.7 mm and no
jaw-free hold samples. Analysis `20260911T060027-65687a2def5a` is retained.
An earlier static filter wrongly included a visual-only mesh; corrected preflight
and the original rejection are both retained. No ordering, dataset or gate changed.
[All transition evidence](SUCCESSOR_READINESS.md).

## Verification

- Clean recovery regression: **822 passed**, fourteen optional skips, nine render
  deselections, 446.40s; `.artifacts/checks-recovery-clean.log` (68236 terminal).
- Clean final ACT-loss regression: **837 passed**, eighteen optional skips, nine
  render deselections, 473.74s; `.artifacts/checks-first-action-loss-final.log`
  (1206 terminal). This precedes the new workflow entrypoint.
- Actual weighted-loss CPU suite: sixteen pass, one MPS skip, including a real
  update and checkpoint/processor/sampler/loss reload. Separate native Metal test
  passes in 11.51s with fallback disabled. Runtime evidence is not quality evidence.
- Recovery CI 34565689004 failed because its lifecycle fixture used real time and
  slow work exceeded the unchanged two-second freshness guard. The fixture now
  uses controlled time, with a separate deliberately stale-frame rejection test:
  **19 pass**, `.artifacts/workflow-logical-clock-check.log`. CI rerun is pending.
- Workflow entrypoint plus CLI: **38 pass** in the combined native environment,
  including immutable-source output confinement, real-worker lifecycle fixtures,
  late-model-output rejection and preserved final supervisor history. Log:
  `.artifacts/workflow-execution-combined-check.log`. No learned cohort was executed.
- Workflow entrypoint aggregate **8916 completed**: 876 passed, eighteen optional
  skips, nine render deselections, 476.53s;
  `.artifacts/checks-workflow-execution-final.log`.
- New scene-layout retention tests: 22 pass. Independent evaluator tests: 21 pass.
  Historical teacher rescore `20260911T055358-51d16be3e162` passes all 240,950
  samples/4,819 actions; this reuses old physics and does not certify learned control.
- Scoring aggregate **62130 completed**: 890 passed, eighteen optional skips,
  nine render deselections, 480.11s; `.artifacts/checks-workflow-scoring-final.log`.
  Ruff, formatting, 389 documentation links and README synchronization pass.
- Native camera recovery test previously passes (3.61s); no new render job runs
  alongside training. Documentation/README checks pass.

## Next executable steps

1. Verify CI after the scoring checkpoint push. Keep draft
   PR #1 unmerged and preserve its explicit model-quality limits.
2. Poll training **61437**. When sealed, run
   `.artifacts/approach-first-action-loss-offline.py` with its run ID, followed by
   `.artifacts/compare-first-action-loss-offline.py` with the offline run ID.
   All six gates must pass before the frozen conditional physical evaluation.
3. Resolve plate separation using measured contacts and a separately declared
   physical protocol, preserving every failure and original source artifacts.
4. Validate the full learned skill cohort, visual reasoning and live operator UI.

## External dependencies

Intel BM-PTL Series3 request `bimanual-sim-intel` was last Pending Review. No actual
Intel/OpenVINO validation exists. Access was requested for September10–17, with
Ubuntu requested; verify hardware identity, expiry and rendering when granted.
Organizer clarifications on assets/seeds, pouring, prior-code eligibility and
hosting remain provisional. Deadline last verified: September16, 2:30PM EDT.
No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).
