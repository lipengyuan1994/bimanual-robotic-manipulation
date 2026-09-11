# Current project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Use `git rev-parse HEAD` for the current checkpoint. The previous pushed checkpoint
is `b793460`; this checkpoint adds verified workflow-cohort integration.
[Roadmap](ROADMAP.md), [original plan](PLAN.md),
[historical status and evidence](STATUS_HISTORY.md).

## Readiness

| Milestone | Current evidence |
|---|---|
| M0 complete | Native environment, evidence, read-only portal, seven lessons, learning site and README/CI synchronization |
| M1 locally complete | One continuous scripted dinner scene passes contact, placement, drawer and hand-off checks with three-camera replay |
| M2 in progress | ACT and Qwen run locally; supervisor, guarded control, skill monitors, successor gates, checkpoint cohorts and serialized workflow exist. No learned grasp or full learned dinner success. Automatic recovery incomplete |
| M3 incomplete | No frozen release suite, Intel/OpenVINO run or final submission package |
| M4 pending | Production reliability, held-out perturbations, interruption/rollback and operational gates incomplete |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Prior-code eligibility remains unconfirmed. Spend is zero. Physical hardware
deployment is outside this simulation release. Do not equate a passing runtime,
integrity check, synthetic fixture or teacher episode with learned task quality.

## Latest learned-model results

**ACT training is finished; no training job is active.** Terminal-decay run
`20260911T035236-64462d013810` completed 20,000 native MPS updates in 3,672.98
seconds from clean `9ca38d1`. Its checkpoint, processor, sampler and seal verify.
Handle 27780 is terminal; do not restart it.

Final offline evaluation `20260911T045418-d8a9a5277bc8` and frozen comparison
`20260911T045441-86b5ad13622d` pass five of six gates. Launch tool error is
0.375 mm and settled error 0.068 mm, but first pan remains -0.002800 rad versus
+0.000564 rad. **The candidate is not promoted; no physical rollout follows.**
The earlier fixed-rate 20,000-update run also failed this gate. Diagnose input/
target representation and persistent launch bias before another training change.
[Policy evidence and earlier physical failures](POLICY_ROLLOUT.md).

**Actual HD Qwen integration completes but recognition still fails.** Run
`20260911T045505-ef9d1f373348` uses live overhead1920/wrist480 cameras, native MPS
and exact fresh recapture. Load/inference are 16.62/85.60 seconds, with a CPU test
suite running concurrently. Qwen reports the bar not visible and requests
clarification; zero attempts/actions/physics steps follow. Human inspection sees
the cyan bar in the overhead image. A paired appearance-description and missing-
object comparison is next, not an inference that the model now recognizes it.
[Live planner details](PLANNER_LIVE_INTEGRATION.md).

## Current implementation and gaps

- [Pinned workflow cohorts](WORKFLOW_MANIFEST.md) verify all seven selected skills,
  dataset/view lineage and measured successor references. `workflow-create` and
  `workflow-check` do not imply model quality. No validated seven-model cohort exists.
- [Serialized workflow runner](WORKFLOW_RUNNER.md) prepares executors before
  planning capture, chains successful steps in the same simulation and preserves
  cancellation, replacement and persistence failures. It does not reset the scene.
- The executor's incorrect comparison of an export file hash to its canonical
  body seal is fixed with a sealed synthetic-source regression. Loaded policies
  are checked against their pinned bindings and cannot be shared by two cohorts
  or workers; factories recheck ownership and binding before execution.
- **Owned failed-step recovery remains missing.** The runner reports
  `recovery_required`; it does not invent unowned motion or reset the retry budget.
  The supervisor's limit remains at most two retries. Current stationary recapture
  supports successful boundaries only.
- The portal remains a read-only evidence/learning application, not the finished
  live operator UI. End-to-end learned execution and full-task scoring still need
  integration and actual quality validation.

## Physical baseline and next repair

The clean teacher `20260911T013229-b7184e9ba66a` completes 4,819 controls and
240,950 samples at 1 kHz, with zero forbidden contacts and a two-second final
placement hold. This is one authored scene. Full-rate recording
`20260911T022644-a24a56ff004c` exports to
`.artifacts/datasets/dinner-nominal-v1`; views are
`.artifacts/dinner-skill-views-v1.json`. Preserve both unchanged.
[Scene](DINNER_SCENE.md), [datasets](DATASETS.md), [skill training](SKILL_TRAINING.md).

The original bar boundary has only six qualifying settled observations. Adding
10 hold controls fails later on a plate/cabinet collision. Static destination,
arm-parking, cup-relocation and timed-return searches all fail their tested
candidates; none proceeds to physics. Repartitioning existing controls at
1574/1580/1660/1670 also lacks the ten stationary observations. No new skill-view
profile, dataset or scene has been adopted.

Release diagnosis `20260911T045528-4a0b37e4eba3` and design note
`20260911T045721-41f7350bb2c3` show that the fixed jaw still supports the plate
after opening. The mostly westward withdrawal intermittently drags it. Next:
preregister and preflight a separating movement/controlled tilt before the long
withdrawal, retaining the original destination and all contact/placement gates.
No proposed separating path is validated yet. [All repair evidence](SUCCESSOR_READINESS.md).

`dinner-evaluate` independently reproduces the baseline pass in
`20260911T043031-3fe61f7bd44b` and retains the failed hold run in
`20260911T043017-446d1af42961`, including its partial-action collision.
It preserves instrumentation declarations and failed source outcomes; it never
manufactures missing zero counters. [Evaluation command](DINNER_OUTCOMES.md).

## Verification and process handoff

- First integration regression: 807 passed, fourteen optional skips, eight render
  deselections in 450.24 seconds. A subsequent policy-ownership correction requires
  the final run below; do not treat the earlier suite as verification of that fix.
- Final base check passed: **808 tests**, fourteen optional skips and eight render
  deselections, 446.95 seconds. Handle 48189 is terminal; log
  `.artifacts/checks-workflow-cohort-final.log`. Ruff, formatting, documentation
  links and README synchronization pass.
- All eight actual native rendering tests passed separately in 72.45 seconds,
  `.artifacts/render-workflow-cohort.log`. No rendering overlapped ACT training.
- ACT training 27780, final offline inference 68644 and HD Qwen 56295 are terminal.
  No model job is active. All newly cited experiment seals verify.
- Previous checkpoint [b793460 CI](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/actions/runs/34562948517)
  passed. New workflow checkpoint CI is not yet claimed. The [draft PR](https://github.com/lipengyuan1994/bimanual-robotic-manipulation/pull/1)
  remains unmerged.

Next executable work:

1. Build a separately recorded plate-jaw separation trial from the diagnosis;
   require complete preflight and unchanged full physical gates before adoption.
2. Diagnose the final ACT launch predictions, then preregister a justified data or
   representation change. Preserve both failed 20,000-update experiments.
3. Compare visible-object descriptions against missing-object controls for Qwen.
4. Implement a genuinely owned recovery boundary before enabling automatic retries.
5. Train/validate the full skill cohort and connect the live operator application.

## External dependencies

| ID | Needed | Effect |
|---|---|---|
| B2 | Free Core Ultra Series 2/3 access | Last checked BM-PTL request Pending Review; no actual Intel validation |
| B3 | Remaining organizer clarifications | Assets/seeds, pouring scope, prior-code eligibility and hosting interpretation remain provisional |

The user requested `bimanual-sim-intel`, BM-PTL Series 3, September 10–17; catalog
choices offered Windows 11 and Ubuntu was requested. Verify host identity,
expiry, rendering and OpenVINO after access is granted. Deadline last verified:
September 16, 2:30 PM EDT. No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).
