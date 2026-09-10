# From a closed drawer to placed utensils

This command opens the drawer, takes out a spoon, places it on the table, then
takes out and places a fork in the **same uninterrupted simulation**:

```sh
.venv/bin/bimanual utensils
.venv/bin/bimanual utensils --missing-object fork --no-render
.venv/bin/bimanual utensils --skip-close fork --no-render
```

The fault options remove an actual object at scene construction or leave the
selected grasp open. A failed grasp must stop before claiming placement, while
preserving earlier steps and the failed attempt. The command remains a scripted
teacher with access to simulator truth; it does not understand instructions or
use a learned policy.

## What works, and under which assumptions

The named scene is `ergonomic_flush_roof_v1`. Its utensils have chunky
12 × 40 × 12 mm handles, a neck, and a spoon bowl or fork bridge/tines. These are
explicit simulation shapes, not validated commercial cutlery. The cabinet roof
is flush with the closed drawer front to provide finger clearance; the drawer
still has its physical roof, sides, floor and passive slide joint. Original
thin-shaft and overhanging-roof attempts remain in the
[full experiment record](experiments/2026-09-10-utensil-feasibility.md).

Only the original robot actuators receive commands. The drawer moves when the
fingers pull its handle; utensils move through contacts. There is no reset or
object repositioning between the spoon and fork. The left arm performs retrieval
while the right arm stays at its checked resting pose. Scratch planning predicts
a held object's relative transform; live contact checks still determine whether
it slips or collides.

The [explicit physics profile](decisions/0004-explicit-physics-profiles.md) uses
1,000 integration steps per simulated second and 20 action updates per second.
The scorer audits every physics step, including the periods between actions.
Canonical portal run `20260910T220228-82cffdf64f0b` completed 94.4 simulated
seconds and preserved 94,400 physics samples, with zero forbidden contacts and
maximum overlap of 1.380 mm. Its three-camera replay and artifact seal were checked.

Each utensil must pass a two-second unsupported bilateral grasp, its complete
transport interval, and two seconds of released table support near its declared
target. The drawer must start closed and actually open. The final scene must
retain both placed utensils; a spoon placed early and knocked away while handling
the fork must not count as success. All timestamps, failures and contact evidence
remain inspectable in the run record.

This establishes one authored scene's teacher skill. It does not establish
held-out robustness, ordinary flatware compatibility, learned execution, the
combined plate/cup/hand-off sequence, or Intel performance.

Read [the implementation](../src/bimanual/utensils.py) and
[its tests](../tests/test_utensils.py) for the exact acceptance conditions.

## Five-minute exercise

A spoon reaches its target at 60 seconds, but the arm later pushes it off the
required location while placing the fork. Should the full retrieval run pass?

**Check your answer:** no. Completing an earlier step is not enough if its
required result no longer holds at the end. The final task evaluator must check
all requested objects together. Explain this using the recorded object positions
before marking the concept as understood.
