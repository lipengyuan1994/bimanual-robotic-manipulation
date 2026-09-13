# ADR 0006: Bar entry-contact corrective boundary

Status: accepted, September 13, 2026.

The weighted bar candidate was evaluated once under a sealed MuJoCo declaration.
It failed on its first autonomous control: the left jaw made forbidden contact with
the bar while the right gripper still carried it. The maximum overlap was below the
2.5 mm limit, so this is not the earlier transport-to-placement overlap failure.

The failed declaration remains immutable and will not be retried. A new, isolated
collection protocol is bound to the exact read-only failure analysis seal. It uses
five fresh seeds (`54000` through `54004`) and replays source indices `[630,1163)`:
the learned-policy entry point through transport, placement, release, and retreat.
This avoids treating the previous `[770,1163)` data as a substitute for the missing
entry trajectory.

The contact guard remains unchanged. A later sampling declaration, training run, and
physical evaluation must each bind this fresh archive explicitly. None may reuse the
failed candidate or claim a result before its own sealed evaluation completes.
