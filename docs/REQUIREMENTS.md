# Requirement-to-evidence register

Source: the user-supplied [Intel online-track brief](https://drive.google.com/file/d/1xSisqTQUAFQiLOpjLZrCVTCsQi4bMCpO/view),
five pages, inspected 2026-09-05. See [source register](sources/README.md).

Updated against the implementation on 2026-09-11. “Implemented” below describes
code and the linked, bounded evidence; it does not mark a milestone or release
complete. Read [STATUS](STATUS.md) for the current checkpoint and
[EVIDENCE](EVIDENCE.md) for scoring, lineage and evaluation rules.

| ID | Requirement | Current evidence | Remaining acceptance |
|---|---|---|---|
| R1 | Two simulated SO-101 arms in MuJoCo | [Pinned assets, mapped joints and three cameras](DUAL_ARM_FOUNDATION.md); [runtime/mapping tests](../tests/test_dual_arm.py). Explicit 200 Hz / 1 kHz physics profiles retain 20 Hz actions. | Validate the complete moving scene and its operating envelope; foundation loading/rendering alone is insufficient. |
| R2 | Multi-step dinner task with dual-arm coordination | Contact teachers for [block placement](CONTACT_GRASP.md), [practice-bar hand-off](HANDOFF.md), [cup](CUP.md), [plate](PLATE.md), and [drawer → spoon → fork placement](UTENSILS.md). The [authored full-scene teacher](DINNER_SCENE.md) completes all seven skills without reset and retains prior placements. | Execute and independently score the same workflow with learned policies and no teacher assistance. The demonstrated hand-off object remains a practice bar. |
| R3 | Language and raw-camera reasoning | [Versioned observations, action chunks and skill requests](INTERFACES.md), local Qwen bridge, raw-camera planning session, guarded runner and supervisor/recovery lifecycle are implemented and fault-tested. [ACT rollout inputs](POLICY_ROLLOUT.md) use three RGB images and measured joints with an explicit truth allowlist. | Run the actual Qwen model on frozen instruction/scene variants and demonstrate camera-grounded decisions and recovery. Schema and injected lifecycle tests do not establish model quality. |
| R4 | Training/fine-tuning with LeRobot or compatible tooling | [Synchronized recording and verified LeRobot v3 export](DATASETS.md), [actual ACT training and saved normalization/checkpoints](TRAINING.md), and an [image/joint policy rollout](POLICY_ROLLOUT.md). | Current data/checkpoints are tiny nominal block-placement pilots. The recorded learned rollout failed physical acceptance. Collect validated task demonstrations, train the required skills and demonstrate the full learned workflow without teacher assistance. |
| R5 | Placement/mass/friction/shape/light/background variation | [Split/seed contracts](../tests/test_contracts.py) and [export leakage checks](../tests/test_dataset_export.py) reject overlap. The [six-family scene generator and frozen 10-seed allocation](SCENE_VARIANTS.md) now bind bounded placement, mass, friction, shape, lighting and background changes before evaluation. | Execute the frozen one-factor diagnostics and all ten combined learned-workflow cases, retaining failures, interventions and uncertainty. A prepared or compilable scene is not generalization evidence. |
| R6 | Both simulation and inference on Core Ultra Series 2/3 | [Access record](INTEL_ACCESS.md) records that the request was rejected without explanation; no allocated/tested host is evidenced. | After planned local training, set up a zero-cost eligible Intel host and run both MuJoCo and inference there. Local ARM64 CPU/MPS runs do not establish Intel compliance. |
| R7 | OpenVINO optimization preserving behavior | [Intel benchmark contract](EVIDENCE.md#intel-benchmark-contract) specifies devices, precision, timings and quality comparisons. | Model conversion, actual OpenVINO execution, CPU/iGPU comparisons and paired precision-quality checks remain unverified. LeRobot dataset export is not OpenVINO model export. |
| R8 | Reproducible repository, simulation, benchmark, video, architecture | [Setup](SETUP.md), [architecture](ARCHITECTURE.md), [sealed evidence/index and verification](EVIDENCE.md), [read-only portal](DEPLOYMENT.md), source/asset lineage, physical replay bundles and automated tests are implemented. The [local release workflow](WORKFLOW_RELEASE.md) can freeze a real seven-checkpoint candidate, run each of all sixteen prepared scenes once, score copied evidence independently and aggregate the complete results with a separate ten-seed metric. A [local activation registry](WORKFLOW_DEPLOYMENT.md) reverifies candidates and records atomic rollback generations. The [submission packager](SUBMISSION.md) requires a clean exact revision and verified release evidence before sealing final media. | Create the declaration after training and execute the still-unrun full-task suite, verify clean installation, exercise rollback between real candidates, then finish benchmark, video and final submission package. The learning site and isolated replays are not the dinner-task application. |

## Implementation and fault-evidence pointers

The physical success predicates live alongside their teachers:
[grasp](../src/bimanual/grasp.py), [hand-off](../src/bimanual/handoff.py),
[drawer](../src/bimanual/drawer.py), [cup](../src/bimanual/cup.py),
[plate](../src/bimanual/plate.py), and [utensils](../src/bimanual/utensils.py).
Their [grasp](../tests/test_grasp.py), [hand-off](../tests/test_handoff.py),
[drawer](../tests/test_drawer.py), [cup](../tests/test_cup.py),
[plate](../tests/test_plate.py), and [utensil](../tests/test_utensils.py) tests
exercise real contact outcomes and targeted false-completion controls. The
[tableware attempt register](experiments/2026-09-10-tableware-feasibility.md) and
[utensil record](experiments/2026-09-10-utensil-feasibility.md) disclose geometry,
contact assumptions, failed attempts and nominal limitations.

The learned-data path is implemented in [contracts](../src/bimanual/contracts.py),
[recording](../src/bimanual/demonstrations.py),
[dataset export](../src/bimanual/dataset_export.py),
[training](../src/bimanual/training.py), and
[policy rollout](../src/bimanual/policy_rollout.py). Relevant
[training tests](../tests/test_training.py) and
[rollout tests](../tests/test_policy_rollout.py) check artifact integrity,
normalization, action bounds, ownership, observation expiry and cancellation.
The implemented supervisor enforces prerequisites, per-step timeouts,
fresh-observation recovery and at most two retries. Its lifecycle and fault tests
do not substitute for physical learned-workflow outcomes; explicit failed-grasp
classification is implemented. Integrated runs now seal a fail-closed
[per-step outcome and latency report](WORKFLOW_STEP_REPORT.md); actual learned
seven-step evidence remains pending the local checkpoint cohort. The evaluator
also requires source-bound zero-intervention and learned-checkpoint provenance
before a completed workflow can pass physical scoring.

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
The current physical teachers contribute bounded evidence toward the first row;
no complete task or awarded score is claimed. Points are judging weights, not
scores awarded to this project.

## Internal targets

10/10 demonstration seeds; at least 95/100 nominal and 90/100 perturbed production
successes; all defined fault cases handled correctly; no more than two percentage
points of paired success loss after quantization. These targets were chosen with
the user and are not additional official hackathon rules. These release suites
have not passed or been established by the nominal skill runs. Freeze test inputs
before checkpoint selection, report every attempted episode and intervention, and
report confidence intervals as specified in [the evaluation protocol](EVIDENCE.md).

## Interpretations still awaiting confirmation

Hand-off-first scope, any organizer scene/seed package, and the track-specific
hosting interpretation remain open. The signed-in event page checked September 10
confirms the September 16, 2:30 PM EDT deadline and explicitly lists an application
URL, cover image, video, and slides alongside the public repository. Its linked
Rule Book specifies interactive URL evaluation, MP4 video, PDF slides, and a 16:9
PNG/JPG cover. Do not substitute the learning site or a recorded replay for the
requested interactive application. See [organizer questions](ORGANIZER_QUESTIONS.md).
