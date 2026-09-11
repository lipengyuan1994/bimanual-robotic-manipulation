# Physical dinner outcomes without teacher stage labels

`dinner_contact_outcomes_v1` independently scores the frozen dinner scene. It
reads physical measurements and confirmed action records; it never awards success
because an actor says “finished” or a log contains a particular skill name.
Simulator truth stays in this evaluator and is not passed to the operating policy
or visual planner. [Per-skill termination](SKILL_EXECUTION.md) is documented separately.

The scorer requires one continuous episode, 1 kHz physics, 20 Hz confirmed
controls, and exactly 50 physical samples per applied control. Missing, extra,
partial, unconfirmed, cross-episode or noncontiguous evidence fails.

Physical requirements include:

- Ordered donor-only, shared and receiver-only airborne contacts, each sustained
  for two seconds. A dropped or supported bar cannot connect separate holds.
- A drawer initially closed, opened at least 8 cm under contact, held open and
  then released open. Contact-free opening does not qualify.
- Sustained airborne contact transport: bar 14 seconds, cup 5, plate 7, and each
  utensil 15.2, with at least 6 cm measured horizontal displacement during contact.
  These are explicit constraints of this authored-scene profile, not general
  requirements for every possible dinner-table layout.
- Released placements supported by the table, with no gripper force, low linear
  and angular speed, and the existing position/upright tolerances. Each needs a
  two-second hold. Previously accepted placements must remain undisturbed.
- A final uninterrupted two-second interval with every object placed and the
  drawer still released open.

The original `score_dinner` remains the teacher-specific reproduction audit.
The new `score_dinner_outcomes(rows, layout, metadata=..., actions=...)` accepts
arbitrary stage labels and verifies the physical events themselves. The layout
and thresholds remain frozen; it does not yet implement randomized release suites.

## Evidence and limits

Audit `20260911T033217-cd9792a67e58` verifies the supported teacher run
`20260911T013229-b7184e9ba66a` after replacing all stage labels. It passes with
4,819 confirmed actions and 240,950 physical samples. This validates the scorer
against a known scripted baseline; it is not learned-policy performance.

Nineteen tests cover missing hand-off, artificial contact-free placements, absent
release, unsupported drawer motion, disturbed placements, malformed physics,
incomplete action coverage and a final hold that is 50 samples too short.

Metadata must explicitly report zero object-state edits, artificial attachments
and external object-force samples. Such counters require trusted instrumentation
and source provenance. Contact logs alone cannot prove the absence of unlogged
state changes. The retained teacher audit identifies its counters as source-
inspected declarations; it does not pretend they were independently measured by
the new evaluator.

## Supported evaluation command

Evaluate an existing sealed run without restarting the simulator:

```sh
.venv/bin/bimanual dinner-evaluate RUN_ID
```

For the historical teacher, its linked source-inspection audit supplies the
otherwise missing instrumentation declarations:

```sh
.venv/bin/bimanual dinner-evaluate 20260911T013229-b7184e9ba66a \
  --instrumentation-run 20260911T033217-cd9792a67e58
```

The command verifies the source before and after reading, verifies any audit's
binding to the exact source manifest, and seals a new `dinner_evaluation` run.
Its artifacts include the source manifest, evaluator source and results. It
preserves declaration provenance and never manufactures missing zero counters.
Both normalized worker actions and explicitly acknowledged legacy teacher actions
are supported. Unsealed or altered inputs are rejected.

The physical scorer may stop at an incomplete action. A separate full-trace scan
therefore retains later collisions, partial controls and malformed rows. Inspect
`full_trace_diagnostics` as well as `score`; zero collisions in a confirmed prefix
do not mean zero collisions in the entire attempt. A failed source remains failed
even if its physical score passes. Exit code 0 requires both source completion
and passing physical evidence; other evaluated outcomes return 1. This command
does not certify learned execution or robustness across scenes.

The first supported-command evaluations are sealed and verified:

| Source | Evaluation | Result |
|---|---|---|
| Original teacher `20260911T013229-b7184e9ba66a` | `20260911T043031-3fe61f7bd44b` | Pass: 4,819 actions, 240,950 samples, zero forbidden contacts |
| Hold probe `20260911T041046-acd11fe83176` | `20260911T043017-446d1af42961` | Fail: 2,732 confirmed actions, one partial action, one forbidden sample in 136,644 rows |

The first uses the linked source-inspection audit shown above; the second retains
the probe's own explicitly scoped declarations. Both are existing scripted runs.
