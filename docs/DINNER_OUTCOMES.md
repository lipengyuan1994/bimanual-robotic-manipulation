# Physical dinner outcomes without teacher stage labels

`dinner_contact_outcomes_v1` independently scores the frozen dinner scene. It
reads physical measurements and confirmed action records; it never awards success
because an actor says “finished” or a log contains a particular skill name.
Simulator truth stays in this evaluator and is not passed to the operating policy
or visual planner. Automatic skill termination is a separate integration task.

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
