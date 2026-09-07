#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'This bootstrap is for native Apple Silicon. See docs/SETUP.md for other hosts.' >&2
  exit 1
fi
BIMANUAL_UV=${BIMANUAL_UV:-/opt/homebrew/bin/uv}
if [ ! -x "$BIMANUAL_UV" ]; then BIMANUAL_UV="$HOME/.local/bin/uv"; fi
file -L "$BIMANUAL_UV" | /usr/bin/grep -q arm64 || {
  echo 'A verified ARM64 uv executable is required.' >&2; exit 1;
}
export UV_PYTHON_INSTALL_DIR="$HOME/.local/share/uv/python-arm64"
BIMANUAL_PYTHON=${BIMANUAL_PYTHON:-}
if [ -z "$BIMANUAL_PYTHON" ]; then
  "$BIMANUAL_UV" python install cpython-3.12.13-macos-aarch64-none
  BIMANUAL_PYTHON="$UV_PYTHON_INSTALL_DIR/cpython-3.12.13-macos-aarch64-none/bin/python3.12"
fi
file -L "$BIMANUAL_PYTHON" | /usr/bin/grep -q arm64
"$BIMANUAL_PYTHON" -c 'import platform; assert platform.machine() == "arm64"'
if [ -e .venv/bin/python ]; then
  .venv/bin/python -c 'import platform; assert platform.machine() == "arm64"'
fi
"$BIMANUAL_UV" sync --frozen --python "$BIMANUAL_PYTHON" --extra ml
.venv/bin/bimanual doctor --require-device mps
