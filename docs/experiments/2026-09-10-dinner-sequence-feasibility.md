# Continuous dinner-scene teacher feasibility — September 10, 2026

This scratch exploration starts from the exact combined layout in sealed static
probe `20260910T220035-a5c40c643f17`, described in [DINNER_SCENE](../DINNER_SCENE.md).
Both SO-101 arms, the ergonomic spoon/fork drawer, plate and physical source rack,
right-arm cup and practice hand-off bar remain present and collidable throughout.
Nothing is removed to make an isolated path pass.

The baseline replays previously recorded **teacher joint targets** in a single
live environment. It is not video concatenation, learned control, or a reset
between skills. Every 20 Hz action is applied to 1 kHz MuJoCo physics with one
episode identity and a continuous clock. Live object positions, velocities and
external forces are never edited. Transitions move real joints through checked
paths. Carried-object prediction changes only a separate scratch kinematic state;
live grasping still depends on physical contacts.

Initial order: drawer/spoon/fork, plate, mirrored right-arm cup, practice-bar
hand-off. The source action traces are:

- Utensils: `20260910T215606-949186e83a27`.
- Plate: `20260910T215707-0266b4a5e7fb`.
- Right-arm cup: `20260910T214956-40fa1c16d088`.
- Hand-off: `20260910T210623-5fab3e3b1d93`.

Their action-file hashes are recorded in each attempt. Cup and hand-off source
runs used 200 Hz physics; replaying their targets at 1 kHz is a new experiment,
not reuse of their earlier success claim. Every attempt retains the exact driver,
scene XML, action trace, compressed per-physics-step state/contact trace, result
and phase counts under `.artifacts/dinner-scene-exploration/attemptNN/`.

## Acceptance boundary

A loop reaching its end is labelled `loop_completed_unscored`; it does not claim
a successful dinner task. Independent checks must confirm the drawer opened
from closed; unsupported bilateral utensil, plate and cup carries; stable released
placements of both utensils, plate and cup after subsequent skills; and actual
donor/shared/receiver hand-off ownership. Every physics step is checked for
forbidden contacts and a 2.5 mm overlap/passive-drawer-overtravel limit.

The practice bar is still a dedicated hand-off object. A utensil hand-off remains
unestablished. All work here is a privileged precomputed teacher baseline in one
authored scene, with no robustness or learned-policy claim.

## Attempt register

| Attempt | Outcome |
|---|---|
| 01 | Drawer opening and spoon lift/carry/lowering executed with all other objects present. Spoon hold 2,000/2,000, clearance 3,000/3,000, transport 7,200/7,200 and lowering 3,000/3,000 physics samples had unsupported bilateral contact. At 52.75 s the next opening command was rejected because the moving-jaw mesh would collide with the hand-off bar. No full utensil placement or workflow success. |
| 02 | Tests a bounded 0-rad spoon release/retreat aperture, followed by opening fully only after retreat. All objects and destination coordinates remain unchanged. Result pending. |

The first failure is specifically `practice_object` versus
`left/collision_or_visual_40`, the stock moving-jaw mesh. It occurs during gripper
opening after lowering, rather than during airborne transport. This illustrates
why isolated successful skill paths cannot be assumed to compose safely.
