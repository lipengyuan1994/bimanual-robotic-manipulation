# Visual skill proposals with local Qwen

The planned model is now supported by `src/bimanual/planner.py`:
Qwen3-VL-4B-Instruct, pinned to upstream revision
`ebb281ec70b05090aa6165b016eac8ec08e71b17`. The
[official model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) identifies
its Apache-2.0 license and documents the Transformers image/chat interface.
The model contains 4,437,815,808 parameters. Downloading it does not establish
that it can plan manipulation reliably.

## What is implemented

`PlannerContext` contains a validated camera/joint observation, operator
instruction, completed-step history, an explicit camera profile and available skill names.
There are no exact object positions, contact forces, teacher waypoints or
independent success labels in this input. Original PNG images are checked by
hash, format, dimensions and ordered camera identity before inference.

`LocalQwenPlanner` loads only a locally verified model snapshot. It does not
download models at inference time, execute repository model code, select devices
automatically or silently fall back from MPS. CPU uses float32; the separate MPS
profile uses float16. The current response is `VisualProposal` version **2**:
an existing version-1 `SkillRequest`, explicit `target_visibility`, and a tentative
visual assessment. Parsing rejects extra fields, duplicate JSON keys, incorrect
episode/revision/observation identities, unavailable skills and invalid arguments.
Manipulation requires `target_visibility=visible`; uncertain/not-visible targets
permit only stop or clarification. An apparently-complete assessment cannot request
further manipulation. These checks do not prove that the model saw correctly.
The parser does not repair malformed output or interpret explanation text as actions.
Earlier version-1 probe records remain unchanged and cannot pass the version-2 parser.

`planner-probe` is an **offline recorded-camera diagnostic**. It verifies a sealed
demonstration run, selects its requested observation and records an actual model
response. The artifact retains source hashes, three original images, exact text
prompt, output, model manifest, timing, requested/actual device and precision.
Malformed outputs and interrupted/failed attempts remain sealed records. A valid
JSON response is not a correct decision, grasp or full-task success.

Optional `--sensor-bundle` accepts a verified [planner sensor run](PLANNER_SENSORS.md)
for a sequence-zero, time-zero observation. It changes only the overhead RGB
resolution, retaining the original policy observation and wrist images. The probe
copies and re-verifies the entire sensor run before inference, binding the exact
source manifest and observation. It never labels these reset reconstructions as
fresh live images. `PlannerContext.camera_profile` declares the dimensions; inputs
that disagree are rejected before model execution.

Every new model run records source image dimensions, the processor's actual
`image_grid_thw`, patch and merge sizes, effective image dimensions and vision-token
counts. This distinguishes a larger source PNG from the resolution actually fed
into the model. Earlier probes lack this telemetry and remain unchanged.

The planner does not yet dispatch live actions. The
[task supervisor](SUPERVISOR.md) remains the execution authority, including
prerequisites, registered capabilities, arm ownership and observation freshness.
Recorded probes are explicitly `live_dispatch_authorized: false`. Slow reasoning
must never silently relax the two-second action freshness gate; a live integration
must account for its latency before accepting any proposal.

## Reproduce locally

Use the native ARM64 runtime described in [setup](SETUP.md). The separate
reasoning environment avoids changing the active ACT training environment:

```sh
sh scripts/bootstrap-reasoning.sh
HF_HOME="$PWD/.artifacts/huggingface" .artifacts/reasoning-venv/bin/hf download \
  Qwen/Qwen3-VL-4B-Instruct \
  --revision ebb281ec70b05090aa6165b016eac8ec08e71b17 \
  --local-dir .artifacts/models/qwen3-vl-4b-instruct --max-workers 2
.artifacts/reasoning-venv/bin/python -c 'from pathlib import Path; from bimanual.planner import seal_model; seal_model(Path(".artifacts/models/qwen3-vl-4b-instruct"), "ebb281ec70b05090aa6165b016eac8ec08e71b17")'
PYTORCH_ENABLE_MPS_FALLBACK=0 .artifacts/reasoning-venv/bin/bimanual planner-probe \
  --model-root .artifacts/models/qwen3-vl-4b-instruct \
  --recording .artifacts/runs/20260910T210237-50fcd0cc7d99 \
  --frame 0 --device mps --instruction 'Pick up the practice block.'
```

The example recording is a local development artifact, not distributed in Git.
On a fresh checkout first create one with `bimanual grasp --record-demo` and use
its reported run directory. `seal_model` creates the manifest exclusively; if it
already exists, call `verify_model` instead of overwriting it. The manifest binds
the exact downloaded bytes and declared revision; it is not a signature from the
publisher. The pinned download and retained upstream README provide provenance.

The base environment tests use fixtures, not actual weights. A real model run
must be recorded separately before claiming model execution or decision quality.
The initial reasoning environment passed a native audit of 168 compiled libraries;
that audit and an import are not model inference evidence. OpenVINO and Intel
execution remain separate, unvalidated work.

## Initial actual-model evidence

The first MPS run, `20260910T223047-5e5897fcb203`, loaded the real pinned weights
and generated 373 tokens in 75.16 seconds, but copied the supplied JSON schema
instead of producing a decision. The strict parser rejected it; its raw response
and failed record remain available. That early probe captured repository provenance
at completion; the adapter now captures it at entry and copies its source file.

The compact instance-output prompt then passed the schema check in
`20260910T223500-0dd265bcb84b`: float16 on actual MPS, 14.03 seconds model loading,
25.77 seconds inference, 929 input tokens and 141 output tokens. Its proposal was
`pick`, `left`, `practice_block`. The block is visible in the source overhead view;
the explanation's reachability claim is unverified and cannot authorize execution.
This is one development case, not an accuracy or generalization evaluation. No
warm latency distribution or isolated hardware benchmark is claimed.

Both runs used the same frame-zero cameras from the nominal placement recording.
CPU run `20260910T223705-2f35cd2e4c13` also produced that nominal proposal:
float32 on actual CPU, 15.76 seconds loading and 220.85 seconds inference. It emitted
141 tokens within a 256-token cap. The two device profiles differ in precision;
these single observations do not isolate hardware performance or prove task-quality
equivalence. CPU execution works but is too slow for the existing live freshness gate.

Missing-object
recording `20260910T223829-5df5f39f2e88` retains one terminal observation and an
explicit failed manipulation outcome; no grasp was attempted. An earlier command
combining `--record-demo` and `--no-render` was rejected before any run began, since
raw recording requires cameras. Its CLI error remains in `.artifacts`.

The first missing-object Qwen run, `20260910T224238-f170359764b9`, took 27.04 seconds
on MPS and exposed a semantic failure: its explanation said the block was not
visible, but its request still said `pick`. It passed the old structural schema,
which was insufficient to reject this contradiction. No action was dispatched.
This motivated the explicit visibility field and version-2 semantic guards above.
The original result remains schema-valid **under version 1**, with no correctness
or manipulation-success claim.

The paired version-2 follow-up completed on MPS with verified seals:

| Source scene | Probe | Result |
|---|---|---|
| Block missing | `20260910T224604-d53894e8e957` | `clarify`, no arm/target/destination, `not_visible`; 27.77 s inference |
| Block present | `20260910T224701-352de484c373` | Also `clarify` and `not_visible`; 27.52 s inference |

Both fit the version-2 contract, and neither could dispatch manipulation. The
missing-object contradiction is prevented, but the nominal scene now yields a
false-negative visibility assessment. This does not establish a working planner.
The block occupies very little of the overhead frame; the home-pose wrist views
mostly show robot/table. A separate sensor-resolution diagnostic must determine
whether more actual image detail helps before changing model/prompt assumptions.
These are development cases, not a frozen accuracy or robustness suite.

## Paired higher-resolution experiment

Protocol `20260910T230553-d67de55a7054` fixed four development probes before
execution: the same two reset scenes at two overhead resolutions, unchanged
version-2 text prompt, model revision, MPS float16, instruction and wrists.
Comparison `20260911T004313-10b11352cb3c` retains all four outcomes and source
manifests. These are development cases, not a held-out accuracy estimate.

| Scene / overhead | Probe | Decision | Inference |
|---|---|---|---|
| Present / 960×540 | `20260910T230553-a210a1fec870` | Visible block, pick left | 37.50 s |
| Missing / 960×540 | `20260910T230707-f3dbfaa8db3b` | Uncertain but requests pick; guard rejects | 38.16 s |
| Present / 1920×1080 | `20260910T230849-62fb2814efea` | Visible block, pick left | 91.01 s |
| Missing / 1920×1080 | `20260910T231125-d7ab77db29e5` | Not visible, clarify, no arm/target | 95.12 s |

The 960 profile produces an effective 960×544 overhead grid with 510 vision
tokens; the 1920 profile produces 1920×1088 with 2,040 vision tokens. Both wrists
become 480×256 with 120 tokens each. Total input tokens were 1,389 and 2,919,
respectively. This confirms that the processor consumed additional image detail.
Three of the four decisions matched the predeclared case check; the rejected
contradiction remains a failure. The nominal explanations still claim reachability,
which the images and proposal do not establish.

The highest-resolution pair distinguishes these two scenes, but requires much
longer inference. These measurements include preprocessing and generation, and
other local checks/simulation ran concurrently; they are not isolated hardware
benchmarks or warm latency distributions. No model dispatched actions. No sensor
profile is promoted to live control or generalization readiness from this pair.
The next integration must resolve planner latency and fresh execution observations
explicitly, and validate dinner objects and changed scenes beyond this practice block.

## Frozen decision suite

`src/bimanual/planner_decision_suite.py` adds the evaluation boundary needed for
that next comparison. A case specification names a sealed recording, an exact
frame, optional sealed higher-resolution sensor bundle, instruction context and
accepted decision fields. `planner-suite-create` resolves those sources and
writes a protocol once, before model inference. The protocol binds the model
manifest and revision, source run and observation digests, sensor identity,
expectations, case order and the two runtime source files that interpret it.

The runner verifies and copies every frozen input before loading Qwen, loads the
model once, and evaluates every case in order. A malformed or wrong response is
retained as a failed case and does not hide later cases. Process completion and
decision quality are separate: a complete run may have failed cases. Suite
records always set `live_dispatch_authorized=false`, keep
`manipulation_success=null`, and carry no evidence claims. They measure visual
decision agreement only.

Create a JSON list whose entries follow `PlannerDecisionCaseSpec`, then use:

```sh
.venv/bin/bimanual planner-suite-create \
  --spec .artifacts/planner-cases-v1.json \
  --model-root .artifacts/models/qwen3-vl-4b-instruct \
  --destination docs/experiments/planner-decision-protocol-v1.json
.venv/bin/bimanual planner-suite-check \
  docs/experiments/planner-decision-protocol-v1.json
PYTORCH_ENABLE_MPS_FALLBACK=0 .artifacts/reasoning-venv/bin/bimanual \
  planner-suite-run docs/experiments/planner-decision-protocol-v1.json --device mps
```

The protocol is intentionally not frozen yet. Dinner skill-start frames need
higher-resolution source bundles, and rendering or Qwen inference must wait for
the active serial ACT training sequence to release the shared local job slot.
Freezing after the inputs exist prevents choosing expectations after seeing model
answers.

## Small learning exercise

Read a probe's `response.txt` and `proposal.json` alongside its three images.
Identify one directly visible claim and one claim the images cannot establish.
Then compare a schema-valid proposal with its physical outcome once execution is
integrated. A valid `pick` request proves only that the proposal fits our interface;
it does not prove that a grasp is reachable or successful. See
[lesson 05](../lessons/0005-supervision-and-recovery.html) for this distinction.
