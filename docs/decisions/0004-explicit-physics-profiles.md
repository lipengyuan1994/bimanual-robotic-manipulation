# ADR 0004: Explicit 200 Hz and 1 kHz physics profiles

Status: accepted for local simulation implementation, September 10, 2026.

The original plan starts at 200 Hz physics and 20 Hz control. That remains the
foundation, practice grasp, hand-off, drawer-only and cup profile. Thin objects
and plate impacts exposed contact oscillation or overlap beyond the unchanged
2.5 mm experiment limit in exploratory utensil/plate runs. A finer **1 kHz physics
profile with the same 20 Hz control interface** enabled specific contact skills.
This is numerical-integration evidence, not proof of real contact-material
accuracy or broader task reliability.

`DualArm(xml=..., physics_hz=1000)` explicitly opts into the finer profile. The
scene XML must also declare a 0.001-second timestep; mismatches are rejected.
Every control action advances fifty physics steps and audits each one. The
ordinary profile advances ten 0.005-second steps. Runtime mappings report the
selected rate, and changing the model timestep during an episode stops execution.
Profiles are instance-local: creating a fine-step scene cannot change another
worker or environment. Mutating a module-global rate is not an application API.

Skill scorers must match their actual physics clock. A two-second hold requires
2,000 consecutive 1 kHz samples, versus 400 at 200 Hz. A 20 Hz demonstration still
pairs one observation and action every 0.05 simulated seconds. Its scene/config
lineage must retain the physics profile; dataset sampling rate alone does not
identify the dynamics. The portal must display the recorded physics rate.

No contact tolerance, joint/actuator limit or action freshness budget is relaxed
by choosing a finer timestep. All failed coarse-step attempts remain recorded.
Higher integration rates increase computation; Intel benchmarks must measure
both the actual profile and end-to-end timing. The new profile does not establish
Intel support or full-task completion.

The supporting experiments are the [utensil feasibility record](../experiments/2026-09-10-utensil-feasibility.md)
and the [plate attempt record](../experiments/2026-09-10-tableware-feasibility.md). The core timing and
instance-isolation checks live in [test_dual_arm.py](../../tests/test_dual_arm.py).
