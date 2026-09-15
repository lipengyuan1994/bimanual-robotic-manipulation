# Evidence and evaluation protocol

## Run artifacts

An ignored `.artifacts/runs/<run_id>` directory contains a manifest and its files.
Each manifest records evidence kind, outcome, configuration, metrics, environment,
Git base revision/dirty state, working-source digests, and per-file SHA-256 hashes.
The manifest digest is over sorted compact JSON with `manifest_sha256` omitted.

`evidence verify` checks manifest identity/schema, all file hashes, path confinement,
and unexpected files. Existing manifests are never overwritten by the writer.
This detects accidental changes; a self-hash is not a signature or protection
against an attacker rewriting both content and hashes. Preserve/review source
history separately. Dirty-source digests identify working bytes, but do not
provide a Git commit that can be checked out.

The SQLite database is only an index. List/review reads authoritative manifests
so a stale index cannot hide an existing sealed run. A process killed before
sealing leaves an unsealed directory for inspection; it is not a completed run.
Ordinary lab exceptions seal failed attempts with an error record.

Pendulum and foundation evidence measure physics/rendering, not manipulation.
`contact_grasp_teacher` separately scores an isolated block grasp, hold and
release with privileged simulator truth. See its [acceptance envelope](CONTACT_GRASP.md).
It reports `grasp_success`; this does not establish dinner-task completion.
Doctor's MPS
probe verifies one matrix multiplication against CPU. It proves neither VLA
compatibility nor training speed. `manipulation_success` remains null.

Current contact skills also produce placement, hand-off, drawer, cup, plate and
utensil manifests. Each outcome is limited to its named authored scene and
independent acceptance checks; none sets full-task `manipulation_success` true.
The [walkthroughs](README.md) link their envelopes and all retained attempts.
Scorers reject malformed/non-finite truth records rather than letting reductions
hide invalid samples. A verified hash establishes integrity, not physical quality.

## Training records and release evaluation

Implemented [demonstration/export records](DATASETS.md) preserve synchronized
camera/joint/action transitions and source lineage. Actual [ACT training](TRAINING.md)
records dataset identity, configuration, device, steps and saved policy/processors;
reload checks verify reproducibility of model outputs. The
[learned rollouts](POLICY_ROLLOUT.md) preserve raw/accepted proposals and real
physics outcomes, including failed attempts. Existing trials use the training
scene and must not be reported as held-out success or robustness.

The following release evaluation requirements remain ahead of the current pilots.


Keep train, validation, and final test episode IDs, randomization configs, and
seeds disjoint. Prevalidate physical feasibility before freezing test scenes;
do not reject or replace seeds because a candidate policy fails them. Freeze the
test contract before selecting the release model. Use only training/validation
data for policy fitting, normalization, and quantization calibration.

Record every attempted episode and the original terminal reason. Full success
requires all requested steps, correct final zones, stable release, required
drawer state, and observed hand-off. Keep completion predicates independent of
the policy. Report collisions, interventions, retries and per-step results.

Compare teacher/learned and PyTorch/OpenVINO under identical inputs. Capture
model/data/config hashes, camera/joint order, normalization, and precision. Final
models must not read teacher poses or evaluator completion flags.

Report numerator/denominator and a 95% Wilson interval for each suite, alongside
failure classes. Ten demonstration seeds do not establish broad generalization.
The larger internal release targets remain documented in [requirements](REQUIREMENTS.md).

## Intel benchmark contract

Record CPU/system model, OS/drivers, RAM, package versions, requested/actual
inference device, precision, cold load/compile, warm p50/p95 latency, throughput,
memory, and available utilization counters. Separate model-only from end-to-end
timings and simulation time from wall time. Report unsupported devices and
fallbacks explicitly. Never infer power savings without measurement.

Before running on an eligible Core Ultra Series 2/3 host, create one JSON record
per model/device/precision configuration and validate it locally with:

```bash
.venv/bin/bimanual intel-benchmark-check path/to/intel-openvino-benchmark.json
```

The versioned `intel_openvino_benchmark_v1` contract rejects records that omit
hardware or software identity, the OpenVINO artifact and frozen-input hashes,
raw warm samples, independently recomputable
p50/p95 and throughput values, peak process/device memory, separate simulation
and wall-clock time, unavailable devices, or a visible device fallback. It also
requires the actual device to appear in the target's OpenVINO device inventory.
The contract validates evidence shape only: it performs no OpenVINO import,
conversion, inference, hardware discovery, or benchmark execution, and its
successful validation is **not** Intel compliance.

A future runner must retain the raw benchmark record with its sealed inference
and simulation artifacts. It must compare PyTorch and OpenVINO on the same
frozen inputs and report any quality difference separately. If the requested
device or precision differs from the actual value, `fallback.occurred` must be
true with a reason; otherwise validation fails rather than silently crediting
the requested configuration.
