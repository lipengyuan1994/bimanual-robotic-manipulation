# Evidence and evaluation protocol

## Preparation artifacts

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

Lab evidence measures actual physics/rendering, not manipulation. Doctor's MPS
probe verifies one matrix multiplication against CPU. It proves neither VLA
compatibility nor training speed. `manipulation_success` remains null.

## Future training/evaluation records

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
