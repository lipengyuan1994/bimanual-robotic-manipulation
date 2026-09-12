# Execution profiles and Intel deployment

## Current verified scope

Local simulation and training use native macOS ARM64. Initial CPU/MPS runtime
checks are in [the preparation record](experiments/2026-09-05-preparation.md);
actual ACT optimization, checkpoint reload and measured step timings are in
[TRAINING](TRAINING.md). Learned physical rollouts still fail their grasp checks;
see [POLICY_ROLLOUT](POLICY_ROLLOUT.md).
No Intel host has been provisioned or tested; there is no compliant final demo yet.
The native dual-arm foundation is now tested locally; see [M1 evidence](experiments/2026-09-10-dual-arm-foundation.md).
Free host candidates and account-dependent next steps are in [Intel access](INTEL_ACCESS.md).

## Execution profiles

| Profile | Purpose | Status |
|---|---|---|
| Local CPU | Simulator, reference execution and model fallback | Contact skills, ACT probes and real-data pilot training/reload verified |
| Local MPS | Apple Silicon model training/inference | Actual ACT training and guarded inference measured with fallback disabled; learned grasp still fails |
| Remote training | Same dataset/config/checkpoint format on available compute | Specification only; zero spend |
| Intel CPU | OpenVINO correctness baseline and full local demo | Blocked on actual host |
| Intel iGPU | Measured latency/throughput improvement | Pending CPU baseline |
| Intel NPU | Supported component experiments | Optional, no assumed support |

Remote access should expose a private session on an actual Core Ultra Series 2/3
system. A Xeon cloud VM is not automatically the specified final target. Native
x86 execution there is distinct from forbidden Rosetta environments on this Mac.

## First Intel actions when access arrives

Record processor/model, OS, memory, graphics/NPU devices and drivers. Check the
current OpenVINO system requirements for that exact host. Establish a separately
locked Intel environment and run a minimal MuJoCo render plus an OpenVINO model
conversion/inference check before exporting the trained application.

Deploy simulator, visual reasoning and policy inference together on the Intel
machine for final evidence. Record whether each scene uses 200 Hz or 1 kHz physics with 20 Hz control; the
finer profile must be included in end-to-end performance measurements.
Transfer versioned model/data artifacts instead of
copying a Mac virtual environment. Ensure actual device selection is logged.

The event Guidelines list an application URL and the linked rules call for
interactive evaluation. Public live access needs a separately reviewed access
arrangement. The current read-only loopback portal does not satisfy live
manipulation evaluation; confirm the online track's hosting interpretation.
