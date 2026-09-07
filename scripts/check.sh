#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
.venv/bin/python -c 'import platform; assert platform.system() != "Darwin" or platform.machine() == "arm64"'
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/pytest -m 'not render'
.venv/bin/bimanual docs-check
.venv/bin/python scripts/sync_readme.py --check
if [ "${1:-}" = --render ]; then .venv/bin/pytest -m render; fi
