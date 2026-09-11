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

## Saved learned-workflow records

`dinner-evaluate` also selects the exact recorded worker paths for a sealed
`dinner_workflow_execution` run: `worker/physics.jsonl`, `worker/actions.jsonl`
and `worker/layout.json`, with `worker/scene.xml` required for scene binding.
It never searches alternate directories for a more
favorable trace. New workers retain the authored layout only after verifying its
digest and scene binding. Layout coordinates are evaluation artifacts and are
not planner or policy inputs.

The evaluation records its selected paths, scans partial/malformed traces and
preserves the source terminal outcome. A clarification, cancellation or failed
run cannot become a successful evaluation. Missing files or intervention metadata
remain failures; zero interventions are never inferred from a quiet trace.
A supplied instrumentation audit must bind the exact source manifest as before.
New workflow workers seal a versioned zero-intervention declaration in both
`worker/worker.json` and the source manifest. The evaluator independently joins
that declaration with the frozen execution profile, final supervisor state,
`step-report.json`, checkpoint identities and every action's attempt ownership.
Only a complete, consistent seven-step source sets
`learned_execution_verified: true`; missing or contradictory evidence keeps it
false and prevents a workflow evaluation from passing. One physical pass still
does not establish generalization or release readiness.

Learning checkpoint: suppose all seven skills report completion, but the plate
slides out of its target during the final hold. The workflow finished, yet the
physical task failed. Conversely, finding objects already near their targets is
not enough: the trace must also prove the required contact transport and hand-off.
Ask which recorded observation establishes each claim before calling a run a
success. Reading this explanation is not recorded as demonstrated mastery.

Historical baseline rescore `20260911T055358-51d16be3e162` preserves all 240,950
physics samples and 4,819 confirmed actions, with zero forbidden contacts or
partial actions. It passes independent physical scoring and explicitly retains
`learned_execution_verified: false`. This is a rescore of existing evidence,
not a new physical run. Workflow scene/layout binding tests additionally reject
missing sealed scenes and mismatched layout digests.


Repaired continuous teacher `20260911T112302-2cba6a2aa0ac` passes supported rescore
`20260911T112722-fd2f1119487f`: 5,049 confirmed controls, 252,450 physics samples,
zero forbidden samples, zero partial actions and no trace errors. Its staged
plate release, validated return and resumed drawer/utensil sequence all satisfy
the unchanged authored-scene profile. Instrumentation remains an explicitly
source-inspected declaration. Learned execution is still unverified.
