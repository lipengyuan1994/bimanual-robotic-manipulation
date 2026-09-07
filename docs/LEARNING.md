# Learning alongside implementation

Your [mission](../MISSION.md) and [starting point](../learning-records/0001-starting-point.md)
guide the sequence. Lessons are in English, short, and built around one observable
win. Ask the agent follow-up questions whenever an explanation is unclear.

The static [public learning site](https://lipengyuan1994.github.io/bimanual-robotic-manipulation/)
is deployed from `main` through GitHub Pages. It includes only the educational
material and static client-side interactions; it does not expose the local control
portal, simulator artifacts, or any control endpoint.

| Stage | Lesson / exercise | Availability |
|---|---|---|
| Preparation | [Observe, act, and step time](../lessons/0001-observe-act-step.html): inspect an actual trajectory | Ready |
| Preparation | [Frames and reach](../lessons/0002-frames-and-reach.html): explore a two-link sketch | Ready |
| M1 | Contacts, friction, grasping, and hand-off failure | Add alongside contact code |
| M2 | Demonstrations, train/test splits, and ACT action chunks | Add alongside data collection/training |
| M2 | Visual reasoning, supervisor state, and recovery | Add alongside planner integration |
| M3 | Randomization, evaluation leakage, and uncertainty | Add alongside frozen evaluation |
| M3 | OpenVINO precision, device choice, and benchmarks | Add alongside Intel measurements |

The reach sketch is an educational two-link illustration, not an SO-101 simulator.
The pendulum replay is actual MuJoCo output, not a trained manipulation policy.
Distinguish the two when interpreting results.

Review vocabulary in [the glossary](../reference/glossary.html). Record mastery only
when demonstrated through explanations or exercises; simply reading a lesson does
not automatically update learning records. Review earlier concepts in later lessons.
