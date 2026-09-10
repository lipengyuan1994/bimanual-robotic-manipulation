#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'This bootstrap requires native Apple Silicon; see docs/SETUP.md for other hosts.' >&2
  exit 1
fi
BIMANUAL_UV=${BIMANUAL_UV:-/opt/homebrew/bin/uv}
if [ ! -x "$BIMANUAL_UV" ]; then BIMANUAL_UV="$HOME/.local/bin/uv"; fi
file -L "$BIMANUAL_UV" | /usr/bin/grep -q arm64 || {
  echo 'A native ARM64 uv executable is required.' >&2; exit 1;
}
# Reuse only an already verified native interpreter; never select by generic version.
BIMANUAL_PYTHON=${BIMANUAL_PYTHON:-"$PWD/.venv/bin/python"}
file -L "$BIMANUAL_PYTHON" | /usr/bin/grep -q arm64
"$BIMANUAL_PYTHON" -c 'import platform,sys; assert platform.machine() == "arm64"; assert sys.version_info[:2] == (3,12)'
export UV_PYTHON_INSTALL_DIR="$PWD/.artifacts/uv-python-arm"
export UV_CACHE_DIR="$PWD/.artifacts/uv-cache"
export UV_PROJECT_ENVIRONMENT="$PWD/.artifacts/training-venv"
export HF_HOME="$PWD/.artifacts/huggingface"
if [ -e "$UV_PROJECT_ENVIRONMENT/bin/python" ]; then
  "$UV_PROJECT_ENVIRONMENT/bin/python" -c 'import platform; assert platform.machine() == "arm64"'
fi
"$BIMANUAL_UV" sync --frozen --extra training --python "$BIMANUAL_PYTHON" --no-python-downloads
"$UV_PROJECT_ENVIRONMENT/bin/bimanual" doctor --require-device cpu
