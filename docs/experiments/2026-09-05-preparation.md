# Experiment: preparation runtime and project foundation

Status: passed for local preparation, 2026-09-05. Manipulation and Intel validation
remain unimplemented. This record does not establish production readiness.

## Question

Can this native Apple Silicon environment run a reproducible, rendered MuJoCo
learning example, perform a tested CPU/MPS arithmetic probe, and serve the
documentation/learning portal without any manipulation-model dependency?

## Reproduction

Host: Apple M1 Pro, 32 GiB RAM, macOS 26.5.2. Python 3.12.13, verified arm64.
The dependency resolution is locked in `uv.lock` and `web/package-lock.json`.
Base revision: `e561487f537bbeb52410715a2967b42f14b62bdd`; the implementation is
uncommitted on `codex/preparation-foundation`. Recorded manifests identify this
dirty state and hash the source files present at the time of each run.
No model weights, training job, paid resource, or Intel machine is used.

Verified managers: `/opt/homebrew/bin/uv` 0.12.1 and `/opt/homebrew/bin/node`
24.19.0, both native arm64. The bootstrap also passed when invoked literally with
`BIMANUAL_PYTHON=/Users/lipengyuan/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12`.
Its separate ARM-only Python store is `~/.local/share/uv/python-arm64`.

Commands from the repository root:

```sh
scripts/check.sh --render
.venv/bin/bimanual doctor --require-device mps --record
.venv/bin/bimanual lab --seed 7 --seconds 4
.venv/bin/bimanual evidence verify 20260905T152424-e96b10d91751
.venv/bin/bimanual evidence verify 20260905T152602-c1fb0930e38a
```

In `web`, with native Node selected: `npm ci`, `npm run check`, and `npm run build`.
Use [setup](../SETUP.md) for a fresh checkout. The existing-environment bootstrap
was validated; a clean-machine installation and remote CI execution remain pending.

## Results

| Check | Observed result | Scope |
|---|---|---|
| Python native audit | 85 compiled libraries checked; 5 universal files include arm64; zero missing ARM slices | Installed core + ML dependencies |
| MuJoCo | 3.12.0 stepping and offscreen rendering passed | Generic one-joint scene |
| PyTorch | 2.11.0; CPU and actual `mps:0` float32 matrix multiplication agree, max absolute error 0.0 | Small arithmetic probe only |
| Other runtime packages | NumPy 2.2.6, torchvision 0.26.0, FastAPI 0.141.1 | Installed versions |
| Python validation | 17 non-render tests and 1 actual-render test passed; Ruff lint and format passed | Determinism, failures, integrity, API boundaries, native-runtime guard, docs |
| Documentation graph | 130 local links resolve; rubric totals 100 | Files and milestone status data |
| Portal | TypeScript check and Vite production build passed | Local build with React 19.2.8 / Vite 8.2.2 |
| Node extensions | Lightning CSS and Rolldown arm64; fsevents universal with arm64 | Native build path |
| Browser | Portal/replay, local lessons and the seven-lesson public site load; quiz feedback and sliders work | In-app browser at loopback and Pages URLs |
| Browser diagnostics | No warning/error logs on checked pages | Manual local smoke check |

The slider check set both angles to 180 degrees and observed a tip at
(-0.100, approximately 0.000) metres, consistent with the lesson's two-link
equations. This is teaching-interface QA, not evidence of the learner's mastery.

Two retained runs live under ignored `.artifacts/runs`:

- `20260905T152424-e96b10d91751`: runtime probe, **passed**. Contains `doctor.json`
  and the source/configuration manifest. The timed MPS probe is not a latency benchmark.
- `20260905T152602-c1fb0930e38a`: pendulum, **completed**, seed 7, damping 0.1,
  torque amplitude 0.2 Nm, render enabled. Contains the XML scene, configuration,
  CSV, preview PNG and actual GIF replay, plus integrity/provenance manifest.

The lab recorded 81 observations over 4.0 simulated seconds at 200 Hz physics /
20 Hz control. Its measured simulation/render loop took 0.294 wall seconds
(13.61 simulation seconds per loop wall second). This timing excludes setup,
renderer initialization, GIF encoding, and manifest creation; it is **not**
application throughput. Current code explicitly records that timing scope.
The record has `manipulation_success: null`.

Lab manifest digest:
`57a9a8d01e1a5d275ea9b5917ec7064365bbb6de97b99da15a7afd884cc0c0cf`.
Both run manifests pass current verification. They retain their original source
digests; later formatting, portal and documentation edits do not rewrite them.

## Limitations and next gate

- LeRobot and Transformers extras resolve in the lock but are not installed or
  executed here. No ACT training, Qwen model load, policy inference, or OpenVINO
  conversion has been measured.
- The CPU/MPS probe does not test every operator required by future models.
- Upstream Starlette/httpx and AnyIO TestClient deprecation warnings remain
  visible in the passing test output; they are not hidden with warning filters.
- The GitHub Actions workflow is authored but has not been pushed or run remotely.
- The portal is a read-only preparation application, without dinner-table controls.
- Early-work clarification, Intel access, and remaining submission details are
  still needed. See [status](../STATUS.md) and [the organizer draft](../ORGANIZER_QUESTIONS.md).
- The public learning site is published and its clean GitHub Actions build/deploy
  is recorded in [GitHub Pages operations](../GITHUB_PAGES.md). It does not
  broaden the preparation boundary.
