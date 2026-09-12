# ADR 0004: Bar transport sampling boundary

Status: accepted, September 12, 2026.

The corrective bar checkpoint failed during the learned place trajectory. Sealed
read-only localization `20260912T145555-503d496afcab` places the peak overlap at
the rejected control 214 while the source teacher is in the bar transport region.

The next candidate will not duplicate existing teacher recordings or relax contact
guards. It requires a new, isolated, source-bound bar-overlap corrective collection
with fresh frozen cases and measured-state variation. The collection and its derived
sampling profile must give equal total probability mass to these two disjoint
regions of each selected corrective replay:

1. transport-to-placement source indices `[770, 1070)`; and
2. all remaining selected bar-skill source indices.

Every selected frame retains its original dataset/source identity, teacher segment,
and plan index. The profile requires the sealed failure-localization manifest, the
selected bar view, and the new corrective archive binding. It produces a fresh
checkpoint and a fresh physical-evaluation declaration; it does not retry the
previous evaluation.

This decision does not claim expected physical improvement. Intel work remains
deferred until local training work completes.
