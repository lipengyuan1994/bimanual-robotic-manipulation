# Bounded dinner skill training

Status: verified data/runtime integration; physical learning remains pending. No learned dinner skill has
passed physical evaluation. See [datasets](DATASETS.md) and [training](TRAINING.md).

The full dinner recording remains one nominal training episode. Small versioned
view manifests select contiguous action intervals without duplicating the images
or inventing new scene seeds. They bind the original export, episode, controller
plan, action log and phase annotations. A failed or altered parent is ineligible.

| Skill | Parent transitions | Count |
|---|---|---:|
| Transfer bar | `[0, 630)` | 630 |
| Place bar and return arms | `[630, 1570)` | 940 |
| Pick and place cup | `[1570, 2089)` | 519 |
| Pick and place plate | `[2089, 2851)` | 762 |
| Open drawer | `[2851, 3411)` | 560 |
| Retrieve/place spoon | `[3411, 4115)` | 704 |
| Retrieve/place fork | `[4115, 4819)` | 704 |

These fixed ranges are specific to the authored scene's frozen teacher plan.
They require confirmation against the completed recording; they are not inferred
from a model's success claim. Frame `end` is the terminal observation for a view,
not an additional action.

## Sampling and action boundaries

The parent LeRobot dataset loads without automatic action-offset queries. A view
fetches only the current observation's original images/state, then constructs its
action chunk from targets within `[start, end)`. Offsets beyond the end repeat the
last in-skill action and carry an explicit padding mask. No next-skill action or
phase annotation enters the policy batch.

Sampling uses local indices but records their original parent indices and episode
identity. Numeric state/action normalization uses selected view rows; image
normalization explicitly uses the complete parent training dataset's statistics.
All data remain seed0/train, one independent nominal scene. Views cannot serve as
independent validation or test scenes.

## Interfaces

After a complete verified export, derive an external manifest:

```sh
.venv/bin/bimanual dataset-skill-views \
  --dataset .artifacts/datasets/dinner-nominal-v1 \
  --destination .artifacts/dinner-skill-views-v1.json
```

The native training environment accepts `train --skill-views <manifest>
--skill-id <id>` with uniform sampling. A separate checkpoint is required for
each skill initially: current ACT inputs are images and robot state, not task
text. Training records the view manifest, parent source identity, local/parent
sampling indices and normalization scope.

This data interface does not authorize execution. The existing approach/placement
runtime holds the right arm fixed. Cup and bimanual skill execution require an
explicit ownership-aware executor in one continuous environment, fresh action
observations, and independent physical checks before availability is advertised.

## Verified integration

The real export produced `.artifacts/dinner-skill-views-v1.json`, binding source
run `20260911T022644-a24a56ff004c` and all seven intervals. Its canonical manifest
hash is `45bf9464a68a93f04ccc23fdd7ebbe473040af40e6b6f1e6414e9e5b521487f2`.
The loader rechecks source/export integrity and preserves the original manifest
across compatible code revisions. It does not silently regenerate lineage.

Twenty-five view tests pass, including tampered source, phase, action, interval
and strict padding rejection. Adapter tests cover every skill boundary and verify
that future action lookup does not load future images. The actual native CPU
training test passes for the 940-transition bar-placement view: one ACT update,
checkpoint/processor/sampler reload, local/parent sampling identity and selected
numeric normalization scope. Log `.artifacts/skill-training-real-test.log` reports
three passing tests. This is a runtime test, not a trained skill quality result.

Full local checks pass: 510 tests, thirteen optional skips and eight rendering
deselections (`.artifacts/checks-skill-training.log`). The real CPU integration
test is recorded separately; skips are not counted as passes.

## Ownership required by the current composite views

Inspection of the actual frozen joint targets shows both arms move in
`handoff_transfer` and `bar_place_and_return`; only the right moves in
`cup_pick_place`; only the left moves in the spoon/fork views. The plate and
drawer views also move the right arm during entry parking (`plate/transition_home`,
`plate/settle`, and `utensils/transition_home`). They therefore cannot be executed
correctly under a left-only ownership mask.

The registry now supports explicit `Capability.auxiliary_arms`. Plate and drawer
need primary left plus auxiliary right; bar placement needs primary right plus
auxiliary left. The grant controls both arms for the whole attempt; it does not
restrict the auxiliary arm to parking. Planner requests retain their primary arm.
Before execution, the dinner integration must bind these registered capabilities
to their verified skill views and checkpoints, or create separately validated
parking/manipulation skill boundaries. Do not infer extra permissions from predicted actions or silently
ignore the other arm's demonstrated movements. The generic owned queue and
supervised bridge preserve the canonical attempt permissions.
