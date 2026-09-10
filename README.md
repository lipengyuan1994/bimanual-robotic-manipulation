# Bimanual manipulation lab

Building a dependable, language-directed dinner-table simulation with two SO-101
arms. The long-term product is an inspectable workstation application with learned
manipulation, recovery, reproducible evaluation, and Intel OpenVINO deployment.

<!-- README-STATUS:START -->
**Current release: Dual-arm foundation.**

- Challenge manipulation: not available
- Intel target: not validated
- Active blockers: B2, B3
- Status data updated: 2026-09-10

The complete evidence and handoff record is in [docs/STATUS.md](docs/STATUS.md).
<!-- README-STATUS:END -->

Event-window implementation is authorized in [decision 0003](docs/decisions/0003-event-window-implementation.md).
The first M1 slice loads two SO-101 arms with bounded control and three cameras.
Drawer use, grasping, hand-off and learned execution remain pending. [Accepted plan](docs/PLAN.md)

## Start here

1. Follow the [native setup guide](docs/SETUP.md).
2. Run `.venv/bin/bimanual doctor --require-device mps --record`.
3. Run `.venv/bin/bimanual sim --seconds 4` for the two-arm foundation.
4. Build the portal in `web` with `npm ci` and `npm run build` using native Node.
5. Run `.venv/bin/bimanual serve` and open <http://127.0.0.1:8767>.

Every rendered run saves a real MuJoCo replay, trajectory, scene, configuration,
versions, source digests, and an integrity manifest under ignored `.artifacts/`.
Failures are retained. These foundation results do not establish task success.
Follow the [two-arm walkthrough](docs/DUAL_ARM_FOUNDATION.md) to inspect mappings
and camera views; the original pendulum remains available with `bimanual lab`.

## Learn while we build

<!-- README-LEARNING:START -->
- [Public learning site](https://lipengyuan1994.github.io/bimanual-robotic-manipulation/)
- [Lesson 01: Observe, act, and step time](lessons/0001-observe-act-step.html) — 15 min
- [Lesson 02: Frames and reachable positions](lessons/0002-frames-and-reach.html) — 15 min
- [Lesson 03: Contacts, grasps, and hand-offs](lessons/0003-contacts-grasps-handoffs.html) — 15 min
- [Lesson 04: Demonstrations and ACT](lessons/0004-demonstrations-and-act.html) — 15 min
- [Lesson 05: Supervision and recovery](lessons/0005-supervision-and-recovery.html) — 15 min
- [Lesson 06: Evaluation and uncertainty](lessons/0006-evaluation-and-uncertainty.html) — 15 min
- [Lesson 07: OpenVINO and benchmarks](lessons/0007-openvino-and-benchmarks.html) — 15 min
- [Robotics vocabulary](reference/glossary.html)
- [Learning mission](MISSION.md) · [Primary resources](RESOURCES.md)
<!-- README-LEARNING:END -->

## Engineering navigation

[Documentation index](docs/README.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Requirements and rubric](docs/REQUIREMENTS.md) ·
[Evidence rules](docs/EVIDENCE.md) · [Organizer questions](docs/ORGANIZER_QUESTIONS.md)

Run `scripts/check.sh --render` for Python, documentation, and rendering checks.
Run `npm run check` and `npm run build` in `web` for the portal.

No paid compute, hosted inference, physical robot, or account credentials are needed
for this foundation release. The final challenge requires separate access to an
actual Intel Core Ultra Series 2/3 machine; see [free access routes](docs/INTEL_ACCESS.md).
