# ADR 0009: Bar completion evaluation successor

Status: accepted, September 13, 2026.

The completion-correction candidate is a new checkpoint trained from a separately
sealed archive. It cannot reuse the earlier physical-evaluation declaration, and it
cannot satisfy the old declaration's same-training-run predecessor check.

The evaluator therefore has a new `bar_transport_physical_completion_evaluation_protocol_v3`
profile. It is available only for a completed native-MPS bar checkpoint whose
sampling profile is `bar_margin_completion_sampling_v5`. It binds the exact sealed
margin evaluation failure `20260913T231721-0f277ff9c89a`, its manifest
`bedfd660f07018408543c9ff754f1ffcade9ac6ce0e4dc2307c212f8b0f04b2a`, the
0.001-radian policy-target margin, 1,900 recorded autonomous actions, and the
unmet successor-readiness reason.

This creates one fresh, one-time physical evaluation only after the new candidate
has completed and its checkpoint re-verifies. It does not retry, alter, or reinterpret
any earlier evaluation. The measured state limit remains strict, and a component pass
still does not establish the complete dinner workflow, generalization, Intel
compliance, or release qualification.
