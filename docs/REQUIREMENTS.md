# Requirement-to-evidence register

Source: the user-supplied [Intel online-track brief](https://drive.google.com/file/d/1xSisqTQUAFQiLOpjLZrCVTCsQi4bMCpO/view),
five pages, inspected 2026-09-05. See [source register](sources/README.md).

| ID | Requirement | Evidence / acceptance | Current state |
|---|---|---|---|
| R1 | Two simulated SO-101 arms in MuJoCo | Reproducible scene and exact asset lineage | Pending M1 |
| R2 | Multi-step dinner task with dual-arm coordination | Full task, released stable objects, contact-based hand-off | Pending M1/M2 |
| R3 | Language and raw-camera reasoning | Visual step decisions, changed instructions/scenes, context | Pending M2 |
| R4 | Training/fine-tuning with LeRobot or compatible tooling | Validated demonstrations, train code/config, learned checkpoint | Pending M2 |
| R5 | Placement/mass/friction/shape/light/background variation | Frozen randomization configuration, all attempted seeds | Pending M3 |
| R6 | Both simulation and inference on Core Ultra Series 2/3 | Host identity plus actual end-to-end run | Blocked B2 |
| R7 | OpenVINO optimization preserving behavior | Same-input baseline/export/precision comparisons | Pending Intel access |
| R8 | Reproducible repository, simulation, benchmark, video, architecture | Clean setup and complete submission manifest | Partial preparation only |

## Official 100-point rubric

| Criterion | Points | Planned evidence |
|---|---:|---|
| End-to-end task completion and bimanual manipulation | 30 | Correct sequence, coordinated arms, grasp/release/hand-off, task success |
| VLA / multimodal reasoning | 20 | Language interpretation, raw camera use, multi-step context and adaptation |
| Robustness and generalization | 15 | All six perturbation families and 10 randomized seeds |
| OpenVINO and Intel Core Ultra optimization | 20 | Device, precision, utilization, latency/throughput, task-quality comparison |
| Technical quality and reproducibility | 10 | Dependencies, scene, commands, testing, lineage and documentation |
| Innovation and technical demonstration | 5 | Understandable coordinated behavior and recovery demonstration |

Preparation checks contribute no demonstrated manipulation/reasoning/Intel score.
Points are judging weights, not scores awarded to this project.

## Internal targets

10/10 demonstration seeds; at least 95/100 nominal and 90/100 perturbed production
successes; all defined fault cases handled correctly; no more than two percentage
points of paired success loss after quantization. These targets were chosen with
the user and are not additional official hackathon rules. Report uncertainty.

## Interpretations still awaiting confirmation

Hand-off-first scope, any organizer scene/seed package, deadline/time zone, and
whether a publicly accessible live prototype is mandatory in addition to the
track's reproducible repository/video package. Generic lablab guidance mentions
a URL, pitch video and deck; do not substitute a recorded replay for a required
live application. See [organizer questions](ORGANIZER_QUESTIONS.md).
