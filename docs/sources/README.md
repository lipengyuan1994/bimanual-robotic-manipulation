# Source register

Requirements inspected on 2026-09-05:

- [Online-track PDF](https://drive.google.com/file/d/1xSisqTQUAFQiLOpjLZrCVTCsQi4bMCpO/view):
  five pages; 123,398 bytes; SHA-256
  `9becb38230f69ff0966d27ec2a413ef48868986a4a32581c5abb07aaf5801fe9`.
  These values identify the brief read during planning. Recheck before accepting a
  newer brief; preserve material changes in the requirements/decision records.
- [Event page](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon): online
  build September 10–16, 2026; reread during implementation preparation.
- [General lablab guidance](https://lablab.ai/guide/ai-hackathons): general early-code
  and submission guidance, not an event-specific eligibility ruling.
- [SO-101 model](https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/robotstudio_so101):
  proposed asset source, pinned repository commit
  `8161bba264d7fa7c99ca301e91e7fb44737676ad`, Apache-2.0.
  The model, required meshes, README, changelog and license are now vendored in
  `src/bimanual/models/robotstudio_so101`; `UPSTREAM.json` contains per-file
  SHA-256 hashes. Original source files are unmodified. Composition and camera
  orientation changes occur in our scene builder and are documented in the
  [foundation walkthrough](../DUAL_ARM_FOUNDATION.md).

The generic pendulum MJCF and lesson diagrams are authored in this repository
under its MIT license. Model names in the plan are not claims that weights were
downloaded, deployed, or validated. Learning sources are indexed in
[RESOURCES](../../RESOURCES.md).
