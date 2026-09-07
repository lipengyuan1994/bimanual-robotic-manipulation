# ADR 0002: Native development and a modular learned workflow

Status: accepted design; model/runtime execution beyond preparation is unvalidated.

Use verified Python 3.12.13 on ARM64 with an ARM-only uv interpreter store. Keep
the environment locked. The machine has Intel interpreter installations, so
generic version selection is insufficient. Development stays local/free.

The first learned policy is ACT for bounded skills. Qwen3-VL-4B-Instruct handles
language/image reasoning. A deterministic supervisor owns control semantics.
SmolVLA is a later comparison, not a silent replacement.

Reuse maintained SO-101 model assets with attribution once M1 begins. Preserve
actual joint constraints and physics contacts. Separate training-only simulator
truth from deployed observations and independent evaluator truth.

On Intel, start with OpenVINO CPU, then measured iGPU support; report actual
devices. Local MPS availability does not prove model compatibility, and macOS
OpenVINO support would not prove Intel challenge compliance.
