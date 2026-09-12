# ADR 0005: Bar-overlap successor collection window

Status: accepted, September 12, 2026.

The first bar-overlap collection protocol is preserved. Its first field case
showed that its `[770,1070)` replay stops before teacher release and settling, so
the independent teacher score remains pending even though contact overlap stayed
within the guard. That interval cannot supply a completed corrective label source.

The successor protocol will use fresh case seeds and a replay interval `[770,1163)`.
It includes transport, placement, release, and retreat through the known successful
teacher boundary. Its sampling declaration will retain a distinct emphasis region
`[770,1070)` and treat the remainder as the comparison region. Collection success
requires the independent physical teacher scorer to report success; sampling
emphasis never changes label eligibility, object contacts, or the 2.5 mm guard.

The consumed v1 cases remain immutable failures or reservations. The successor does
not retry or replace them.
