# ADR 0004: Bar transport sampling boundary

Status: accepted, September 12, 2026.

The corrective bar checkpoint failed during the learned place trajectory. Sealed
read-only localization `20260912T145555-503d496afcab` places the peak overlap at
the rejected control 214 while the source teacher is in the bar transport region.

The next candidate will not duplicate teacher recordings or relax contact guards.
It will use the existing, sealed nominal and corrective sources with a new
source-bound sampling profile. The profile must give equal total probability mass
to these two disjoint regions of the selected bar skill view:

1. transport-to-placement source indices `[770, 1070)`; and
2. all remaining selected bar-skill source indices.

Every frame remains eligible and its original dataset/source identity is retained.
The profile requires the sealed failure-localization manifest, the selected bar
view, and the corrective archive binding. It produces a fresh checkpoint and a
fresh physical-evaluation declaration; it does not retry the previous evaluation.

This decision does not claim expected physical improvement. Intel work remains
deferred until local training work completes.
