# Accepted product plan

Accepted by the user on 2026-09-05. This document records intended behavior;
[STATUS](STATUS.md) records what actually exists.

## Product

A workstation application accepts dinner-table instructions, operates two
simulated SO-101 arms, detects incomplete steps, and recovers or stops with an
understandable explanation. The operator watches cameras, inspects progress,
replays runs, and reproduces evaluations.

V1 includes opening a drawer, retrieving a spoon and fork, placing a plate and
cup, and a contact-based object hand-off. Pouring is deferred. No physical robot
deployment is claimed. Production means reliability within a documented
simulation operating envelope. Continue hardening after the event.

## Technical decisions

- MuJoCo, maintained SO-101 assets, overhead and wrist cameras, 200 Hz physics,
  20 Hz control, distinct simulation and wall clocks.
- Qwen3-VL-4B-Instruct interprets instructions/images and proposes supported steps.
- LeRobot ACT learns bounded manipulation skills from validated demonstrations.
- A scripted, joint-limited IK teacher generates initial demonstrations through
  physics. No teleportation, artificial grasp attachment, or evaluator leakage.
- A deterministic supervisor owns prerequisites, task state, arm assignment,
  shared-space coordination, cancellation, action validation, and at most two
  recovery attempts per failed step using new observations.
- SmolVLA is a later challenger, evaluated on the same inputs before adoption.
- Python/FastAPI plus React/TypeScript; SQLite index and filesystem artifacts;
  one active simulation per worker; versioned observations/actions/results.
- CLI operations eventually cover diagnosis, simulation, collection, training,
  evaluation, export, benchmarking, and serving. Current commands are explicitly
  listed in [setup](SETUP.md); future operations are not fake success stubs.
- Native Python 3.12 on Apple Silicon, verified MPS and CPU profiles, configurable
  local/remote jobs with common artifacts. Separate actual Intel execution.
- Intel OpenVINO CPU first, then measured iGPU support; NPU only where supported.
  Final simulation and inference remain together on Core Ultra Series 2/3.

## Timing and constraints

Preparation September 5–9; target physical foundation September 10–11, learned
workflow September 11–13, and evaluated hackathon release September 14–16.
These are planning targets, not promises of achieved results. Acceptance checks
govern readiness. See [roadmap](ROADMAP.md).

The accepted plan limits pre-clarification preparation to research, docs,
learning, and general environment work. Event-specific early-work permission,
Intel access, and final submission details remain external dependencies.

Compute budget: zero. No paid model API, training job, or machine purchase.
Intel does not provide training infrastructure according to the supplied brief.
Do not infer usable credits from general event marketing.

## Evaluation and release

Preserve train/validation/test separation, freeze final test inputs before final
checkpoint selection, retain all attempts, and independently score complete
requested workflows including stable release and hand-off. Compare teacher vs
learned execution and PyTorch vs OpenVINO without replacing failed seeds.

Internal targets (not official rubric thresholds): 10/10 demonstration seeds;
production at least 95/100 nominal and 90/100 perturbed full workflows, with
confidence intervals/intervention rates; correct termination or recovery in
every defined fault-injection case; at most two percentage points of observed
paired success loss after quantization. Keep higher precision when the gate fails.

Required evidence: repository, reproducible randomized scene, training/evaluation/
inference code, Intel benchmark, demonstration video, and architecture summary.
Rubric: manipulation 30, multimodal reasoning 20, robustness 15, Intel 20,
reproducibility 10, innovation/demonstration 5. See [requirements](REQUIREMENTS.md).

## Continuity and learning

Update status and evidence at each milestone. Record code, config, data/model,
seeds, hardware, commands, and outcomes for experiments. Keep setup, architecture,
decisions, troubleshooting, and deployment docs navigable.

English 15–20 minute lessons progress through simulation basics, frames/IK,
contacts/hand-offs, imitation learning/ACT, visual reasoning/recovery,
evaluation/randomization, and OpenVINO. Use short exercises with feedback;
record demonstrated understanding separately from coverage.

The user handles event registration, organizer clarifications, and remote Intel
access. The agent handles implementation, tests, docs, and teaching.
