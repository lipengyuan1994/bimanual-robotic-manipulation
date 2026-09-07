# Project status

Updated: 2026-09-07. Branch: `codex/preparation-foundation`.

## Current boundary

M0 preparation is complete and validated locally. No dinner-table scene, teacher, manipulation
policy, VLM execution, recovery supervisor, or Intel deployment is available yet.
This implements the preparation portion of the accepted plan; the full product
is not complete. See [decision 0001](decisions/0001-preparation-boundary.md).

## Implemented

- Native-runtime bootstrap and a locked Python package with optional ML/training dependencies.
- CLI diagnostics, CPU/MPS arithmetic probe, and compiled-extension architecture audit.
- General MuJoCo pendulum at 200 Hz physics / 20 Hz control; CSV and rendered replay.
- File-integrity manifests, explicit evidence types, retained failures, and a SQLite run index.
- Read-only FastAPI/React project portal, documentation navigation, and seven
  beginner lessons. Lessons 3–7 are conceptual preparation for later code and
  make no claim that contact, ACT, supervisor, evaluation, or Intel components exist.
- Requirement/rubric matrix, architecture and interface specifications, staged roadmap,
  experiment protocol, organizer-question draft, and learning records.
- Project-scoped OpenViking retrieval instructions and an explicit
  [indexing prompt](OPENVIKING.md). This documentation change does not ingest
  project files; the initial project index is still pending.
- A static GitHub Pages learning-site build and deployment workflow. It is
  separate from the local operator portal. The public site and clean deployment
  run are verified; see [public-site operations](GITHUB_PAGES.md).
- Generated README release and lesson sections, sourced from `project.json`, with
  a local hook and required CI validation. See [native setup](SETUP.md).

## Verification

See [the preparation validation record](experiments/2026-09-05-preparation.md).
The native bootstrap, 85-library architecture audit, CPU/MPS arithmetic,
18 Python tests (including rendering), TypeScript checks, frontend build, and 136
documentation links pass.
The portal, actual replay, lesson navigation, quiz feedback, and frame sliders
were also checked in the in-app browser. GitHub-hosted CI completed successfully
for the seven-lesson publication.

Recorded runtime: `20260905T152424-e96b10d91751`.
Recorded four-second lab: `20260905T152602-c1fb0930e38a` (81 observations).
Both local manifests verify. These are preparation checks, not learned-task results.

Current checkpoint: the verified seven-lesson publication and its CI are on the
branch above. Each recorded run includes the dirty flag and source-file digests.
No manipulation checkpoint or dataset exists yet.

## Blocking dependencies

| ID | Owner | Needed | Consequence |
|---|---|---|---|
| B1 | User / organizers | Event-specific early-work ruling | M1/M2 implementation remains pending |
| B2 | User / organizers | Remote Core Ultra Series 2/3 access | Intel compliance cannot be demonstrated |
| B3 | User / organizers | Assets/seeds, scope, deadline and submission fields | Submission packaging remains provisional |

No paid credits are assumed. No organizer message has been sent.

## Next executable steps

1. Open the local portal at <http://127.0.0.1:8767>; restart with
   `.venv/bin/bimanual serve` if needed.
2. Continue from [lesson 3](../lessons/0003-contacts-grasps-handoffs.html); lessons
   3–7 are concepts for later implementation and are clearly labelled as such.
3. Obtain the event-specific answers in [the organizer draft](ORGANIZER_QUESTIONS.md)
   and arrange remote Intel access. No response is assumed.

When B1 is resolved, record the exact source and ruling in a new decision record,
then begin M1 from [the roadmap](ROADMAP.md). If the ruling disallows early work,
retain the preparation history and wait for the allowed build window. Do not
retroactively describe preparation as challenge-task success.
