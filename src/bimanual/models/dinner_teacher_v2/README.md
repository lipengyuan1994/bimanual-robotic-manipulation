# Repaired continuous dinner recipe v2

This recipe preserves the original scene, robot assets, destinations and scoring
thresholds. Targets come from verified run `20260911T112302-2cba6a2aa0ac` and its
independent evaluation `20260911T112722-fd2f1119487f`.

It adds ten bar-settling controls and replaces the plate withdrawal with a measured
staged release, hold, and checked return before the original drawer/utensil sequence.
All 5,049 targets are copied exactly. The final 40 controls of the return hold are labeled
`plate/settled`; this does not change any target or physics parameter.

Version 2 explicitly records path-check starting state and a restrictive no-object-
contact override for the post-release return. No object pose is replayed or attached.
The original v1 recipe and recorded dataset remain unchanged.

SO-101 asset provenance and license remain in `../robotstudio_so101`.
This is one authored teacher scene, not learned-policy or generalization evidence.
