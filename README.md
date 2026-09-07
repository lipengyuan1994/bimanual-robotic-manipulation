# Bimanual manipulation lab

Building a dependable, language-directed dinner-table simulation with two SO-101
arms. The long-term product is an inspectable workstation application with learned
manipulation, recovery, reproducible evaluation, and Intel OpenVINO deployment.

**Current release: preparation foundation.** The executable lab is a generic
pendulum for learning and runtime validation. Dinner-table manipulation, ACT/VLM
integration, and Intel demonstration have **not** been implemented or validated.
The accepted plan reserves submission-specific AI work until the early-work
policy is clarified. [Current status](docs/STATUS.md) · [Accepted plan](docs/PLAN.md)

## Start here

1. Follow the [native setup guide](docs/SETUP.md).
2. Run `.venv/bin/bimanual doctor --require-device mps --record`.
3. Run `.venv/bin/bimanual lab --seed 7 --seconds 4`.
4. Build the portal in `web` with `npm ci` and `npm run build` using native Node.
5. Run `.venv/bin/bimanual serve` and open <http://127.0.0.1:8767>.

Every lab run saves a real MuJoCo replay, trajectory CSV, scene, configuration,
versions, source digests, and an integrity manifest under ignored `.artifacts/`.
Failures are retained. These are preparation results, not hackathon scores.

## Learn while we build

- [Public learning site](https://lipengyuan1994.github.io/bimanual-robotic-manipulation/)
- [Lesson 1: Observe, act, and step time](lessons/0001-observe-act-step.html)
- [Lesson 2: Frames and reachable positions](lessons/0002-frames-and-reach.html)
- [Robotics vocabulary](reference/glossary.html)
- [Learning mission](MISSION.md) · [Primary resources](RESOURCES.md)

## Engineering navigation

[Documentation index](docs/README.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Requirements and rubric](docs/REQUIREMENTS.md) ·
[Evidence rules](docs/EVIDENCE.md) · [Organizer questions](docs/ORGANIZER_QUESTIONS.md)

Run `scripts/check.sh --render` for Python, documentation, and rendering checks.
Run `npm run check` and `npm run build` in `web` for the portal.

No paid compute, hosted inference, physical robot, or account credentials are needed
for this preparation release. The final challenge requires separate access to an
actual Intel Core Ultra Series 2/3 machine.
