# Native setup and current commands

Run commands from the repository root unless stated otherwise. This release is
intended to run from its checkout; the portal loads repository documentation.

## Apple Silicon

Use native Homebrew `uv` and an ARM-only Python store:

```sh
chmod +x scripts/bootstrap.sh scripts/check.sh
scripts/bootstrap.sh
```

The bootstrap verifies architecture, installs the exact aarch64 Python 3.12.13 in
the separate store when needed, then syncs `uv.lock` with the ML extra. It does not
download model weights or start training. Python's generic version file is only
editor metadata and must not select an Intel cached interpreter.

An already verified native interpreter can be selected explicitly:

```sh
BIMANUAL_PYTHON=/absolute/path/to/macos-aarch64/bin/python3.12 scripts/bootstrap.sh
```

The `ml` extra installs PyTorch/torchvision. The training extra now supports
verified recordings, LeRobot dataset export and ACT execution. To create its
separate native environment without changing the simulator environment:

```sh
sh scripts/bootstrap-training.sh
HF_HOME="$PWD/.artifacts/huggingface" .artifacts/training-venv/bin/bimanual training-probe --device cpu
```

This selects the existing verified native `.venv/bin/python` (or an explicit
`BIMANUAL_PYTHON`), uses a separate ARM-only interpreter/cache location, installs
the frozen training extra and audits compiled libraries. It does not download
model weights or upload data. See [training details](TRAINING.md) and
[dataset operations](DATASETS.md). The reasoning extra remains for later use.
Installing packages alone is not an ACT or VLM implementation.

Bootstrap also installs the repository's local Git hook. It checks that the generated
README status sections agree with `docs/project.json` before each commit. To install
it in an existing checkout without re-running bootstrap, use:

```sh
scripts/install-git-hooks.sh
```

The hook is a convenience check; GitHub Actions runs the same validation for every
push and pull request. Update the project record and narrative status first, then
refresh the README with `.venv/bin/python scripts/sync_readme.py --write`.

## Current CLI

```sh
.venv/bin/bimanual doctor --require-device mps --record
.venv/bin/bimanual doctor --require-device cpu
.venv/bin/bimanual lab --seed 7 --seconds 4
.venv/bin/bimanual lab --seed 7 --seconds 4 --damping 0.8 --no-render
.venv/bin/bimanual sim --seconds 4
.venv/bin/bimanual sim --seconds 4 --no-render
.venv/bin/bimanual grasp --destination -.15 .08
.venv/bin/bimanual grasp --arm right --destination .15 -.08
.venv/bin/bimanual grasp --destination -.15 .08 --record-demo --seed 0 --split train
.venv/bin/bimanual handoff
.venv/bin/bimanual evidence list
.venv/bin/bimanual evidence verify RUN_ID
.venv/bin/bimanual status
.venv/bin/bimanual docs-check
scripts/check.sh --render
```

`RUN_ID` is printed by `lab` or recorded `doctor`. Each execution gets a new run
directory. Use `--artifacts /absolute/directory` before the subcommand to choose a
different store. No-render mode is labeled explicitly; it does not validate cameras.

## Portal

Use native Node 24 (verify `file -L` and `node -p process.arch`, which must report
`arm64` on this Mac). In `web`, run:

```sh
npm ci
npm run check
npm run build
```

Then, from the repository root:

```sh
.venv/bin/bimanual serve
```

Open <http://127.0.0.1:8767>. The API is read-only and bound to loopback. If port
8767 is busy, use `serve --port 8768`; do not stop unrelated services.
The documentation and lessons can also be opened directly from the checkout.

## Rendering

Offscreen rendering uses MuJoCo's macOS OpenGL context; it is independent of
PyTorch MPS. The interactive native viewer needs `mjpython` on macOS:

```sh
.venv/bin/mjpython -m mujoco.viewer --mjcf=src/bimanual/models/pendulum.xml
```

## Other hosts

The Apple bootstrap deliberately refuses other architectures. For Linux CPU CI,
use a Python 3.12 host and `uv sync --frozen`; headless rendering needs a working
OpenGL/EGL/OSMesa setup. Intel runtime instructions remain a separate, unvalidated
target until hardware is available. See [deployment](DEPLOYMENT.md).

## Check a built wheel in a fresh native environment

Use a new output/environment directory for each check. The following base-package
procedure was exercised offline on this Mac; cached dependencies are required.
A cache miss is an incomplete offline check, not permission to use another
architecture or an unlocked dependency set.

```sh
BIMANUAL_PYTHON=/Users/lipengyuan/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12
"$BIMANUAL_PYTHON" -c 'import platform; assert platform.machine() == "arm64"'
file /opt/homebrew/bin/uv
export UV_PYTHON_INSTALL_DIR=/Users/lipengyuan/.local/share/uv/python-arm64
/opt/homebrew/bin/uv build --offline --wheel --python "$BIMANUAL_PYTHON" --out-dir .artifacts/wheel-check-dist
/opt/homebrew/bin/uv export --offline --frozen --no-dev --no-emit-project --format requirements-txt --output-file .artifacts/wheel-check-requirements.txt
/opt/homebrew/bin/uv venv --python "$BIMANUAL_PYTHON" .artifacts/wheel-check-env
/opt/homebrew/bin/uv pip sync --offline --require-hashes --python .artifacts/wheel-check-env/bin/python .artifacts/wheel-check-requirements.txt
/opt/homebrew/bin/uv pip install --offline --no-deps --python .artifacts/wheel-check-env/bin/python .artifacts/wheel-check-dist/bimanual_sim-0.1.0-py3-none-any.whl
.artifacts/wheel-check-env/bin/python -c 'import bimanual; print(bimanual.__file__)'
.artifacts/wheel-check-env/bin/bimanual doctor --require-device cpu
```

The import path must point into `wheel-check-env`, not the source checkout or
another environment. Preserve the wheel and lockfile hashes with the diagnostic
output. Run `20260911T140058-01b5bd0ef785` verified a fresh base installation,
68 native extensions, CPU arithmetic and MuJoCo stepping. It did not install ML
extras or validate rendering, learned control, or Intel compatibility; those
remain separate checks. Later source changes require their own wheel validation.
