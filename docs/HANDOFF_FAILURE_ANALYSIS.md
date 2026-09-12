# Learned hand-off continuity failure

The reproducible analysis command verifies the sealed physical wrappers, their
child runs, the complete worker action and1kHz physics logs, the shared training
checkpoint, and the packaged nominal-v2 teacher plan. It then rebuilds the donor,
shared, and receiver contact stages without loading a policy or running MuJoCo.

```sh
.venv/bin/bimanual handoff-failure-analyze \
  20260911T202840-4d435b9b3475 \
  20260911T203307-69308d4aecf0
```

Analysis run `20260911T210617-481ff0b6e8eb`, seal
`6466ef3ce767e469ef58052d4832742a9b60c2f83c5ef8ca966014fc628ceb81`,
reproduced both failures:

| Execution prefix | Highest completed stage | Loss point | Terminal right-gripper target | Error from nearest nominal target |
|---:|---|---:|---:|---:|
|2actions | donor hold | action567, physics sample18 |0.0707rad |+0.1707rad |
|5actions | shared hold | action676, physics sample30 |0.1323rad |+0.2323rad |

The nominal receiver target in the nearest `handoff/left_release` posture is
`-0.1rad`, which keeps the right gripper closed. Both terminal forecasts instead
open it and lose all practice-bar grip. The prefix-5 run first completed the
required shared-contact hold, so the next corrective data should cover receiver
close/shared hold through donor release, hold the receiver gripper closed, and
begin from varied measured approach states.

This is failure diagnosis, not a successful physical hand-off. The checkpoint
remains unpromoted. Per the agreed work order, collection and retraining for this
region wait until all six currently planned local skill trainings finish.

