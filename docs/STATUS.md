# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Current committed checkpoint: `c429601`; previous pushed checkpoint: `6719928`.
[Roadmap](ROADMAP.md), [original plan](PLAN.md), [detailed history](STATUS_HISTORY.md).

## Readiness

| Milestone | Evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site, README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher dinner workflow passes in one authored scene |
| M2 in progress | Training, visual planner, outcome/readiness monitors and isolated workflow runner exist; no learned grasp or full learned dinner success |
| M3 incomplete | No frozen release suite, Intel/OpenVINO execution or submission package |
| M4 pending | Held-out reliability, operational recovery, rollback and support gates incomplete |

Implementation is authorized by [decision0003](decisions/0003-event-window-implementation.md).
Spend remains zero. Prior-code eligibility remains unconfirmed. Physical hardware
deployment is outside scope. Runtime checks never establish model quality or Intel compliance.

## Corrected dinner recording: passed

Clean `106f5ed` recording **`20260911T114540-8b3b1ff0238d`** completed:
5,049 actions, 5,050 observations, 15,150 RGB images and 252,450 physical samples.
Both the fixed stage audit and independent task score pass, with zero forbidden
contacts. Source seal:
`37ec8a70353517d668f4bc18cf8252c2067e2fe4db6b7d1060e1c43d782808ff`.
Session18623 is terminal. This remains an authored teacher demonstration, not learned success.
[Scene](DINNER_SCENE.md), [datasets](DATASETS.md), [skill training](SKILL_TRAINING.md).

The first v2 recording `20260911T113458-5a8697f744a0` is retained failed: physical
outcomes passed, but the plate-settled stage had 3,000 samples instead of exactly
2,000. The correction changes 20 phase labels only; targets, guards and thresholds
are unchanged. Exact comparison `20260911T115118-910bbec745e4` verifies all 5,049
targets against the successful physical source `20260911T112302-2cba6a2aa0ac`.
Original v1 recording/dataset/views remain immutable and still load successfully.

V2 views have an explicit pinned plan/profile, exact partition and mandatory
independent score. Corrected plan hash:
`0c93816e3791ac577cc3284fc8b9932ee0e34a2f067eca805ad12f72117b9231`.
Physical readiness at all seven boundaries is not yet verified.

## Active processes and next executable actions

- **6150: native LeRobot export**, `.artifacts/dinner-v2-export.log`.
  Driver `.artifacts/export-dinner-v2.py` checks the successful source, exports to
  `.artifacts/datasets/dinner-nominal-v2`, performs full image/state/action readback,
  then creates and reloads `.artifacts/dinner-skill-views-v2.json`.
  Poll this handle; do not restart or overwrite partial output.
- **60454: native MPS Qwen description diagnostic**, fallback disabled.
  Protocol `20260911T114805-29483c134fad`; exact frozen positive/negative images,
  pinned weights, neutral descriptions instead of structured skill proposals.
  Log `.artifacts/qwen-description-diagnosis.log`. No action authority or promotion.
- **22860: fixed-snapshot full checks** from `c429601`,
  `.artifacts/checks-v2-corrected-snapshot.log`. No code/assets changed since launch.

After export succeeds, run `.artifacts/audit-dinner-v2-boundaries.py`. It verifies
new v2 references and replays recorded physical/observation evidence through the
unchanged outcome/readiness monitors. Require ten consecutive qualifying
observations at each actual terminal boundary, including final parking. Clock is
replayed from capture timestamps; no live freshness or learned reliability claim.

Then finish verification, update evidence/README, push the checkpoint, and update
draft PR#1 without merging. Continue ACT and Qwen quality work, learned cohort,
live operator controls and release gates. No seven-policy cohort is validated.

## Learned-model quality

ACT first-action-weighted run `20260911T053104-2b24b508ff79` completed 20,000 MPS
updates. Offline comparison `20260911T110901-a43fc6ef185a` passes **five of six**
gates; first pan remains -0.001956 rad versus teacher +0.000564 rad. No physical
rollout or promotion. Input diagnosis `20260911T111920-7fd911a11b83` shows weak
joint-state sensitivity under crossed inputs; it is not a causal/physical result.
Next: declare and evaluate a representation change against unchanged quality gates.
[Training](TRAINING.md), [policy evidence](POLICY_ROLLOUT.md).

Qwen frozen paired evaluation `20260911T111242-65da2d81e562`: both present-object
cases fail and both absent-object cases pass. Adding the cyan-bar appearance
phrase did not repair recognition. Earlier exact historical pixel replay attempts
failed before inference and remain preserved. Current description diagnostic
separates image recognition from skill-prompt demands.
[Planner evidence](PLANNER_LIVE_INTEGRATION.md).

## Application and verification

[Workflow execution](WORKFLOW_EXECUTION.md) verifies all seven models and Qwen
before starting one simulation worker. It retains action/observation evidence,
bounded recovery and independent evaluation. The default spawned process supports
cooperative cancellation then terminate/kill/reap. Parent-crash recovery and the
live operator UI remain incomplete; the current portal is read-only.

- Recipe baseline: 919 pass, eighteen optional skips, nine render deselections;
  `.artifacts/checks-dinner-v2-final.log`.
- Corrected teacher/view tests: 53 pass in13.63s;
  `.artifacts/v2-phase-correction-tests.log`.
- Successor/training adapter checks: 30 pass, one optional real-training skip.
- Aggregate70584 ended with922 pass/one failure because assets changed after its
  old hash was imported. It is superseded by active fixed-snapshot22860.
- Corrected wheel builds offline; packaged digests/counts and external-directory
  loading pass. No new clean-install physics claim.
- Earlier process-isolation regression:911 pass; actual real-child cancellation,
  escalation and reap tests are recorded in the history. No hung GPU claim.

## External dependencies

Intel BM-PTL Series3 request `bimanual-sim-intel` was last Pending Review. No actual
Intel/OpenVINO validation exists. Verify identity, expiry and rendering when granted.
Organizer details on assets/seeds, pouring, prior-code eligibility and hosting
remain provisional. Deadline last verified: September16, 2:30PM EDT.
No organizer message or hackathon submission has been sent.
[Intel access](INTEL_ACCESS.md), [questions](ORGANIZER_QUESTIONS.md).

## Latest continuation

Export6150 is terminal failed: LeRobot's readback requested a restricted default
Hugging Face dataset cache. Failed output is preserved at
`.artifacts/datasets/dinner-nominal-v2-export-failed-cache`. Retry **82810** uses
explicit project-local `HF_HOME`/`HF_DATASETS_CACHE`, offline flags and a fresh v2
destination; log `.artifacts/dinner-v2-export-retry.log`. Do not overwrite it.

Qwen60454 is terminal completed, run `20260911T115608-34d5fb7f9763`: positive
image describes a cyan beam but rejects the word bar; negative describes only the
small cyan drawer part. Neither output is truncated. Alias protocol
`20260911T115919-698f78cadeac` tests bar/beam/strip terminology with unchanged
presence/absence decision gates. No deployment promotion or actions.

Fixed-snapshot22860 is terminal:922 pass/one failure. Cooperative cancellation
used a test-only150ms grace, shorter than production2s; the child sealed but was
forced during shutdown under concurrent load. Only that test now uses the
production default. Forced-stop test deadlines and runtime code remain unchanged.
All19 process tests pass in14.84s; `.artifacts/process-production-grace-tests.log`.
A final aggregate is still required after the test adjustment.
Alias inference **38174** is active; log `.artifacts/qwen-alias-pair.log`.
Only this job uses MPS. Export82810 uses CPU. Timings are not isolated benchmarks.
