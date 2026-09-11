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

Intel BM-PTL Series3 request `bimanual-sim-intel` is Rejected on the September11 signed-in check. No actual
Intel/OpenVINO validation exists. The rejection has no explanation. Defer access
work and Intel setup until local training is complete, then verify hardware
identity and rendering on the eventual target.
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
Final aggregate **58592** is active from clean `56437fa`;
`.artifacts/checks-v2-production-grace-final.log`. No code/assets changed since launch.

Intel request was rechecked in the signed-in Instances page on September11:
`bimanual-sim-intel` is **Rejected**, not Pending Review. No reason is shown in the
list, and no replacement request or support message was sent. The user has been
asked for any non-sensitive rejection-email explanation. Local work continues.

Alias inference38174 remains active, run `20260911T120355-678cc31f134e`. Its first
case recognizes the cyan target but requests `left_gripper` instead of the
instructed `right_gripper`, so that case fails. New frozen protocol
`20260911T120740-a2070b401571` tests receiver-first wording in both directions and
both present/absent scenes. Driver `.artifacts/qwen-direction-pair.py`; no inference
has run yet. It supersedes an unused draft protocol whose inherited positive-gate
text named only right; the final protocol explicitly requires the requested direction.
Wait for38174 to terminate before another MPS job. Export82810 and aggregate58592
remain active at this checkpoint; no completion is assumed from output files alone.

User steering September11: Intel rejection has no explanation. Defer Intel setup
until local training is complete, then handle it as a separate step. No further
access investigation or support request now. Zero spend and actual Intel execution
requirements remain unchanged. Continue the local dataset, policy training and
visual-planning work; the Intel rejection does not block those tasks.

Export82810 is terminal successful. Dataset v2 has full native LeRobot
image/state/action readback parity; export hash
`38a7939bca2c0465858492a24c9217673a8fe8c57fb0789ca78916062aafeab2`.
View hash `004d0bf3efa4998f1debd0e86a989fdab6ae7370e919c5c710548fdb45a449d3`.
Boundary audit **11316** is active, `.artifacts/dinner-v2-boundary-audit.log`.
Alias38174 is terminal completed: positive fails recipient, negative passes.
Direction protocol `20260911T120740-a2070b401571` is now launched; log
`.artifacts/qwen-direction-pair.log`. No production prompt change is adopted.

Boundary audit11316 is terminal **passed**, run
`20260911T121108-abc948e25b7d`, seal
`b14dfe17570b2c13528cbbaf524e309e5ce13c7f37e9bc1d5154736424f8a0e7`.
All seven physical outcomes and boundary readiness checks pass. Terminal stable
observation counts:43,16,20,64,43,43,43. No gates changed and no learned success
claimed. See SUCCESSOR_READINESS.md for exact interpretation.

Direction test **69764** remains the sole active MPS job.
First full hand-off ACT training driver `.artifacts/train-dinner-handoff-v2.py`
is prepared:20,000 updates, small ACT, chunk10/batch1, uniform skill sampling,
first-action-weighted loss, terminal learning-rate schedule, final checkpoint only.
Protocol preparation55788 verifies the completed dataset and boundary audit before
sealing; log `.artifacts/dinner-handoff-v2-training-protocol.log`. Do not start
training until69764 is terminal. This separate full-skill experiment does not
relabel failed approach-checkpoint gates. No training has started yet.
Training protocol preparation55788 completed:
`20260911T121325-10260896f896`. Launch the frozen driver with this protocol only
after direction69764 finishes, using native training-venv, fallback disabled and
explicit project-local Hugging Face caches/offline settings.

Aggregate58592 completed: **923 passed**, eighteen optional skips, nine render
deselections,661.80s. Documentation links402 and README synchronization pass.
Log `.artifacts/checks-v2-production-grace-final.log`. No remaining code test failure.
The prepared exhaustive hand-off evaluator is
`.artifacts/evaluate-dinner-handoff-v2.py`; it must run on the completed trained
checkpoint, cover all630 source observations, retain every forecast/error, and
report bounds and joint-target errors without claiming physical success.

Qwen direction69764 is terminal completed, run `20260911T121102-7f242fa1b264`:
all four frozen presence/absence and right/left recipient cases pass. This validates
only the preregistered wording on the fixed images; no general planner promotion.
Next GPU job is the prepared ACT hand-off training protocol
`20260911T121325-10260896f896`.

New `operator_jobs.py` implements one active background workflow, job-specific
stop requests, verified final evidence and explicit shutdown-timeout reporting.
Eleven CPU tests pass, including simultaneous starts, stale stop IDs, corrupted
results and failed thread startup. It is not yet wired into the API or UI; the
portal remains read-only. Job completion never claims independent task success.

ACT hand-off training **95347 is active**, run
`20260911T122319-b2ee550f005b`, started from clean `284e86f` with protocol
`20260911T121325-10260896f896`. Native MPS, fallback disabled, explicit local
Hugging Face caches,20,000 planned updates. Actual step175 is recorded; no result
or checkpoint quality is claimed. Log `.artifacts/dinner-handoff-v2-training.log`;
progress is the run's `steps.jsonl`. Do not run another GPU/model/render job alongside it.

Next independent implementation: wire the tested OperatorJobs controller into an
opt-in local API and UI, preserving read-only default, one active simulation,
job-specific cancellation, request-origin protection and no task-success claim
from process completion. No validated seven-model cohort exists yet. Run the full
regression after API/UI integration; the new controller currently has11 focused
passing tests. Latest pushed checkpoint is `c3479a3`; operator component `284e86f`
is local. Draft PR#1 remains open/unmerged; CI34598151792 was last in progress.

Operator integration checkpoint: optional `serve --operator-config` now wires
OperatorJobs into the API and a React instruction/start/stop panel. Default is
read-only. Sixteen focused API/controller tests pass; native ARM frontend build
passes. The panel polls process status and preserves job-specific stop identity;
process completion never claims table success. Live cameras/per-step UI and
browser interaction validation remain outstanding. Full regression is running
in session33890, log `.artifacts/checks-operator-integration.log`; do not claim its
result until terminal. Training95347 was re-polled live at this checkpoint, with
step2615 recorded toward20000. No second GPU job was started.

Operator setup verification: five CLI tests pass (valid opt-in/default read-only,
relative configuration path, malformed/incomplete configuration rejected before
server start, loopback bind). Temporary portal54779 on8769 displayed the unconfigured
operator message in the real browser; no start control exposed. This is only
read-only browser verification; configured interactions remain to check. Original
portal8768 was left untouched. Full regression33890 and training95347 both
confirmed live again; latest observed training step3440. No learned-quality claim.

Configured browser fixture verification (no models/physics): native Node24 with
installed Chrome, isolated evidence root `.artifacts/operator-browser-fixture/evidence`.
Start initially disabled, instruction enabled Start, active job disabled duplicate
start/edit, Stop showed `stopping`, polling reached `cancelled`. Fixture run
`20260911T123653-f9bcf0d10a98`, seal
`85f5211c6b2b409bf7ef75bd71c68bdd04d79b73fddf81bf26c7a8fc31ee5500`.
Snapshots retained in `output/playwright/operator/`. Only console error was a
missing favicon404. This does not verify learned execution or physical stopping.
Large existing run archives still delay `/api/runs` because every artifact is
hashed; operator polling is independent, but archive pagination remains next work.

Operator integration full regression33890 completed: **936 passed,18 skipped,
9 render deselected**,501.83s;403 documentation links pass and generated README
is synchronized. This full run predates the subsequent pagination changes and
five separately verified CLI tests. It is not a rendering or model-quality test.

Run-history follow-up: optional `limit`/`before` cursor pagination verifies only
selected records and preserves corrupt/failed entries. CLI/default unpaged API
behavior remains available; portal requests20 records with Older/Newest controls.
Project data now renders without waiting for run verification. No integrity cache
or unverified-success shortcut was introduced. One very large run may still be
slow; no latency target is claimed. Targeted evidence/API/controller/CLI checks
cover this delta; live browser pagination remains to verify. Training95347 remains
active; do not launch GPU evaluation until it is terminal and sealed.
