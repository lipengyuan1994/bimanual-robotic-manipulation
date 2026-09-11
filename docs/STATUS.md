# Project status

Updated: 2026-09-11. Branch: `codex/preparation-foundation`.
Previous pushed checkpoint: `5430df7`. This checkpoint adds verified live
progress/camera integration; see Git history for its exact revision. Draft PR#1 remains unmerged.
[Roadmap](ROADMAP.md), [accepted plan](PLAN.md), [historical evidence](STATUS_HISTORY.md).

## Readiness

| Milestone | Current evidence and remaining gate |
|---|---|
| M0 complete | Native tooling, evidence portal, seven lessons, learning site and README/CI synchronization |
| M1 locally complete | Continuous contact-based teacher dinner workflow passes one authored scene |
| M2 in progress | Full hand-off ACT training active; planner, bounded recovery, worker isolation and operator UI implemented; no full learned dinner success |
| M3 incomplete | Frozen release suite, actual Intel/OpenVINO execution and submission package remain |
| M4 pending | Held-out reliability, parent-crash recovery, rollback, installation and support gates remain |

Implementation is authorized by [decision 0003](decisions/0003-event-window-implementation.md).
Spend is zero. Prior-code eligibility is unconfirmed. Physical deployment is outside
scope. Do not relabel runtime checks, fixture tests or teacher success as learned
quality, release reliability or Intel compliance.

## Active jobs and next executable actions

- **95347: ACT hand-off training**, run `20260911T122319-b2ee550f005b`,
  protocol `20260911T121325-10260896f896`, clean training source `284e86f`.
  Native MPS, fallback disabled,20,000 planned updates; step12,577 last observed.
  Log `.artifacts/dinner-handoff-v2-training.log`; progress in the run's `steps.jsonl`.
  Poll the existing handle. No final checkpoint quality or completed training claim.
- **19814: full progress regression is terminal**,956 passed,18 skipped,9 render
  deselected in500.57s; `.artifacts/checks-live-progress.log`. It predates the
  camera changes. Final camera regression22054 is now terminal:964 passed,
  18 skipped,9 render deselected in527.11s; `.artifacts/checks-camera-final.log`.
- GitHub CI for pushed5430df7: run34600233738, last observed in progress.

Only one GPU/model/render job may run at a time. Do not start evaluation/rendering
until95347 is terminal. After training finishes, verify its sealed manifest and
checkpoint binding, then run the prepared recorded-input evaluator:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HOME="$PWD/.artifacts/huggingface" \
HF_DATASETS_CACHE="$PWD/.artifacts/huggingface/datasets" \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.artifacts/training-venv/bin/python .artifacts/evaluate-dinner-handoff-v2.py \
20260911T122319-b2ee550f005b --device mps
```

The evaluator is syntax-checked, not yet executed. It examines all630 recorded
training observations with preserved forecasts/errors and no physical steps.
Then evaluate the learned hand-off in the guarded simulator; a low offline error
alone cannot authorize a success claim. Continue the remaining six trained skills,
continuous learned workflow, broader planner evaluation and held-out release gates.

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
gate result; no physical promotion. The active full hand-off run is a separate
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

Final camera regression handle: **22054**, `.artifacts/checks-camera-final.log`.
No further production source changes are planned during this check. Poll it and
training95347 rather than restarting either process. Next commit should include
the progress/camera code, focused tests, README and this consolidated handoff.

Prepared next physical diagnostic (not executed):
`.artifacts/evaluate-handoff-physical-v2.py TRAINING_RUN` in the native training
runtime with fallback disabled and project HF caches. It preloads/verifies the
handoff policy and measured successor reference, performs one dummy warm-up before
capture, then runs at most900 learned actions in the authored seed0 scene with
unchanged control/contact/readiness gates and no retry/teacher fallback. A parent
process enforces900s and kills/reaps before sealing partial evidence on timeout
or interruption. The following bar step is declared only to require the correct
handoff successor boundary; it is not executed. All outcomes remain single-skill
training-scene diagnostics, never full dinner success. Driver is syntax-checked
only; inspect/review and execute after training95347 and recorded-input evaluation
are terminal. Final camera regression22054 continues with production source unchanged.

Frozen evaluation protocol **20260911T125848-12e6816cc83b**, seal
`29feb15a3c14ca80372ce48c70092b3f112b0c8fb276d9b8fd1c75da68adc795`,
contains exact recorded/physical evaluator drivers and settings before final
checkpoint inspection. Final20k checkpoint only;630 recorded inputs, authored
seed0 physical handoff,900-action budget, unchanged contact/readiness gates,
no retries, no teacher actions. This is development data, not a frozen release suite.
Before execution compare driver hashes against this protocol; retain deviations
as a new declared protocol rather than overwriting it.
CPU watchdog harness passes real timeout, KeyboardInterrupt and missing-result
cases. Isolated fixture runs under `.artifacts/physical-driver-watchdog-fixtures`:
125811-d1a669d4cb40,125811-0b09f22d8d96,125811-69305b8e8147. Timeout/interruption
children exited-9 after kill/reap; all failure records verify. These checks do not
load ACT or MuJoCo. Physical driver additionally checks actual MPS model devices.

Draft PR#1 description now reflects pushed5430df7 (operator controls, paginated
history,936-test baseline and32-test delta). Unpushed camera/progress changes are
explicitly excluded from that PR checkpoint until their final check and commit.
GitHub CI34600233738 was still in progress on the latest check. No merge occurred.

CPU preview-read diagnostic `20260911T130137-323d8f628eca`:100 reads of the
saved three-camera fixture, median0.545ms,p95 0.936ms,max13.653ms,payload94,990bytes.
ACT training was active, so this is not an isolated benchmark. It measures only
bounded PNG validation/encoding, not model inference, rendering or Intel behavior.

Final camera checkpoint: regression22054 passed964 tests,18 optional skips,9 render
deselections;416 documentation links and README synchronization pass. Native UI
build and saved-image browser fixture pass. Training95347 remains active (last
observed step15,848/20,000). No live rendering or learned physical result is claimed.
