# Hackathon submission handoff

Updated 2026-09-16. This document is the operator handoff for the final submission
window. It records what can be claimed from sealed evidence and what remains
unavailable. Do not describe the project as a completed autonomous dinner-table
system.

## Claimable result

The repository contains a MuJoCo dual SO-101 simulation, contact-based teacher
demonstrations, bounded ACT training and inference interfaces, task supervision,
recovery guards, evidence manifests, a read-only portal, seven lessons, and a
GitHub Pages workflow. Native Apple Silicon checks and teacher physical foundation
evidence are complete. A 20,000-update ACT run completed on native CPU, but its
sealed physical evaluation stopped safely when the learned bar placement exceeded
the workbench-overlap limit by 2.537 mm. Five fresh contact-only corrective teacher
sources subsequently passed; they remain teacher data until a complete export,
retraining, and learned evaluation are independently verified.

## Do not claim

There is no evidence for full learned dinner completion, learned hand-off success,
held-out generalization, OpenVINO inference, Intel Core Ultra execution, or release
qualification. No physical robot deployment is included. The incomplete export
directories under `.artifacts/datasets/bar-cpu-late-workbench-overlap-v9*` are not
training inputs and must not be submitted as datasets.

## Three-hour operator sequence

1. Export the sealed corrective view from a normal macOS Terminal, where the long
   image/parity operation can outlive the Codex command worker:

   ```sh
   .artifacts/training-venv/bin/bimanual bar-overlap-export \
     --views .artifacts/experiments/bar-cpu-late-workbench-overlap-v9-views.json \
     --destination .artifacts/datasets/bar-cpu-late-workbench-overlap-v9-r4 \
     --repo-id local/bar-cpu-late-workbench-overlap-v9-r4
   ```

2. Verify the export. Stop if `EXPORT_FAILED.json` exists or the manifest is
   missing:

   ```sh
   .artifacts/training-venv/bin/bimanual bar-overlap-export-check \
     .artifacts/datasets/bar-cpu-late-workbench-overlap-v9-r4
   ```

3. If export verification passes, create a new sampling declaration and record its
   manifest, then train only under a new experiment declaration. A completed
   training run still requires a fresh physical evaluation; do not reuse a consumed
   evaluation declaration.

4. For the presentation, show the teacher foundation run, the failed learned
   placement stopping at the contact guard, the sealed diagnosis, and the recovery
   data boundary. This is a reproducible robustness story even if learned full-task
   success is not reached.

## Submission inputs

Prepared upload assets are under `assets/submission/`:

- `tablemate-cover.png` — 1672×941 16:9 cover image.
- `tablemate-teacher-evidence.mp4` — 58-second camera replay of a sealed,
  contact-based corrective teacher run. It is teacher evidence; it does not
  claim learned full-task success.
- `tablemate-submission-final.pdf` — six-slide 16:9 presentation PDF.
- `tablemate-submission-final.pptx` — editable source deck; the PDF is the
  required upload for the slide field.

The deck passed package integrity, layout, font, and Artifact Tool import checks;
the validation receipt is kept in `.presentation-build/finalizer/`.

The packager remains the final gate:

```sh
.venv/bin/bimanual submission-check \
  --revision "$(git rev-parse HEAD)" \
  --release-protocol .artifacts/releases/CANDIDATE.json \
  --release-suite "$RELEASE_SUITE_RUN_ROOT" \
  --interactive-url https://YOUR_HOST/app \
  --video demo.mp4 --slides slides.pdf --cover cover.png
```

It must report every missing input before packaging. A failed check is evidence of
an incomplete submission, not a reason to bypass the gate. If the release suite or
Intel evidence is still absent at the deadline, submit the repository and learning
site links with the limitations above stated plainly.

## Evidence links

- [Project status](STATUS.md)
- [Reproduction runbook](RELEASE_REPRODUCTION.md)
- [Evidence contract](EVIDENCE.md)
- [Learning site](GITHUB_PAGES.md)
