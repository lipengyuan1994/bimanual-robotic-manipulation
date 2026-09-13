# ADR 0008: Bar margin completion correction boundary

Status: accepted, September 13, 2026.

The bar candidate evaluated under the 0.001-radian interior policy-target margin
completed all 1,900 learned controls on native MPS without the earlier measured-joint
limit failure. It nevertheless did not become successor-ready within the frozen
action budget. The sealed read-only analysis
`20260913T233014-c9f9c4de21d5`, manifest
`36e2298ebe8d853b2c0d75854dcc3ea9f39d15b5618b06c1c362463b04f94d79`, records
no forbidden contacts, zero overtravel, and 0.241965593 m target displacement.

The existing safety margin remains mandatory. This decision does not relax a joint
limit, increase an evaluation budget, or retry either consumed physical evaluation.
Instead, it freezes five fresh contact-only teacher cases in
`.artifacts/experiments/bar-margin-completion-v6-protocol.json`. The allocation uses
seeds 57000–57004 and the source interval `[630,1163)`, covering learned-policy
entry, transport, placement, release, and retreat. This creates labels for the whole
trajectory that determines successor readiness.

Every case may execute once. Each source must independently reproduce physical
teacher success before it can enter a view or local LeRobot export. Any resulting
checkpoint requires a distinct frozen evaluation declaration. Teacher collection,
training completion, component success, full dinner success, Intel compliance, and
release qualification remain separate claims.
