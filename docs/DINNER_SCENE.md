# Combining the skills into one dinner scene

Individual contact skills now exist for the drawer/utensils, plate, cup and a
practice-bar hand-off. They still execute as separate skill runs. The next
integration must preserve one continuous simulation and all previously placed
objects; concatenating independent replays is not a full dinner-table result.

An initial combined layout was checked using the existing authored scene elements:

- The ergonomic utensil drawer and its physical cabinet.
- The plate and source rack at `(.15,-.09)` metres.
- The mirrored right-arm cup at `(.136,.110)` metres.
- The practice hand-off bar centred at `(0,0)` metres.
- Both original SO-101 instances and all three cameras.

Sealed layout probe `20260910T220035-a5c40c643f17` advanced 1,000 consecutive
1 ms steps, with zero forbidden contacts and maximum overlap 0.0664 mm. All five
free objects ended below 0.01 m/s linear and 0.1 rad/s angular speed. Its local
bundle contains the combined scene/assets, exact probe script, source hashes,
contact trace and final positions/velocities. Earlier probe
`20260910T215759-120f72776ee9` checked contacts but did not explicitly gate final
object velocities; both remain recorded.

This proves only that the initial layout can be constructed and settle. It does
not prove motion clearance, reachability of the combined paths, success of any
skill in that cluttered scene, or a full workflow. In particular, the bar may
obstruct later utensil placement, and the plate skill uses a different right-arm
parking pose. These require actual guarded execution and coordination, not an
assumption that isolated successes automatically compose.

## Next integration checks

1. Extract reusable teacher sequences that act on an existing environment without
   resetting its physics, objects, clock or episode identity.
2. Use one scene-wide contact audit and explicit arm ownership. Check every park,
   approach, transport and retreat against every object already in the scene.
3. Keep observation/action timestamps continuous at 20 Hz while auditing 1 kHz
   physics. Record skill boundaries as supervisor metadata, not policy inputs.
4. Perform the physical hand-off within the same episode and preserve its ownership
   evidence. The current demonstrated object is a practice bar; a utensil hand-off
   has not been established.
5. After all movements, independently verify both utensils, plate and cup remain
   released in their intended locations, plus drawer and hand-off outcomes.
6. Record all failures, then collect demonstrations only from validated continuous
   workflows. Learned execution and visual reasoning remain separate M2 gates.

The original scope remains in [PLAN](PLAN.md), with readiness gates in
[ROADMAP](ROADMAP.md). A successful static layout must not advance either full-task
or learned-policy readiness.
