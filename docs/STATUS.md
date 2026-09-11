# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Use `git rev-parse HEAD` for the exact checkpoint; previous pushed checkpoint is
`6719928`. Current work packages and records the repaired v2 teacher recipe.
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

## Latest ACT training and quality gate

Training **61437 is terminal**. Run `20260911T053104-2b24b508ff79` completed
20,000 native MPS updates in 3,667.71s, fallback disabled, from clean `1f7c0a0`.
Protocol `20260911T052340-2416748543bb` changes temporal L1 weighting only: first
action 50%, remaining nine share 50%, valid-target normalization. Dataset,
initialization, sampler, terminal learning-rate schedule and all six gates stayed fixed.

Offline run `20260911T110831-7101df3ccdb6` and comparison
`20260911T110901-a43fc6ef185a` pass **five of six** gates. Launch mean tool-target
error is 0.344 mm and settled error 0.033 mm, but the first pan command remains
-0.001956 rad versus teacher +0.000564 rad. No physical rollout or promotion.
Previous terminal-decay run `20260911T035236-64462d013810` also passed five of six.
The next ACT step is to diagnose the persistent signed launch error before declaring
another controlled training experiment. [Training](TRAINING.md), [policy evidence](POLICY_ROLLOUT.md).

Qwen **50272 is terminal**. No GPU model job remains active from this session.
Full teacher trial **76771 is terminal and passed**. No model or physics job from
this session remains active. Preserve all source runs and the original dataset.

## Workflow execution and recovery

- [Pinned cohorts](WORKFLOW_MANIFEST.md) bind all seven selected policies to their
  dataset, view and successor references. No validated seven-model cohort exists.
- [Workflow runner](WORKFLOW_RUNNER.md) chains authorized steps in one simulation.
  Eligible incomplete action-budget attempts may request fresh visual assessment
  and retry at most twice. Collision, partial-action and stopped-worker failures
  remain ineligible. No reset, teacher fallback or artificial grasp is inserted.
- [Local execution command](WORKFLOW_EXECUTION.md) is implemented. It verifies
  sources and loads ACT/Qwen before creating the worker, records final supervisor
  history and preserves failed outcomes. The CLI now defaults to a spawned process
  with cooperative cancellation, bounded terminate/kill escalation and reaping.
  `--in-process` retains cooperative debugging. Parent-crash recovery, unmanaged
  subprocess trees and the live operator UI remain incomplete.
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

Actual HD Qwen run `20260911T045505-ef9d1f373348` reports the visible cyan bar
missing and requests clarification; zero actions follow. Recognition is unresolved.
Two preregistered paired replay attempts, `20260911T110859-4158aa25c243` and
`20260911T111049-12b26169fffe`, stopped before inference because historical RGB
was not bit-identical. The overhead differs in 88 channels by one intensity level;
both wrist images match. Both failed attempts remain preserved.

New protocol `20260911T111218-c75b807e19fb` freezes the last captured positive and
negative pair. Four cases use identical saved pixels per scene and unchanged
visual-decision gates; no historical exact replay is claimed. Evaluation
`20260911T111242-65da2d81e562` completes all four cases: both present cases fail,
both absent cases pass. The appearance description is not promoted.
[Planner evidence](PLANNER_LIVE_INTEGRATION.md).

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
The larger west30/south5/down10 mm trial `20260911T060903-2e2b0e5fc492` also
completes 2,781 controls/139,050 samples collision-free but fails release. Final
jaw load is 0.389 N, tilt 10.45 degrees and height +11.74 mm; no hold sample is
jaw-free. Analysis `20260911T061047-d494cfcfd579` preserves the support migration.
The next measured down2 mm / northwest24 mm sequence **passes release** in
`20260911T111745-e717fe08f3a5`: 2,901 controls/145,050 samples, zero forbidden
contacts. Analysis `20260911T112034-4540db745aa4` confirms all final 2,000 rows pass;
plate target error is 2.270 mm, with zero jaw forces and essentially flat placement.
A 120-control return route passes static checks in `20260911T112143-e4f5f6790080`.
Full continuous teacher run `20260911T112302-2cba6a2aa0ac` passes all 5,049
controls/252,450 samples, with zero forbidden contacts. Independent rescore
`20260911T112722-fd2f1119487f` confirms completion, zero partial actions and no trace
errors; learned execution remains false. A packaged recipe, new recording and
verified skill boundaries remain necessary before adopting a replacement dataset.
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
  **19 pass**, `.artifacts/workflow-logical-clock-check.log`. Workflow checkpoint
  `4434407` CI 34567398213 now passes, including rendering. Scoring checkpoint
  `852b7fa` CI 34568561533 and 34568558635 both pass.
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
- Process isolation: nineteen real spawned CPU tests pass, including ignored
  termination, kill/reap, parent interruption, corrupt child evidence and a child
  sealed as completed while a background thread hangs. Four CLI wiring tests pass.
- Actual default CLI missing-cohort run `20260911T061251-260718b9a590` returns
  failed in 0.389s, verifies its failed child and reaps it. No model is loaded.
- Process aggregate **75625 completed**: 911 passed, eighteen optional skips,
  nine render deselections, 481.95s; `.artifacts/checks-workflow-process-final.log`.
  Ruff, formatting, documentation links and README synchronization pass.
- Native camera recovery test previously passes (3.61s); no new render job runs
  alongside training. Documentation/README checks pass.

## Next executable steps

1. V2 recipe and CLI selection are implemented; 24 focused teacher tests pass.
   Baseline regression **1316 passed: 919 tests**, `.artifacts/checks-dinner-v2-final.log`.
   After a clean checkpoint, record `dinner-teacher --recipe v2 --record-demonstration`,
   then verify all seven boundaries and export separately. Preserve the v1 dataset.
2. ACT input diagnosis `20260911T111920-7fd911a11b83` finds weak joint-state
   sensitivity: +/-0.08 rad state changes shift nominal-image first pan by only
   0.000389 rad. Diagnose/train a declared representation change; no failed rollout.
3. Improve visual recognition under a new matched protocol; the appearance pair failed.
4. Verify CI after the checkpoint push. Keep draft PR #1 unmerged.
5. Validate the full learned cohort, live operator UI and remaining release gates.

## External dependencies

Intel BM-PTL Series3 request `bimanual-sim-intel` was last Pending Review. No actual
Intel/OpenVINO validation exists. Access was requested for September10–17, with
Ubuntu requested; verify hardware identity, expiry and rendering when granted.
Organizer clarifications on assets/seeds, pouring, prior-code eligibility and
hosting remain provisional. Deadline last verified: September16, 2:30PM EDT.
No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).


## Current continuation: v2 recording correction

Recording `20260911T113458-5a8697f744a0` finished **failed**, preserved unchanged.
All 5,049 controls and 15,150 images were captured; independent physical scoring
passes with zero forbidden contacts. The stage audit requires exactly 2,000
plate-settled samples, while the packaged labels supplied 3,000. Only the first
20 labels of that 60-control hold are corrected to `plate/retreat`; all targets,
guards and acceptance thresholds remain unchanged. Re-record before export.

The explicit v2 skill-view profile is implemented with pinned plan identity,
profile/count/interval consistency and mandatory independent score. Original v1
manifests remain compatible. View tests: 29 pass. Successor/training adapters:
30 pass, one optional skip. Aggregate 70584 predates the phase correction and
cannot establish the final corrected asset check. Next: finish focused correction
checks, record the corrected recipe, then export and audit all seven boundaries.
