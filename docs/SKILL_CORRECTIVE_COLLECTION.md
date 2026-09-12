# Six-skill corrective teacher collection

This collector consumes one case from the sealed
[six-skill corrective protocol](experiments/six-skill-corrective-collection-protocol-v1.json).
It runs only a privileged scripted teacher in the real MuJoCo `DinnerEnvironment`.
It does not load a learned policy, manipulate object state directly, attach objects,
or create a training dataset.

Each source records three synchronized parts through `DemonstrationRecorder`:

1. the contact-checked teacher prefix that reaches the component’s starting state;
2. one bounded measured-joint probe and exact measured-state recovery command; and
3. the frozen source-plan replay interval.

All recorded actions are initially `training_eligible: false`. Acquisition has no
candidate replay label. A later independent source validator must verify the physical
trace and choose any replay labels before retraining. A completed collection is teacher
evidence only; it is not learned skill success.

A case identity is `family-seed`. The five approach/contact seeds rotate in their frozen
order across cup, plate, fork, cup, plate; other families each use their sole skill.
A reservation is created before physics starts. Failed and interrupted reservations stay
consumed, and rerunning the same exact request returns its verified manifest.

```bash
.venv/bin/bimanual skill-corrective-protocol-check \
  docs/experiments/six-skill-corrective-collection-protocol-v1.json
.venv/bin/bimanual skill-corrective-run \
  docs/experiments/six-skill-corrective-collection-protocol-v1.json \
  bar_contact_avoidance-51000
```

Run each of the twenty cases at most once, preserve every outcome, and do not begin
local retraining until a separate validation/export boundary exists.
