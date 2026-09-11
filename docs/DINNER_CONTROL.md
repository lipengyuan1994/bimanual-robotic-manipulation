# Continuous learned dinner control

Status: development integration. Training completion and checkpoint verification
are not evidence that a skill can complete its physical task. No learned dinner
capability is released. See [status](STATUS.md) for measured results.

## Checkpoint identity

The development registry ties each selected dinner skill to a sealed, completed
ACT training run, its bounded training view, dataset lineage, normalization,
checkpoint/processor artifacts and action horizon. It verifies these before
binding the policy. There is no model download or training during inspection:

```sh
.venv/bin/bimanual skill-checkpoint .artifacts/runs/TRAINING_RUN \
  --skill-id bar_place_and_return \
  --dataset .artifacts/datasets/dinner-nominal-v1
```

The report keeps `release_available` false. A one-update CPU checkpoint can prove
loading and data integration; it cannot satisfy a manipulation quality gate.

The seven views require explicit ownership:

| View | Primary arm | Auxiliary arm |
|---|---|---|
| Hand-off | Both | None |
| Bar placement and return | Right | Left |
| Cup placement | Right | None |
| Plate placement | Left | Right |
| Drawer opening | Left | Right |
| Spoon retrieval and placement | Left | None |
| Fork retrieval and placement | Left | None |

Auxiliary permission grants joint control for the whole attempt. It does not
restrict the additional arm to a particular parking trajectory. The planner
cannot add permissions. View/checkpoint mismatches must fail before execution.

## Continuous scene and observations

`DinnerControlWorker` integrates with the guarded supervisor. It owns
one dinner environment and advances it only under an active attempt. The operating
policy receives camera pixels and measured robot joint positions. Teacher targets,
phase schedules and object poses are not policy inputs. Simulator state remains
available to contact guards and independent evidence, outside inference inputs.

There is no reset between skills, no object attachment, and no inference that a
step succeeded merely because its action queue emptied. Real termination criteria
and physical evaluation remain separate from action delivery.

## Stationary handover

After a successful skill, a serial simulation worker can stop advancing physics,
render fresh images and call `dispatch_stationary`. This avoids an unowned physics
step between two owners. The new capture must:

- Be taken after the predecessor's recorded finish and within the age limit.
- Preserve episode/revision, control sequence, simulation time, joints and velocity.
- Have identical camera digests but distinct, newly written image artifacts.
- Be tied by the worker to the exact unchanged simulator state and its owned pause.

The supervisor records this transition. It cannot prove that a renderer ran from
hashes alone: the worker is responsible for actual capture and full-state checks.
Retimestamping old images is prohibited. Normal dispatch, recovery, action
freshness and physical completion retain their existing advancement requirements.
The stationary exception only connects a successful step to its successor; it
cannot retry a failed skill or claim success without further physical execution.

## Verified local checks

- Registry: 18 focused integrity/selection tests, plus actual CLI inspection of
  CPU training run `20260911T031045-ba4157987d18`.
- ACT adapter: actual CPU inference run `20260911T031612-91ae14d2402a` produces a
  finite 10-by-12 forecast from original bar-view training frame 630. This
  one-update checkpoint is an integration fixture, not a learned skill release.
- Worker: 18 tests use real MuJoCo and explicitly injected test images, covering
  control/state/model/contact guards and stationary transitions.
- Actual three-camera check `20260911T032007-745257453221` captures before/after
  one 50 ms simulated held-target step, then cancels. All six image artifacts
  and the evidence seal verify; final overhead and wrist images were inspected.
  No trained model or task-success assertion is used in this camera check.

Load `DinnerSkillPolicy` before capture and dispatch. Its verification/model
loading may exceed the observation-age window. Use `worker.bind_skill` to connect
it to the active registered capability, `worker.policy_inputs` for the exact
current capture, then `policy.predict`, `worker.offer`, and `worker.step`.
All operations belong to the same serialized worker. Capture a new observation
following every applied action. `finish` still requires trusted task termination
logic; queue exhaustion is not completion.

## Remaining integration

Checkpoint registry and physical worker verification are development gates. A
complete product still needs trained skills with measured success, validated
termination/recovery, live visual planning, a live operator UI, held-out task
outcomes, and target Intel/OpenVINO execution. The fixed authored teacher remains
the comparison baseline, not a fallback silently substituted for learned actions.

The [phase-free physical evaluator](DINNER_OUTCOMES.md) checks complete dinner
outcomes independently of the operating controller or teacher stage labels.

A [bounded skill executor](SKILL_EXECUTION.md) now connects policy forecasts to
physical outcome monitoring. Its outcome does not certify successor arm posture
or full-task success.
