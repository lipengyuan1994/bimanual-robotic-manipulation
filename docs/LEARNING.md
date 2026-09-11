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
| M1 foundation | [Two real simulated arms](DUAL_ARM_FOUNDATION.md): inspect channel ordering, timestamps and wrist views | Running code and five-minute exercise |
| M1 contact skill | [Contacts, grasps, and hand-offs](../lessons/0003-contacts-grasps-handoffs.html), then [run a contact grasp](CONTACT_GRASP.md) | Grasp and placement run locally; [physical hand-off walkthrough](HANDOFF.md) available |
| M1 drawer | [Open a physical drawer](DRAWER.md): distinguish motor commands, handle contact and passive movement | Drawer and retrieval run in the continuous teacher |
| M2 data groundwork | [Demonstrations and ACT](../lessons/0004-demonstrations-and-act.html): build an aligned data contract | [Recording contracts](INTERFACES.md) and [dataset export](DATASETS.md) connect to running code; ACT fitting and saved-checkpoint inference run; learned dinner success remains incomplete |
| Preparation extension | [Supervision and recovery](../lessons/0005-supervision-and-recovery.html): separate planning from stopping | Ready; [live planner and supervisor](PLANNER_LIVE_INTEGRATION.md) now connect to actual cameras |
| Preparation extension | [Evaluation and uncertainty](../lessons/0006-evaluation-and-uncertainty.html): freeze the test before model choice | Ready; conceptual, no frozen task suite yet |
| Preparation extension | [OpenVINO and benchmarks](../lessons/0007-openvino-and-benchmarks.html): measure actual target-device behavior | Ready; conceptual, no Intel host yet |

The reach sketch is an educational two-link illustration, not an SO-101 simulator.
The pendulum replay is actual MuJoCo output, not a trained manipulation policy.
Distinguish the two when interpreting results.

Review vocabulary in [the glossary](../reference/glossary.html). Record mastery only
when demonstrated through explanations or exercises; simply reading a lesson does
not automatically update learning records. Review earlier concepts in later lessons.

## Exercise from the current build: better errors, still a failed skill

Read the [20,000-update ACT result](TRAINING.md). Its nominal launch tool error
fell below one millimetre, but the first commanded pan movement still had the
wrong sign. Why did we keep this checkpoint out of physical validation?

**Check your answer:** an average error can hide a failure at a critical moment.
The acceptance rule required the first movement to have the correct direction
as well as improvements in average errors. Passing five conditions cannot cancel
the sixth failure. We retained the rule and recorded a new training experiment.
This exercise links lesson 4 (imitation learning) and lesson 6 (honest evaluation).
Reading this feedback is not a recorded demonstration of mastery.
